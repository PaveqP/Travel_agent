# Исторический live E2E-прогон — 28 октября 2026

Это архив результатов прежней версии, не инструкция запуска и не приёмка текущего кода.
Актуальная проверка сдачи — в [SUBMISSION.md](../../SUBMISSION.md).
Сырые трассировки и промежуточные JSON убраны из текущего дерева; они доступны
в [истории Git](https://github.com/PaveqP/Travel_agent/tree/5876f5bc3e89d1a5a50cdeef4e49ba0c747af5d6/test%20MVP).
Итоговые отчёты сохранены, включая неуспешные сценарии.

Дата: 2026-10-28, с 19:24 UTC (22:24 МСК); завершение/формирование: 2026-10-28T20:01:56.475383+00:00.
Исследованный код приложения: `9c1836aaabfd47602f8195e46d213cb1c741da80`. Backend package `0.1.0`, frontend package `1.0.0`. Продуктовый код, промпты, модель, endpoints и валидация не изменены. Локальную пользовательскую правку `.gitignore` не включали в задачу.

Приложение действительно запущено с новым существующим `.env`: модель `deepseek/deepseek-v4.1-flash-1017`, OpenRouter, реальные ключи источников. Значения секретов не публикуются. Настроек PostgreSQL не было, поэтому использован **существующий** `scripts/serve_web.py --local-postgres`: он поднимает штатный Compose PostgreSQL 17, создаёт пароль только процесса и умеет восстановить его из контейнера при restart. `.env` не менялся. Новые сервисы и отдельный frontend не создавались.

Backend: FastAPI/LangGraph, autonomous=True, один worker, http://127.0.0.1:8000. `/health` HTTP 200 persistent=true, `/api/config` HTTP 200, Telegram не настроен. После backend restart история, constraints, revision, options, results и selected case_01 совпали полностью. Два перекрёстных запроса разных аккаунтов к чужой поездке вернули 404.

Frontend `npm ci --no-audit --no-fund --fetch-retries=0 --fetch-timeout=20000` завершился ETIMEDOUT registry.npmjs.org. Поэтому пользовательские запросы пяти сессий отправлялись через **публичный HTTP API**; live LLM/MCP работали только в cases 01–04, case 05 заблокирован бюджетом до первого inference, с реальной регистрацией аккаунтов и отдельными cookie/поездками. Прямых вызовов агентов/graph для запуска пользовательских сценариев и подмены TripState нет. Instrumentation оборачивает вызовы для наблюдения и бюджетирования, не меняет их результаты.

Backend после завершения измерений остановлен, чтобы исключить дальнейший расход. PostgreSQL и данные остаются в штатном volume; ledger сохранён без сброса.

## Артефакты

- [USE_CASES.md](USE_CASES.md): пять согласованных комплексных сценариев, покрытие трёх User Story и шести основных задач исходного ТЗ.
- [SUMMARY.md](SUMMARY.md): итоговые статусы, времена, токены, стоимость и MCP-метрики.
- [COST_REPORT.md](COST_REPORT.md): общий лимит, реальные usage.cost, консервативные резервы и тарифы.
- [PREFLIGHT.md](PREFLIGHT.md), [ARCHITECTURE.md](ARCHITECTURE.md), [RECOMMENDATIONS.md](RECOMMENDATIONS.md).
- В case_01…case_05: полный безопасный диалог, safe trace и фактические MCP/API вызовы. Screenshots не создавались: метод backend_http_e2e.

Сырые состояния, cookie, тестовые login credentials и серверный log остаются только локально в `/tmp/flinters-live-e2e/`/`/tmp/flinters-e2e-server.log`; в Git включаются только отфильтрованные события, публичные цены, синтетические сообщения и метаданные. Старый blocked preflight остаётся в истории коммита 9c1836a.

## Воспроизведение

1. Установить зависимости по существующему lock: `uv pip install --python .venv/bin/python -r requirements.lock.txt`. Нужны существующие MODEL/TOKEN/BASE_URL и API keys в `.env`, Docker и доступ к сети.
2. Прочитать COST_REPORT.md, перепроверить актуальные тарифы. В этом прогоне используется global $4.50 soft guard с запасом до $5. Каталоги тарифов не являются платным inference.
3. `.venv/bin/python -u scripts/live_e2e_server.py` запускает **штатный** serve_web с budget/trace hooks. Путь приватного ledger фиксирован `/tmp/flinters-live-e2e`; при его наличии новый прогон отклоняется, расходы не сбрасываются. `--resume-budget` продолжает существующий ledger, сохраняет расходы и консервативно списывает незавершённые резервы. Для нового независимого бюджета нужен отдельный явно авторизованный запуск, а не удаление ledger.
4. Для каждого номера последовательно: `.venv/bin/python -u scripts/live_e2e_client.py --case 01 --initial` (затем 02…05). Клиент регистрирует синтетический аккаунт/новую поездку и отправляет запрос из USE_CASES.md. Внутри кейса продолжать `--message '...'` по фактическим ответам. Конкретные сообщения данного прогона сохранены в conversation.json, включая ошибки и диагностические переформулировки.
5. В case 03 после выдачи выполнялись `--select`, затем `--book` с явным confirm только симуляции. Для кейсов 04/05 отправлялись изменения из USE_CASES.md. При недостающих вводных отвечать в рамках сценария, не заменять требования.
6. Offline: `.venv/bin/python -m unittest discover -s tests -v`; `node --test frontend/src/format.test.js`. Не запускать run_all.py или внутренний smoke вместо пользовательского E2E.

Каждый будущий live replay снова расходует бюджет и может дать другие цены/наличие. Автоматическая реплика всего диалога не предусмотрена: исполнитель читает ответы и адаптирует следующие сообщения как пользователь.

Offline validation: `.venv/bin/python -m unittest discover -s tests -v` — 194 tests, OK, 8 skipped (17.095s); JS — 17/17 passed. Подробности: [исторический лог offline-проверок](https://github.com/PaveqP/Travel_agent/blob/5876f5bc3e89d1a5a50cdeef4e49ba0c747af5d6/test%20MVP/offline_tests.txt).
