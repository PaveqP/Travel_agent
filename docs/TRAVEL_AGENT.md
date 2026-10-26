# Backend AI Travel Agent

FastAPI + CLI, без фронтенда. Четыре LLM-роли: Supervisor и три ограниченных ReAct-специалиста Transport, Stay, Experience. Внешний `StateGraph` проверяет решения Supervisor, ограничения, версии и результаты. Специалисты создаются стандартным `langchain.agents.create_agent`; они не изменяют TripState.

## Запуск

Python 3.11+. Используются существующие `MODEL`, `TOKEN`, `BASE_URL` из `.env`; файл не изменяется. Установка:

```bash
uv venv
uv pip sync requirements.lock.txt
```

Для постоянной памяти запустите PostgreSQL. Значения ниже — локальная конфигурация, не настройки внешних API:

```bash
export TRAVEL_POSTGRES_PASSWORD="$(python -c 'import secrets; print(secrets.token_hex(24))')"
docker compose up -d postgres
export TRAVEL_DATABASE_URL="postgresql://travel:${TRAVEL_POSTGRES_PASSWORD}@127.0.0.1:55432/travel"
export TRAVEL_API_TOKEN="$(python -c 'import secrets; print(secrets.token_hex(24))')"
.venv/bin/uvicorn travel_agent.api:app --host 127.0.0.1 --port 8000 --workers 1
```

Сохраните локальные значения для следующего запуска; не генерируйте новый пароль для уже существующего volume. В другом терминале задайте тот же `TRAVEL_API_TOKEN` и запустите:

```bash
.venv/bin/python -m travel_agent
# Продолжение ранее созданной поездки:
.venv/bin/python -m travel_agent --trip UUID
```

Без `TRAVEL_DATABASE_URL` работает временный InMemorySaver, который **не переживает перезапуск**. `/health` показывает `persistent`. Для приёмки восстановления необходим PostgreSQL. Без `TRAVEL_API_TOKEN` сервер не стартует. Несколько токенов через запятую — отдельные demo-пользователи; каждый клиент передаёт только свой токен. Это минимальная авторизация для локального хакатонного демо.

Пример диалога в CLI:

```text
Хочу из Москвы в Сочи, двое взрослых, бюджет 100000 рублей, море и прогулки.
С 12 по 16 ноября 2026 года.
Замени отель на Mirror Residence, билеты оставь прежними.
Сдвинь поездку на 13–17 ноября 2026 года.
/show
/select ID_ИЗ_OPTIONS
/book ID_ИЗ_OPTIONS unique-key-123 confirm
/quit
```

Даты примера использованы в проверке 26.10.2026; для будущих запусков выбирайте актуальные даты. `/book` выполняет только локальную имитацию. `simulated=true`, `paid=false`, `reserved=false`; реального резерва и оплаты нет. Повтор с тем же ключом возвращает ту же запись; другой вариант с тем же ключом отклоняется.

## API

Swagger: `http://127.0.0.1:8000/docs`. Все операции поездки требуют `Authorization: Bearer TOKEN`.

| Метод | Путь | Назначение |
|---|---|---|
| POST | `/trips` | Создать поездку, получить `trip_id` |
| GET | `/trips/{trip_id}` | Получить состояние и текущую `revision` |
| POST | `/trips/{trip_id}/messages` | `{message, revision}` — диалог и изменения |
| POST | `/trips/{trip_id}/select/{option_id}?revision=N` | Выбрать текущий вариант |
| POST | `/trips/{trip_id}/bookings` | `{option_id, revision, confirm, idempotency_key}` |
| PUT | `/profile` | JSON-массив интересов для последующих поездок |
| GET | `/health` | Готовность приложения и режим памяти |

Ответ содержит `status`: `needs_input`, `ready`, `partial`, `unavailable`, `unsupported` или `error`. `ready` означает наличие проверенных транспорта и проживания; он не подтверждает полную стоимость или бронирование. `partial` явно сообщает об отсутствующем компоненте.

