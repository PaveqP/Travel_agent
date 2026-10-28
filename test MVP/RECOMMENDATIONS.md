# Рекомендации по подтверждённым данным

Live-поведения нет. Ниже разделены воспроизводимые проблемы окружения, статические дефекты и гипотезы для измерения; не делаются выводы о фактическом качестве ответов или скорости агентов.

| Приоритет | Проблема | Доказательство | Причина | Рекомендация |
|---|---|---|---|---|
| P0 | UI/backend: невозможно поднять реальную систему | PREFLIGHT.md: нет .env/LLM/БД, startup RuntimeError, health ConnectError | Среда не подготовлена | Восстановить существующие секреты и PostgreSQL настройки; использовать штатный Compose, не менять модель/endpoint |
| P0 | Нет общего денежного guard в серверном pipeline | api.py lifespan создаёт httpx без budget hooks; MCP connection создаёт отдельный клиент | Лимиты количества вызовов не задают долларовый предел | Минимальные hooks/общий атомарный счётчик по всем transport, reservations до сети, provider tariff/usage, stop $4.50; unknown cost сохранять резервом |
| P1 | MCP/API telemetry может ложно сообщать ok | tools.py execute: ранние returns schema_error/empty/provider error, finally использует прежний status | Возвращаемый результат и лог используют разные значения | Присваивать точный outcome до каждого return; тест на real adapter response с mock network и проверку лога, без изменения fallback |
| P1 | Нет полной корреляции и времён workflow | model.py UsageLogger, tools.py logger, api.py in-memory progress; MCP retry log отдельно | Нет общего session/run/case и persistent event stream | Использовать существующие LangChain callbacks/LangGraph events и logging, безопасные JSONL node/agent/tool start/end, counts/attempts/cached usage; не сохранять prompts и приватные рассуждения |
| P1 | UI сборка заблокирована registry | Два npm ci ETIMEDOUT разных tarball | Сеть npm | Восстановить доступ к registry, повторить lock-based npm ci/build; не заменять версии или frontend |
| P2 | Возможен лишний LLM overhead Supervisor/presenter | supervisor/agent.py planner затем extraction, repair, response.py presenter | Раздельные typed этапы | Сначала измерить per-role tokens/latency в live; при доказанном overhead сокращать передаваемый context и устранить только доказанно повторное извлечение, сохраняя runtime-валидацию |
| P2 | Накладные MCP подключения | client.py _runtime_attempt на каждом запросе connection → initialize → list_tools | Сессии и schema lookup не переиспользуются | Измерить долю времени handshake; только при существенной доле переиспользовать клиент/схемы через существующий lifespan, не расширяя allowlist и owned IDs |
| P2 | Документация лимитов расходится с кодом | AUTONOMOUS_PLANNING.md: 8 model calls, LLM 20s/API 240s; react.py: 6 (+финализация), api.py: 35/45s и 360s | Документы отстают от текущей реализации | После live измерений синхронизировать лимиты и различать ReAct, финализатор и полный пользовательский ход |

## По компонентам

- MCP/API: доступность, ошибки поставщиков, duplicate calls и скорость **не проверены**. Memo responses локален одной build_tools делегации; нет доказательств реальных лишних повторов.
- Промпты: дефектов, подтверждённых live, нет; правки промптов без измерений не рекомендуются.
- ReAct: стандартный create_agent и bounded middleware присутствуют; реальная остановка/финализация и tool choice не проверены.
- Supervisor: отдельное извлечение и repair видны по коду; корректность делегирования и отсутствие лишних специалистов в live неизвестны.
- StateGraph: независимые роли уже распараллеливаются Send; дополнительно распараллеливать зависящие от транспорта даты отелей нельзя без доказательств совместимости. evaluate фильтрует revision/round.
- Travel Engine: Decimal/basis, freshness, география, совместимость и partial feedback присутствуют; live-цены и полнота не проверены. Не отключать проверки для покупки.
- Память: ownership/revision/checkpointer есть; долговечность PostgreSQL в реальном окружении не доказана, тесты с отдельной БД skipped. После настройки проверить восстановление через публичный HTTP/UI, не прямую подмену state.
- UI/backend: startup и npm блокеры воспроизведены; browser E2E и сессии продукта не пройдены.

Новые агенты, MCP, инфраструктурные компоненты и большой рефакторинг не требуются для следующего измерения. Ни одна гипотеза об оптимизации не считается установленным live-дефектом.
