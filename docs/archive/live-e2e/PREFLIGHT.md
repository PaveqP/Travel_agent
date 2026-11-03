# Повторный preflight, 2026-10-28

Исходный запуск без конфигурации зафиксирован в коммите 9c1836a. После добавления переменных пользователем выполнены новые проверки. Секреты и .env не менялись.

| Проверка | Факт |
|---|---|
| Ветка / код | main, 9c1836aaabfd47602f8195e46d213cb1c741da80; пользовательская .gitignore оставлена отдельно |
| LLM | MODEL deepseek/deepseek-v4.1-flash-1017, BASE_URL host openrouter.ai; TOKEN настроен |
| Бесплатная метаинформация LLM | GET models/endpoints/key: HTTP 200; тарифы и limit metadata доступны, limit ключа null |
| База | TRAVEL_DATABASE_URL/password отсутствовали; существующий serve_web --local-postgres поднял штатный postgres:17-alpine и сохранил пароль только в процессе/контейнере |
| Backend | FastAPI startup complete, loopback:8000, autonomous=True, один worker |
| HTTP | /health 200, persistent=true; /api/config 200, telegram_configured=false |
| Регистрация / поездки | Пять отдельных синтетических аккаунтов, cookie и trip ID через публичный API, без прямой записи state |
| Frontend | npm ci --fetch-retries=0 --fetch-timeout=20000: ETIMEDOUT source-map-js tarball; UI не запущен, выбран backend_http_e2e |
| Реальная LLM | Подтверждённые chat/completions/usage в cases 01–04; case 05 заблокирован до сети |
| Реальные источники | Tutu MCP, 2ГИС MCP; Geoapify, Open-Meteo, Timepad, OpenTripMap, Travelpayouts и Tavily REST — фактические вызовы есть в trace/mcp_calls |
| Не проверено | Яндекс Расписания не требовался выбранными агентами; UI, Telegram и реальная покупка не тестировались |
| Бронирование | Только локальный simulated endpoint; case 03 select HTTP 200, bookings HTTP 409 из-за отсутствующего горного дня, реальные места/оплата не затрагивались |
| Restart / память | Case 01 после остановки/нового backend: revision, constraints, messages, options, results, selected совпали полностью |
| Владение | Два перекрёстных запроса разных пользователей к чужим trip ID вернули 404 |
| Бюджет | Единый atomic guard с резервами in-flight, история сохранена при restart. Case 05 required reserve $0.050716, available $0.0320290192: запрос не отправлен |
| Завершение | Backend остановлен после измерений; PostgreSQL volume оставлен, ledger не удалён. Новых платных операций нет |

Старые сообщения password/Pool warnings относятся к первым секундам старта новой БД; затем pool и приложение поднялись. Ошибки не скрывались повторным платным preflight: первый настоящий inference включён в case 01.

Результаты offline-проверок — [исторический лог offline-проверок](https://github.com/PaveqP/Travel_agent/blob/5876f5bc3e89d1a5a50cdeef4e49ba0c747af5d6/test%20MVP/offline_tests.txt). Полный тестовый лог, сырой state, cookie и credentials остаются локальными и не включены в Git. Пять бюджетных unittest проверяют общий pending, списание unknown billing, soft limit и redaction.
