> Исторический снимок этапа 1. Этап 2: основная `.venv` дополнена MCP-клиентами; community MCP изолирован в `.mcp-venv`. LLM настройки не изменены. Результаты function calling и расход в LLM_EXPERIMENTS.md.

# Окружение и фактически выполненные проверки

25 октября 2026. Завершён этап 1; интеграционные сценарии A–F и LLM tool-calling ещё не запускались.

Исходный проект: README с названием Flinters, `.env`, `.gitignore`, `.idea`, локальные служебные каталоги, Git. Python-кода, pyproject, requirements и проектного venv не было. Применимых AGENTS.md в проекте и проверенных родительских каталогах не найдено. Исходные пользовательские файлы не удалялись; `.env`, LLM-настройки, `.idea` не менялись.

Shell использовал Python 3.13.7 из `/home/artur/projects/crpt_rd/.venv/bin/python3`. В том окружении уже были httpx 0.28.1, requests 2.28.1, openai 1.97.1, python-dotenv 1.1.1, pydantic 2.11.7; MCP SDK отсутствовал. Установка в чужой venv не выполнялась.

Создан `.venv` внутри Flinters: Python 3.13.7, httpx 0.28.1, python-dotenv 1.2.4, pydantic 2.14.1, mcp 1.30.0. Прямые зависимости заданы в pyproject.toml, установленный набор закреплён в requirements.lock.txt. `pip check` успешен. HTTPX достаточно для прямой проверки OpenAI-compatible протокола; дополнительный OpenAI SDK не нужен. Для сторонних локальных MCP потребуется отдельный аудит и, возможно, отдельное окружение; сейчас они не устанавливались.

| Проверка | Результат | Что НЕ доказывает |
|---|---|---|
| HTTPS GET публичных моделей OpenRouter | HTTP 200, 441 ms в сохранённом прогоне | Доступ ко всем travel providers |
| Настроенная модель найдена в каталоге | Да; metadata заявляет tools/tool_choice | Работоспособность tool calling |
| POST Chat Completions, один запрос, output cap 16 | HTTP 200, ответ точно OK, 726 ms | Responses API и многошаговый workflow |
| Usage по ответу провайдера | 9 input, 16 completion, 25 total; cost $0.00000872 | Универсальную цену будущих запросов |
| GitHub metadata/manifests пяти репозиториев | Отдельный JSON отчёт | Безопасность полного исходного кода и работающий MCP |
| Туристические REST и MCP tools | Не запускались по границе этапа | Нельзя утверждать наличие номеров, рейсов или событий Сочи |

В `.env` обнаружены именно `MODEL`, `TOKEN`, `BASE_URL`, все заполнены. Провайдер — `openrouter.ai`, base path `/api/v1`. Chat Completions подтверждён реальным запросом. [Документация OpenRouter](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request) также содержит Responses API; его совместимость с настроенной моделью в этом проекте не проверялась, второй запрос не выполнялся. Предварительная оценка по публичной цене — существенно меньше $0.001 для этого короткого smoke; фактическое значение взято из usage, не из предположения.

`.gitignore` дополнен: `.env.*` с исключением `.env.example`, `.venv`, IDE-конфиги, кэши, логи, private key файлы и raw reports. Уже существующая строка `.codex` сохранена. Секреты не копировались в примеры или отчёты. Подробности stdout/HTTP bodies платного запроса не сохраняются, исключения выводятся только по типу. Редиректы при авторизованном запросе отключены, host/path ограничены настроенным провайдером.

Повторение без генерации:

```bash
.venv/bin/python scripts/check_environment.py
```

Публичная инвентаризация репозиториев, без установки/исполнения их кода:

```bash
.venv/bin/python scripts/inspect_mcp_repositories.py
```

Повторение минимального LLM-запроса, с осознанным дополнительным расходом:

```bash
.venv/bin/python scripts/check_environment.py --llm-smoke
```

Первый прогон сохранён в `reports/environment_smoke.json`. Обычная проверка сохраняется отдельно в `reports/environment_inventory.json`, поэтому она не затирает свидетельство LLM smoke. Новый запуск с `--llm-smoke` обновляет smoke-отчёт.

После подтверждения пользователя появятся адаптеры, сценарии и одна команда всех разрешённых интеграционных тестов. MCP_TEST_RESULTS, API_COMPARISON, RECOMMENDED_STACK и ARCHITECTURE_PROPOSAL пока не создавались: иначе возникло бы впечатление, что измерения и финальный выбор уже сделаны. Текущие приоритеты и кандидаты перечислены в API_CATALOG.