`504` означает исчерпание общего deadline хода; перед повтором нужно прочитать текущее состояние поездки. `409` означает устаревшую revision, неизвестный вариант, конфликт idempotency key или просроченные котировки. Чужая поездка возвращает `404`. В одном процессе изменения каждой поездки сериализованы. Запускать с одним worker; распределённые блокировки не реализованы.

Short-term memory: сообщения, ограничения, evidence, варианты, выбор и simulated bookings в стандартном LangGraph checkpoint. Long-term memory: явно сохранённые интересы пользователя в `AsyncPostgresStore`; векторный поиск и автоматическое извлечение профиля не используются.

## Структура

```text
travel_agent/
  __init__.py
  __main__.py      CLI-клиент FastAPI
  api.py           lifespan, авторизация, память, API, simulation
  config.py        существующее окружение и настройки backend
  schemas.py       Pydantic-контракты
  state.py         TripState / add_messages
  graph.py         Supervisor, переходы, валидация результатов
  agents/
    model.py       конфигурация ChatOpenAI
    react.py       запуск стандартного create_agent и проверка evidence
    supervisor/agent.py
    transport/{agent.py,tools.py}
    stays/{agent.py,tools.py}
    experience/{agent.py,tools.py}
  tools.py         общие сетевые guards, Tavily, нормализация evidence
  engine.py        invalidation, география, itinerary, Decimal-бюджет
  prompts/
    loader.py      UTF-8, allowlist имён, проверка содержимого, LRU cache
    supervisor.md
    transport.md
    stays.md
    experience.md
integrations/
  mcp/client.py    runtime_call отдельно от research call
  providers/      совместимые параметризованные REST-функции
  schemas/        переиспользованные Money, Provenance, Budget
scripts/
  smoke_travel_agent.py
  smoke_travel_sources.py
tests/
  test_research.py
  test_travel_agent.py
  test_agent_isolation.py
  test_pipeline_e2e.py
  test_travel_postgres.py
  fixtures/searches.json
compose.yaml
```

Research entrypoints сохранены. Runtime не импортирует `integrations.core`, не отключает logging и не перезаписывает старые reports. Промпты включены в wheel.

## Источники и ограничения доступа

| Роль | Подключённые источники |
|---|---|
| Supervisor | Нет внешних инструментов; только типизированное решение |
| Transport | Tutu search_avia/search_rail/search_etrain и ограниченные avia details; Яндекс Расписания; Travelpayouts; Tavily |
| Stay | Tutu search_hotels и hotel details; Tavily |
| Experience | 2GIS search_places/build_route; Geoapify Places, Open-Meteo Forecast, Timepad, OpenTripMap; Tavily |

Тарифы для полноценного round-trip варианта нормализуются только из Tutu avia. Яндекс, Travelpayouts и железнодорожные результаты используются как контекст, а не автоматически как полноценный транспортный пакет. Произвольный город отправления передаётся Tutu; неподдержанная выдача не подменяется московскими билетами.

Allowlist проверяется при формировании инструментов и перед сетью. Tutu details проверяет тип продукта и принадлежность ID текущей делегации. Checkout, пассажирские данные и платежи не доступны. Tavily Extract допускает максимум три публичных HTTPS URL из Search текущей делегации. Tavily-контекст никогда не повышается до live цены.

Каждая роль имеет свой модуль, явный набор инструментов и отдельный узел внешнего графа. На старте создаются четыре экземпляра ChatOpenAI с одинаковыми настройками endpoint. История ReAct, evidence, список разрешённых IDs и URL живут только в делегации; checkpoint содержит валидированные результаты. Experience получает только проверенных кандидатов проживания, а не историю других специалистов. Ключи провайдеров фильтруются по роли перед формированием инструментов.

Обязательный primary search выполняется внутри роли до ReAct: модель не может его пропустить. Experience имеет один явный резерв Geoapify при пустой/ошибочной выдаче 2GIS. Затем стандартный `create_agent` допускает до 4 model calls и 6 дополнительных tool calls; суммарный лимит сетевых tool-операций — 8. Structured результат возвращается через стандартный `ToolStrategy`, без отдельного второго LLM-прогона. На делегацию отведено 90 секунд, `recursion_limit=20`. Supervisor ограничен 7 решениями; менять ограничения разрешено только на первом решении нового пользовательского хода.

