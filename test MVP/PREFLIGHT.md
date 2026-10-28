# Подтверждённые проверки

| Проверка | Результат | Доказательство / команда |
|---|---|---|
| Git | main; исходный SHA f3fdcad0ab206a260304e685ab52815caf92826f | git branch --show-current; git rev-parse HEAD |
| Рабочее дерево до задачи | Только существовавшая .playwright-mcp/ untracked | Не добавлять её в коммит |
| Исходное ТЗ | Открылось через Playwright, название «О!дин запрос» | Web open дал Internal Error; browser_navigate + document.body.innerText успешны |
| Конфигурация | .env отсутствует; обязательные переменные отсутствуют | Path('.env').is_file(); travel_agent.config.environment(), вывод только configured/missing |
| Compose | Не может интерполировать конфигурацию | docker compose ps: required variable TRAVEL_POSTGRES_PASSWORD is missing a value |
| Docker daemon | Доступен, 29.1.3 | docker info; сервисы этого проекта не запущены |
| Python зависимости до подготовки | Не установлены | dotenv/httpx/pydantic import errors; pip отсутствовал в .venv |
| Python зависимости после подготовки | Установлены по lock | uv pip install --python .venv/bin/python -r requirements.lock.txt; exit 0 |
| Реальный backend startup | Exit 1 | uvicorn travel_agent.web:create_web_app --factory ...; RuntimeError: Set TRAVEL_DATABASE_URL to the project's PostgreSQL database before starting the web application |
| HTTP | /health и /api/config ConnectError | httpx.get на 127.0.0.1:8000, timeout 3s, без retry |
| Frontend установка | Не завершена | npm ci: ETIMEDOUT source-map-js tarball; повтор с fetch-retries=0/fetch-timeout=20000: ETIMEDOUT update-browserslist-db tarball |
| UI | Не запущен | Playwright browser_navigate http://127.0.0.1:8000/ → net::ERR_CONNECTION_REFUSED; нет frontend/dist |
| LLM | Не проверен | Нет MODEL/TOKEN/BASE_URL; платных запросов 0 |
| MCP/API | Не проверены | Без тарификации и нужных ключей автономный live не запускался |
| БД и сохранение пользовательского состояния | Live не проверены | Нет TRAVEL_DATABASE_URL и пароля Compose; чужая БД не использовалась |
| Python offline | 189 tests, OK, skipped=8 | .venv/bin/python -m unittest discover -s tests -v; 24.608s после установки зависимостей |
| JS offline | 17/17 passed | node --test frontend/src/format.test.js |

Первый Python-прогон до установки зависимостей завершился 15 import errors и 3 failures — ошибка среды. После восстановления зависимостей suite зелёный. Пропуски — условные integration/test prerequisites; см. [offline_tests.txt](offline_tests.txt). Mock/fixture проверки не засчитываются как live. Код продукта, промпты, модель, endpoints, валидация и файлы конфигурации не менялись. Минимальных технических исправлений кода не потребовалось. Установка зависимостей — локальная подготовка среды.
