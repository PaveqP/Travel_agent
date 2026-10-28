# Live E2E: результаты подготовки и блокировки

Дата: 2026-10-28, 19:14–19:21 UTC (22:14–22:21 МСК); формирование отчёта: 2026-10-28T19:20:17.268953+00:00.
Исследуемый Git SHA: `f3fdcad0ab206a260304e685ab52815caf92826f`. Backend package version: `0.1.0`; frontend: `1.0.0`.

**Приложение с реальными настройками не запущено. Live E2E не выполнен: 0/5.**
Все пять кейсов blocked до отправки пользовательских сообщений. Это отчёт о фактическом preflight и статическом исследовании, а не подтверждение качества live-системы.

Источник требований: [ТЗ Островка](https://docs.ostrovok.tech/s/0ee4d8b2-ae50-4dda-a2b5-112fcdb5398d), открыт настоящим Playwright-браузером. После уточнения заказчик разрешил собственную декомпозицию в пять комплексных сценариев. Их сопоставление: [USE_CASES.md](USE_CASES.md).

Окружение: Linux, Python 3.13.7, Docker 29.1.3. Корневой `.env` отсутствует. MODEL/TOKEN/BASE_URL, настройки БД и ключи поставщиков отсутствуют также в процессе. Значения секретов не читались из других проектов. `.env` не создавался и не изменялся. Чужой PostgreSQL не использовался.

Проверено: Docker daemon доступен; backend startup завершился RuntimeError; HTTP health/config недоступны; Playwright доступен; Python suite и JS unit проходят. БД, LLM и MCP в live не проверены. Зависимости Python установлены по существующему lock через `uv pip install --python .venv/bin/python -r requirements.lock.txt`; код и версии не менялись. npm ci дважды завершился ETIMEDOUT; frontend не собран.

## Воспроизведение

1. В рабочем окружении предоставить существующую конфигурацию проекта: `.env` с MODEL, TOKEN, BASE_URL, TRAVEL_POSTGRES_PASSWORD и ключами нужных источников. Для запуска с хоста нужен TRAVEL_DATABASE_URL. Секреты в отчёты не копировать.
2. `uv pip install --python .venv/bin/python -r requirements.lock.txt`.
3. `.venv/bin/python -m unittest discover -s tests -v`; `node --test frontend/src/format.test.js`.
4. `docker compose up --build` — штатный полный запуск; UI на http://127.0.0.1:8000. Альтернатива: сборка frontend и `.venv/bin/uvicorn travel_agent.web:create_web_app --factory --host 127.0.0.1 --port 8000 --workers 1 --no-access-log` при существующей PostgreSQL.
5. Сначала установить единый guard и тарифы, описанные в [COST_REPORT.md](COST_REPORT.md). Штатный сервер сейчас денежный лимит не гарантирует.
6. Выполнить сценарии [USE_CASES.md](USE_CASES.md) последовательно в пяти новых пользовательских сессиях. Предпочтителен browser_e2e, при недоступности UI — backend_http_e2e; необходимы реальные LLM и источники. Текущие пустые conversation/mcp файлы означают отсутствие вызовов, а не успешную трассу.

[Preflight](PREFLIGHT.md), [архитектура](ARCHITECTURE.md), [сводка](SUMMARY.md), [рекомендации](RECOMMENDATIONS.md).
