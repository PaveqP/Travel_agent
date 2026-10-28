# Текущее устройство: факты из кода

Это статическое исследование актуального SHA; ниже нет утверждений о реально выполненных live-агентах.

## Запуск и пользовательский путь

`compose.yaml`: PostgreSQL 17 → FastAPI app → React/nginx. Backend: `travel_agent.web:create_web_app`, одна worker; frontend proxy и API на одном origin, наружу loopback:8000. PostgreSQL volume постоянный. Dockerfile использует Python 3.11 и lock; локальный Python 3.13.7. `scripts/serve_web.py` — существующий запуск без Docker-приложения; может поднять штатный Compose postgres. Здесь не запускался, поскольку LLM-конфигурация отсутствует. `chat.py` — публичный CLI с локальным SQLite, не заменяет веб/БД preflight.

`frontend/src/main.jsx`: fetch API с cookie; регистрация/логин `/api/auth/*`; POST `/trips`; POST `/trips/{id}/messages` передаёт message/revision. Ответ — JSON view с историей/карточками/пакетами. SSE `/trips/{id}/events` показывает прогресс и previews, **не token streaming**. Выбор `/trips/{id}/select/{option_id}`, покупка `/trips/{id}/bookings`. UI предоставляет профиль, список поездок, корзину/оформление, PDF и сопровождение. Никаких продуктовых запросов в этом исследовании не отправлено.

## Workflow и реальные роли

`graph.build_graph` по умолчанию выбирает `planning.build_planning_graph` (autonomous=True); прежний пошаговый режим сохранён. START → supervisor → delegate / evaluate / respond / answer / research / finish. delegate через Send отправляет готовые независимые задачи специалистам. transport/stays/experience → evaluate; evaluate при зависимостях возвращается в delegate, при feedback один repair круг, затем respond → finish → END. Вопрос может идти через answer, исследование через research → answer. Supervisor использует typed TurnPlan, отдельный TripDelta extractor; repair — RepairPlan. Внешних tools у него нет. Presenter — отдельный LLM-вызов роли presenter; research использует модель существующего специалиста, это не новый отдельный специалист.

`agents/react.py` действительно вызывает `langchain.agents.create_agent`, ToolStrategy(SpecialistSelection), ModelCallLimitMiddleware(6), ToolCallLimitMiddleware(12 autonomous), context editing; отдельная финализация при оставшемся времени. Adapter ограничивает 10 внешних операций на делегацию. `Settings.deadline` по умолчанию 90s; API реальный timeout autonomous **360s**, не 240s из части документации. Модели API max_tokens: специалисты 4096, supervisor 2600, presenter 3000. SDK retries=0; MCP runtime имеет до двух попыток timeout/network_error с общим timeout 63s. Изменять эти лимиты для искусственного прохождения не пытались.

## Доступные регистрации (не доказательство подключения)

| Роль | Tools | Физический runtime путь |
|---|---|---|
| Transport | search_flights, search_trains, transport_details | Tutu MCP search_avia/search_rail/search_etrain/get_offer_details |
| Transport | yandex_schedule, cached_flights | Яндекс Расписания REST, Travelpayouts REST (cache) |
| Stay (код stays) | search_hotels, hotel_details | Тот же Tutu MCP, product_type=hotels; ownership ID |
| Experience | search_places, route | 2ГИС MCP search_places/build_route |
| Experience | geoapify_places, weather, events, attractions | Geoapify REST, Open-Meteo REST, Timepad REST, OpenTripMap REST |
| Все три специалиста | tavily_search, tavily_extract | Tavily REST, Extract только URL текущего поиска |
| Supervisor | Нет внешних tools | Делегация через StateGraph |

Allowlist есть при сборке tools и перед adapter operation; MCP отдельно проверяет роль/метод и product/owned ID. В `integrations/mcp/client.py` также перечислены исследовательские Geoapify/LiteAPI/OpenWeather MCP, но наличие в SERVERS не означает разрешение этим runtime-агентам. Geoapify у Experience фактически REST. Для каждого MCP чтения создаётся connection, initialize, list_tools, затем call_tool; это потенциальная накладная задержка, здесь не измеренная. Tutu endpoint без ключа не доказывает бесплатность и доступность. Все фактические вызовы этого прогона = 0.

## Данные, память и покупки

`TripState` — TypedDict, add_messages history, task_results merge reducer. PostgreSQL checkpointer/store + Accounts; thread_id из владельца и trip ID, проверка ownership, блокировка пользовательского хода, проверка revision. Результаты параллельных задач принимаются evaluate только при совпадении revision и round; изменения инвалидируют зависимые роли. Подтверждения долговечности памяти в live нет.

`tools.normalize` преобразует live Tutu в Candidate, проверяет даты/состав/basis, provenance/expiry. Tutu party total не умножается повторно; hotels stay_total → room_stay, ЖД per_seat умножается на взрослых. Travelpayouts cache, Tavily/catalog и POI не становятся подтверждённым live quote. Weather проверяет горизонт; отсутствующие цены не становятся нулями. Engine компоновки проверяет географию/состыковки/программу и считает Decimal budget; полная стоимость при пропусках неизвестна.

`engine.simulate_purchase`: только локальная имитация, explicit confirm, revision/current selection, свежие quotes, бюджет и состыковки; idempotency. Результат simulated=true, paid=false, reserved=false; payment.status=succeeded относится только к симуляции. В runtime не вызываются реальный checkout и платёж. В существующих backend-тестах HTTP/LLM/MCP моки, в frontend browser tests перехватываются route ответы. Эти проверки не доказывают доступность live источников. Старые reports snapshots в новый E2E не подставлялись.

## Наблюдаемость и ограничения

UsageLogger: LLM run UUID, thread/role на start и input/output/total tokens на end. Нет единого persisted cost ledger/cached tokens/provider cost в обычном API. `run_react` пишет usage после успешного ainvoke; при лимитах этот финальный список неполон. tools.execute пишет роль/tool/provider/revision/status/duration; runtime_call отдельно attempts. Нет единой persisted trace JSONL по session/case/node, времени каждого узла, safe request parameters и cardinality. Custom graph progress и API status — изменяемая in-memory сводка, не полный event journal.

Статический дефект: early return в `tools.execute` при response.status != ok, error payload или empty не всегда присваивает локальную переменную status; finally может записать status=ok при возвращённом schema_error/empty/no_availability. Это риск неверной оценки MCP success rate, а не наблюдавшийся live сбой. Минимальные рекомендации в RECOMMENDATIONS.md. Инструментализацию не добавляли: live заблокирован до workflow, поэтому измерений, которые она могла бы собрать, нет.
