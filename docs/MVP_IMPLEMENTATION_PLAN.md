# Минимальный план backend MVP

Статус: анализ и соглашения, 26.10.2026. Код Travel Agent на этом этапе не создаётся.

## Основания и устройство эталона

Найден точный путь: `/home/artur/projects/crpt-llm/crpt_llm_utils/crpt_llm_utils/openai_sdk/langgraph_multi_agent`. Далее `REF/` означает эту директорию. Рядом есть другие копии; источником выводов является именно указанный путь. Анализ статический: код, схемы, промпты, графы и тесты; запуск корпоративных сервисов и подтверждение работоспособности всего эталона не выполнялись.

Это библиотека графов, а не готовый supervisor swarm. `agents/` содержит conversational, rag, rag_react, deep_research, link_processor, bfr_validation, file_processing и transcribation. Обычно агент разделён на `agent.py`, `state.py`, `graph/`, `nodes/`, иногда `schemas.py`, `tools/`, `config.py`; рядом находятся `core/`, `prompts/`, `external/`, `callbacks/`, `pipelines/`, `test/` и демонстрационные данные.

`BaseAgent` создаёт workflow, добавляет callback и вызывает `ainvoke`; `AgentFactory` передаёт зависимости. Узлы — преимущественно async-функции, зависимости связываются через `functools.partial`. Графы явно задают edges и conditional edges. ReAct реализован вручную через `bind_tools`, `ToolNode`, сообщения и маршрутизатор; deep research добавляет observation, compaction, findings и finalize. Отдельного думающего Supervisor и MCP-изоляции в этом пакете нет. `pipelines/link_conversational_pipeline.py:main` показывает последовательную передачу результата между агентами; conversational/transcribation также используют context processor как вложенный workflow.

`BaseAgentState` — `TypedDict`; ReAct расширяет его `add_messages`, `RemainingSteps`, рабочей/пользовательской историей и хранилищем источников. В рассмотренных сборщиках `compile()` вызывается без checkpointer; историю примеры передают вручную. Это не постоянная память. `schemas.py` описывают Pydantic-входы и structured output, а `ToolArtifact` в deep research — dataclass, не Pydantic.

LLM: `core/llm_client.py:LLMClient` оборачивает `ChatOpenAI`, использует `bind_tools`, `with_structured_output`, async-вызовы и env `CONVERSATIONAL_OPENAI_*`. `ReasoningChatOpenAI` переопределяет внутренний `_create_chat_result` для reasoning metadata. `run_agent.py` собирает внешние клиенты и конфигурацию; `core/config_resolver.py` допускает fallback невалидных значений. Внешние источники внедряются через `DocumentProvider`, `LinkProcessorRegistry`, `GitLabAgentClient`, `AbbreviationsServiceClient`, а не автоматически обнаруживаются как tools.

Ошибки обрабатываются неоднородно: `core/llm_retry.py:execute_with_retry` использует Tenacity и timeout; deep research передаёт tool errors в `ToolNode(handle_tool_errors=...)`, старый rag_react ловит общий `Exception`. Есть `GraphRecursionError` и ограничения контекста. Асинхронность — `ainvoke`, async HTTP, bounded concurrency в observation/context processor. Логирование — стандартный logging, event consumer (его базовая реализация печатает stdout), OTel callback длительности tools. Тесты — pytest, async mocks, проверки маршрутизации, сообщений, токенов и mock workflow; benchmark-скрипты отдельно.

## Что перенимаем