Для безопасных MCP-чтений допускаются две попытки только при timeout/network_error: до 30 секунд на попытку и 63 секунды общего deadline. Forbidden, unauthorized, schema_error и rate_limited не повторяются. SDK retries отключены, повторные одинаковые запросы в делегации получают сохранённый ответ. При исчерпании лимита сохраняются наблюдённые кандидаты и причина partial. По явной просьбе пользователя `SupervisorDecision.refresh` инвалидирует только нужные роли и повышает revision.

## Расчёты и честные ограничения

- Поддерживаются 1–6 взрослых, 1–30 ночей, RUB. Детские тарифы, несколько номеров и сложные пересадки не реализованы.
- Tutu aviation price — вся группа туда-обратно; hotel price — весь срок проживания. Повторного умножения нет. Неизвестные налоги, питание, местный транспорт, активности и сборы не превращаются в ноль. `confirmed_total=null`.
- Проверяются даты/гости, round-trip, аэропорт AER, arrival/return и координаты. Географические зоны приблизительные; это не GIS-полигоны административных границ.
- Дневная программа — предложения из каталога, сгруппированные по району. Часы работы, точное расписание посещений, возможность успеть на трансфер и стоимость переездов не подтверждены. В дни прилёта и вылета активности не назначаются.
- Бюджет меняет ранжирование/расчёт; дата и гости обновляют зависимые результаты; замена отеля сохраняет транспорт. Если названный отель уже есть среди свежих котировок для тех же дат/гостей, сохраняется и котировка проживания, повторно собирается только Experience. Истёкшие или несовместимые котировки не переиспользуются. Известные суммы выше бюджета явно помечаются. Полная укладываемость в бюджет не обещается.
- Поисковые котировки имеют локальный срок свежести 10 минут, каталог — 60 минут. Это ограничение приложения, не гарантия поставщика. Истёкшие результаты пересобираются на следующем planning turn.
- Точечный ответ возвращает выбранные проверенные факты по ID в JSON. Свободное LLM-объяснение фактов не публикуется, поскольку его истинность нельзя проверить одной JSON-схемой.
- Tavily подключён, но ключ отсутствовал при проверке; live Search/Extract не проверены. Hotel/flight details не являются гарантированно работоспособным источником условий; были timeout/schema errors.
- Не все запросы модели заканчиваются полным результатом: ошибки источников и лимиты явно видны в `results.*.warnings`. Неполные варианты допустимы для просмотра, но не для mock booking.

## Проверки

Офлайн, без API/LLM расходов:

```bash
.venv/bin/python -m unittest discover -s tests -v
uv pip check
```

PostgreSQL integration mode на отдельной тестовой БД:

```bash
TRAVEL_TEST_DATABASE_URL="$TRAVEL_DATABASE_URL" .venv/bin/python -m unittest discover -s tests -p test_travel_postgres.py -v
```

Сетевые проверки требуют отдельного разрешения и бюджета:

```bash
.venv/bin/python scripts/smoke_travel_agent.py --budget-usd 0.20 --extended --repeat 2
.venv/bin/python scripts/smoke_travel_sources.py --read-only
```

Smoke скрипты пишут отдельные файлы в `/tmp`; не обновляют исследовательские snapshots. LLM-smoke резервирует консервативный byte-as-token потолок по $0.000002/token перед каждым запросом, после ответа учитывает `usage.cost`, а при отсутствии стоимости оставляет резерв. Guard сравнивает расход плюс незавершённые резервы с лимитом; `reserved_usd` в отчёте суммирует все временные резервирования, включая уже освобождённые, и не является расходом. Это сценарный guard для проверенного endpoint, не универсальный биллинг для произвольной модели. При изменении модели нужен новый тарифный аудит. Провайдерский smoke ограничен фиксированным набором read-only операций, использует существующие квоты ключей, не покупает доступ.

Результаты текущих запусков и различия между live и replay отражены в [отчёте](TRAVEL_AGENT_VALIDATION.md).