| Паттерн | Конкретный исходник | Применение в MVP |
|---|---|---|
| Явная сборка графа, узлы-функции, внедрение зависимостей | `REF/agents/rag_react/graph/workflow.py:create_rag_react_graph_workflow`; `REF/agents/rag/graph/workflow.py:_route_after_reflection` | Один внешний `graph.py`, проверяемые переходы, без фабрики классов |
| Отдельное состояние и reducers | `REF/agents/rag_react/state.py:RagReactState` | `TripState`, `add_messages`; Pydantic на границах, не вместо reducers |
| Отдельные Markdown-промпты | `REF/prompts/__init__.py:PromptManager.get_prompt` | Одна директория, простое UTF-8 чтение; класс менеджера не нужен |
| Явный набор tools на агент | `REF/agents/rag_react/agent.py:RagReactAgent._create_workflow`; `REF/agents/deep_research/agent.py:DeepResearchAgent._create_workflow` | Три отдельных набора; дополнительная проверка прав при исполнении |
| Типизированные tool args и скрытый runtime-контекст | `REF/agents/deep_research/schemas.py:LoadLinksInput`, `ReadDocumentInput`, `RagSearchInput` | Аргументы валидируются; клиенты, роль и принадлежность поездке задаёт сервер, не LLM |
| Краткий content отдельно от полного artifact | `REF/agents/deep_research/tools/base.py:BaseRagTool`, `ToolArtifact`; `REF/agents/deep_research/nodes/tools_node.py:_collect_documents_into_store` | Компактный ответ LLM и нормализованные evidence для Python; без наследования BaseRagTool |
| Ограниченная автономность и явное завершение | `REF/agents/rag_react/agent.py:do_task`; `REF/agents/deep_research/graph/workflow.py:_agent_routing_condition` | Лимиты LLM/tools/делегаций/deadline, типизированный partial при исчерпании |
| Разделение добычи данных и итогового ответа | `REF/agents/deep_research/graph/workflow.py:create_deep_research_graph_workflow`; `REF/agents/deep_research/schemas.py:ResearchFinding`, `EvidenceRef` | Сначала tools/evidence, затем structured результат; source IDs проверяет Python |
| Тестирование графа без настоящей LLM | `REF/test/deep_research/test_dr_routing.py`; `REF/test/deep_research/test_dr_workflow_smoke.py`; `REF/test/test_llm_client_tools.py` | Mock-модель и реальные переходы графа; сохраняем текущий unittest вместо добавления pytest |

## Что не копируем и совместимость версий

- `BaseAgent`/`AgentFactory`, десятки папок `nodes/graph/utils`, `LLMClient`/`MessageFormatter` и собственный token framework из `core/`: обслуживают большую корпоративную библиотеку. Для четырёх ролей достаточно функций и стандартных SDK.
- RAG/Qdrant, reranker, reflection, OCR, multimodal, корпоративные аббревиатуры, Jira/Confluence/GitLab, BFR validation, ML benchmarks: не нужны текущему продукту. `setup.py` эталона включает для них transformers, torch, sentence-transformers, qdrant-client, atlassian API, splitters; эти зависимости не переносим.
- `core/decorators.py:validate_node_token_limit` мутирует state служебными полями; не копируем кастомный декоратор. Tools эталона — классы `BaseTool`, применение `@tool` здесь будет нашим упрощением, а не найденным паттерном.
- `DeepResearchAgent._build_tools_section` собирает длинные инструкции из Python-полей tools; у нас системные инструкции только в `.md`, в Python остаются короткие описания входных контрактов. Think/ResearchComplete tool не нужен для делегации Supervisor.
- `core/llm_client.py:ReasoningChatOpenAI` зависит от private API; Qwen/vLLM `extra_body` в `agents/rag_react/nodes/agent_node.py` специфичен для исходной модели. Используем публичный `ChatOpenAI` с существующими `MODEL/TOKEN/BASE_URL`; не переносим параметры thinking и не меняем модель молча.
- Не переносим широкий перехват ошибок, возврат сырого `str(exc)` модели, молчаливые config fallback и подробные debug dumps. Также не переносим общий mutable `last_response_metrics` объекта агента на параллельные запросы.
- Есть конкретные следы устаревания: `PromptManager.get_prompts_from_dir` определён дважды; `pipelines/link_conversational_pipeline.py` вызывает отсутствующий `AgentFactory.create_link_agent` и импортирует старые loaders/utils, где в данном дереве остались только pycache. Этот пример не является готовым рабочим pipeline.

Manifest `crpt_llm_utils/setup.py` закрепляет `langchain==0.3.27`, `langchain-core==0.3.75`, `langgraph==0.2.76`, `langchain-openai==0.3.11`, `pydantic==2.11.2`, `openai==1.71.0`, `tenacity==9.1.2`. Это объявленные версии, не доказательство актуальности установленного окружения. FastAPI/MCP в агентном пакете не образуют backend, аналогичный нашему.

Для нового кода ориентируемся на согласованный LangChain/LangGraph 1.x. `StateGraph` и разделение состояния сохраняем. `create_react_agent` в просмотренном коде не используется; для нашего стандартного ReAct выбираем `langchain.agents.create_agent`, поскольку прежний prebuilt deprecated: [официальная миграция](https://docs.langchain.com/oss/python/migrate/langgraph-v1). Совместимость всех деталей эталона с 1.x не утверждаем без запуска. Точные версии нового набора закрепим после resolution, `pip check` и offline smoke; сейчас ничего не устанавливаем.

## Что уже есть в Flinters

Изучены `RECOMMENDED_STACK.md`, `API_COMPARISON.md`, `MCP_TEST_RESULTS.md`, `ARCHITECTURE_PROPOSAL.md`, `LLM_EXPERIMENTS.md`, исполняемые `integrations/`, исследовательские `scripts/` и `tests/test_research.py`. Предложение в старом `ARCHITECTURE_PROPOSAL.md` начать без мультиагентности заменено текущим требованием четырёх ролей; принципы provenance, бюджета и безопасности сохраняются. Старые документы не перезаписываем.

| Источник кода | Переиспользование и граница |
|---|---|
| `integrations/schemas/models.py` | `Money`, `Coordinates`, `Provenance`, `Stay`, `Flight`, `Route`, `Activity`, `SourceResult`, `BudgetLine`, `calculate_budget`; новые контракты импортируют их, не дублируют |
| `integrations/mcp/client.py:connection`, `call`, `ALLOWED` | Проверенные MCP transport/auth/timeout/JSON Schema и deny-before-network. Сейчас allowlist общий для provider, не для роли; этого недостаточно для агентов |
| `integrations/providers/yandex_rasp.py`, `travelpayouts.py` | REST endpoints и преобразование параметров транспорта; полезное разрешение станций `train,suburban` — `scripts/run_followups.py:yandex` |
| `integrations/providers/geoapify.py`, `openmeteo.py`, `timepad.py`, `opentripmap.py` | REST-контракты Experience; Geoapify не используем для отельной выдачи Stay |
| `scripts/run_tutu.py`, `run_tutu_followup.py`, `run_mcp.py` | Проверенные формы запросов Tutu/2GIS; не импортировать сценарии в сервер |
| `scripts/normalize_tutu.py:build`, `normalize_results.py:stamp/build` | Правила нормализации, basis и исходного времени получения; snapshots — fixtures, не новый live поиск |
| `integrations/outcomes.py:payload/outcome` | Разбор MCP content и различение HTTP/MCP успеха от бизнес-исхода |
| `tests/test_research.py` | Сохранить регрессии Decimal, неизвестных расходов, redaction и запрета booking до сети |

В текущем `pyproject.toml` Python >=3.11 и пять прямых зависимостей: httpx, python-dotenv, pydantic, mcp, jsonschema. В lock — MCP 1.30.0, Pydantic 2.14.1; LangGraph/LangChain ещё не заявлены. Community MCP изолирован в `.mcp-venv`, не нужен backend. LLM-скрипты используют HTTPX Chat Completions с `MODEL/TOKEN/BASE_URL`; native tools проверялись, Responses API — нет. Сами секреты в документацию не переносим.

Важные ограничения: `integrations/core.py` при импорте читает `.env`, отключает logging глобально, хранит `RESULTS` и пишет reports; `providers/*.py:run()` используют фиксированные сценарии. Прямое включение этого пути в API не подходит. На этапе реализации добавляем в существующие provider-модули параметризованные async-функции с переданным клиентом/конфигом и чистым результатом, сохраняя исследовательские entrypoints и отчёты. Потребуется локально убрать import-time зависимость серверного пути от research core; только целевой совместимый change с regression-тестами, без общего рефакторинга. Для MCP аналогично выделяем исполняемый вызов без записи reports и сохраняем нынешний `call()` как исследовательский entrypoint. Не дублируем параллельную библиотеку адаптеров.

Из результатов стенда: Tutu поиск работает, hotel details давал timeout; Яндекс полезен для электричек при пустом Tutu; Travelpayouts — cached цены; прогноз Open-Meteo ограничен собственными датами. LiteAPI не является разрешённым резервом Stay. Доступность из исторических снимков не гарантирует текущую. В LLM-экспериментах structured output подавлял необходимые calls, а формальный passed пропускал подмену Адлера центром Сочи. Поэтому факт выполнения tools и точность entities проверяются отдельно от JSON.

## Минимальная структура (пока только предложение)

```text
travel_agent/
  __init__.py
  api.py           # FastAPI endpoints, lifespan, checkpointer
  config.py        # env → валидированная конфигурация
  schemas.py       # ограничения поездки, решения, результаты, itinerary
  state.py         # TripState
  graph.py         # Supervisor, маршрутизация, проверки переходов
  agents.py        # сборка трёх специалистов, чтение prompts, LLM config
  tools.py         # @tool, отдельные allowlists, связывание адаптеров
  engine.py        # budget, география, расписание, invalidation, mock booking
  prompts/
    supervisor.md
    transport.md
    stays.md
    experience.md
integrations/      # существующие клиенты и модели, совместимые дополнения
tests/             # существующие и новые offline-тесты
scripts/           # исследовательские entrypoints остаются
```

Не создавать пустые модули заранее. `tools.py` делить по доменам только при реальном росте. Клиенты и граф создавать при старте, без глобального mutable state запроса. Промпты читать через `Path(__file__).parent / 'prompts'`, включить `.md` в package data; без собственного PromptManager и шаблонизатора. Динамические даты/ограничения передавать как данные контекста. FastAPI API: отправка сообщения в поездку, чтение состояния, изменение ограничений и локальная booking simulation; не отдельные сервисы.

## Supervisor, специалисты и StateGraph

Supervisor — отдельная LLM-роль с `supervisor.md`, без внешних tools. Возвращает Pydantic `SupervisorDecision`: действие `clarify | transport | stays | experience | compose`, задача специалисту, уточнения и предлагаемый patch ограничений. Python проверяет patch и допустимость действия. Это думающий планировщик, а не keyword router; исполнение разрешает граф.

Три специалиста создаются через `create_agent(model=..., tools=..., system_prompt=...)`, каждый с собственным prompt и набором инструментов. Используем стандартные лимиты LLM/tools из [middleware LangChain](https://docs.langchain.com/oss/python/langchain/middleware/built-in), внешний deadline и общий бюджет поездки. Стартовый предел на одну делегацию: 6 вызовов модели, 8 tool calls; не более 6 делегаций на пользовательский turn. Значения конфигурируемы, но не управляются LLM. Таймаут или исчерпание дают `partial` с сохранёнными evidence; никакого бесконечного самоповтора.

После ReAct отдельный вызов той же роли без поисковых tools формирует типизированный результат: status, candidate IDs, source IDs, warnings, недостающие данные. Это не пятый агент. Цены/координаты/даты берутся Python из артефактов, не из пересказа модели. Если tool не был выполнен, факт не считается найденным. Пустой поиск и ошибка не превращаются в выдуманные альтернативы.

Внешний поток:

```text
START → validate_input/invalidate → supervisor
supervisor → clarify → END
supervisor → transport | stays | experience → validate_result → supervisor
supervisor → engine → supervisor_finalize → validate_answer → END
```

`supervisor_finalize` использует ту же роль и prompt в режиме объяснения готового itinerary. Не имеет внешних tools. Python разрешает compose только после выполнения необходимых задач либо явного учёта их ошибок/пропусков. Проверка финального ответа сверяет ссылки и утверждения с ID/evidence; неподтверждённые числовые поля не публикуются. Уточнение завершается checkpoint, продолжение приходит новым сообщением.

Специалистов сначала вызываем последовательно: отель может быть нужен до nearby-поиска. Задачи передаются как ограниченный контекст, а назад приходят только проверенные результаты. Произвольных handoff между специалистами нет. Повторная задача разрешается только при новых ограничениях/аргументах или конкретной незакрытой потребности и в пределах бюджета.

`TripState`: пользовательские messages (`add_messages`), `TripConstraints`, revision, текущая задача/решение, transport/stays/experience results, evidence по ID, выбранные IDs, itinerary/budget, warnings, счётчики текущего turn и simulated bookings. Рабочая ReAct-история локальна делегации и не смешивается с историей других специалистов. Узлы возвращают updates; ограничения и результаты заменяются по revision. Для текущего последовательного графа custom merge reducers не нужны. Клиенты, секреты, сырые ответы и невалидированные решения в checkpoint не попадают.

## Отдельные allowlists

| Роль | Инструменты MVP |
|---|---|
| Supervisor | Только внутреннее решение о делегации; никаких внешних инструментов |
| Transport | Tutu `search_avia`, `search_rail`, `search_etrain`, transport-specific details; REST Яндекс/Travelpayouts; Tavily Search/Extract |
| Stay | Tutu `search_hotels`, hotel-specific details; Tavily Search/Extract |
| Experience | 2GIS `search_places`, `geocode_address`, `build_route`, `calculate_distance_matrix`; REST Geoapify/Open-Meteo/Timepad/OpenTripMap; Tavily Search/Extract |

Для Tutu транспорт и отели — логические группы одного `tutu` endpoint, не два обнаруженных сервера. `get_offer_details` публикуем как отдельные узкие tools: hotel фиксирует `product_type='hotels'`; transport принимает только проверенные транспортные типы по сохранённой схеме. Opaque ID/ref берём из server-side evidence текущей поездки, проверяем роль, тип, revision и параметры поиска. LLM не выбирает provider/endpoint/product_type свободной строкой. Запрет работает до сети, включая прямой вызов функции мимо графа.

Схемы уже есть в `reports/tutu_mcp_schema.json` и `reports/2gis_mcp_schema.json`; на этапе подключения проверяем только нужные контракты. Объявленные `search_bus`/`search_multitransport` не входят в нынешний `ALLOWED` и не подтверждены вызовами стенда; добавлять лишь при нужном сценарии и отдельном контрактном тесте. Checkout/passenger, произвольные resource readers и финансовые методы не разрешать. Инструкции провайдера использовать при разработке адаптера, не как system prompt агента. Python allowlist и runtime guards важнее MCP annotations.

## Tavily, ошибки и наблюдаемость

Минимально — два async REST-вызова через уже используемый HTTPX, опубликованные как `@tool`: [Search](https://docs.tavily.com/documentation/api-reference/endpoint/search) (`POST /search`) и [Extract](https://docs.tavily.com/documentation/api-reference/endpoint/extract) (`POST /extract`). Отдельные Tavily SDK, MCP-сервер и adapter-framework не нужны. Новый `TAVILY_API_KEY` добавляется только как имя в примере конфигурации на этапе реализации; наличие доступа сейчас не подтверждено.

Search ограничиваем пятью результатами, без generated answer и полного raw content; Extract — до трёх выбранных публичных HTTPS URL из результатов текущего поиска, без credentials и локальных адресов. Ограничиваем объём текста, deadline и число вызовов; сохраняем URL/время/источник. Используем для контекста и ссылок, не для подтверждения тарифа/наличия. При отсутствии ключа возвращаем `missing_key`, не подменяем успешный поиск заглушкой.

Адаптеры нормализуют ожидаемые сетевые и schema ошибки, проверяют и HTTP, и business outcome. Retry безопасных чтений — максимум две попытки в одном deadline; 401/403 и невалидный ввод не повторять. Не умножать retry адаптера на retry middleware. Ошибки программирования остаются видимыми; в LLM возвращается безопасный код, не полный exception. Логи: request/thread ID, роль, имя tool/provider, duration, status, usage; без prompts, PII и токенов. OTel/LangSmith не обязательны для MVP.

## Travel Engine, память, пересборка и simulation

`engine.py` — обычные функции. Проверяет географию Большого Сочи, даты/timezone, стыковки, длительности и доступность evidence; строит простой план по дням из проверенных кандидатов, считает бюджет через существующий `calculate_budget`. Количество для `person/ticket` задаётся явно; `party/room_stay` не умножаем повторно. Смена валюты требует датированного курса; первый MVP может ограничиться RUB. Неполный бюджет содержит missing и `confirmed_total=null`. Сам `calculate_budget` не проверяет basis/freshness: эти проверки добавляются перед его вызовом.

Память MVP — ограничения, выбранные варианты и evidence в checkpoint внешнего графа по server-side `thread_id`. Для локального однопроцессного демо — `InMemorySaver`; потеря данных при перезапуске явно допустима. Если требуется восстановление — `AsyncPostgresSaver` и PostgreSQL, без ORM/собственной checkpoint-таблицы: [механизм persistence](https://docs.langchain.com/oss/python/langgraph/persistence). Междиалоговые профили и векторная память пока не нужны. Доступ к thread проверяется по владельцу; для одной поездки сериализуем изменения и проверяем ожидаемую revision.

Пересборка: валидированный patch повышает revision. Даты/гости инвалидируют тарифы и availability, даты также расписания, события и прогноз; смена отеля — nearby POI/маршруты; бюджет — выбор и расчёт, с повторным поиском только при недостатке вариантов. Статические данные можно сохранить в пределах freshness. Результат старой revision не принимается. Старые сообщения не считаются доказательством актуальной цены; предыдущий вариант сохраняется для сравнения, но помечается устаревшим. Это обычный новый run графа, не replay внешних вызовов из старого checkpoint.

Booking simulation — детерминированная функция Python для выбранного варианта/revision: локальный ID, `simulated=true`, отдельный статус, явное отсутствие реального резерва/оплаты. Повтор с тем же idempotency key возвращает ту же запись. Никакого checkout, передачи пассажирских данных или контактов поставщику, включая LiteAPI sandbox из старого стенда.

## Минимальные зависимости и этапы

Сохраняем текущие `httpx`, `python-dotenv`, `pydantic`, `mcp`, `jsonschema`. Добавляем `langgraph`, `langchain`, `langchain-core` (прямые импорты сообщений/tools), `langchain-openai`, `fastapi`, `uvicorn`. `openai` придёт транзитивно; отдельный клиент поверх него не пишем. `pydantic-settings`, `langchain-mcp-adapters`, Tavily SDK, Tenacity и pytest специально не добавляем. Для постоянного хранения отдельно `langgraph-checkpoint-postgres` и требуемый им async PostgreSQL driver. Проверить совместимость существующих Starlette/MCP с FastAPI, обновлять основной lock согласованно; community lock не смешивать.

| Этап | Работа | Проверяемый результат |
|---|---|---|
| 1. Контракты и зависимости | Минимальный пакет, конфиг, TripConstraints/решения/results, четыре `.md`; согласовать версии | `pip check`, импорт/сборка пакета с prompts, невалидные даты/гости отклоняются; текущие 12 тестов проходят |
| 2. Безопасные tools | Совместимая параметризация существующих адаптеров, отдельные allowlists, Tavily | Offline fixtures проходят; чужие tools, неверный Tutu product/ID и checkout блокируются до сети; серверный путь не пишет research reports |
| 3. Оркестрация | Думающий Supervisor, три ReAct-специалиста, StateGraph и лимиты | Mock LLM проходит уточнение → делегацию → результаты → завершение; повторный цикл останавливается; отсутствие tools не выдаётся за найденный факт |
| 4. Детерминированный план | Engine, нормализация evidence, itinerary, финальная проверка | Нет повторного умножения цены; неизвестное не ноль; Адлер не переименован в Сочи; прогноз за пределами дат помечен; JSON success не заменяет фактологические проверки |
| 5. API и память | FastAPI, checkpoint, revision/invalidation, simulation | Два turn одной поездки связаны; чужой thread недоступен; смена дат сбрасывает зависимые данные; старая revision отвергается; simulation идемпотентна и не вызывает сеть |
| 6. Сквозная проверка | Offline API+graph тесты, затем отдельный ограниченный live smoke | Сценарии «море+горы», отель+nearby, смена дат/бюджета, timeout/no_availability, injection; отчёт о реальных вызовах, расходе и неподтверждённых компонентах |

На этапе анализа выполнен `.venv/bin/python -m unittest discover -s tests -v`: 12/12 успешно, без внешних API/LLM. Не запускались обновление reports, MCP discovery, эталонные корпоративные графы или установка пакетов. Изменения этого этапа ограничены корневым `AGENTS.md` и данным планом.
