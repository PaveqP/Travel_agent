# Live E2E: итог повторного прогона

Исследованный код приложения: `9c1836aaabfd47602f8195e46d213cb1c741da80`. Реальные настройки `.env`, OpenRouter, PostgreSQL и источники; интерфейс `backend_http_e2e` (frontend npm timeout). Live LLM/MCP проверены в 4/5 сценариях. Case 05 получил только HTTP-ответ о бюджетной блокировке до LLM; полный прогон всех пяти не завершён. Исходный blocked preflight сохранён в Git-коммите 9c1836a, ниже результаты повторного запуска.

| Case | Сценарий | Статус | Время | LLM calls | MCP/API calls | Стоимость |
|---|---|---|---:|---:|---:|---:|
| [case_01](<case_01/report.md>) | От размытого запроса к направлению | partial | 287.441s | 33 | 42 | $0.735180 |
| [case_02](<case_02/report.md>) | Подбор и объяснимое сравнение | partial | 259.676s | 26 | 31 | $0.747234 |
| [case_03](<case_03/report.md>) | Единый план, корзина и имитация покупки | failed | 220.837s | 26 | 33 | $0.714430 |
| [case_04](<case_04/report.md>) | Пересборка при изменении дат | partial | 639.206s | 60 | 81 | $2.271127 |
| [case_05](<case_05/report.md>) | Пересборка при уменьшении бюджета | blocked | 0.163s | 0 | 0 | $0.000000 |

Время — сумма ожидания полных HTTP-ответов и действий select/book; чтение/обдумывание тестировщиком между сообщениями исключено. Стоимость — консервативный учёт, включая неразрешённый биллинг и квоты API; это не точный счёт всех поставщиков.

Passed 0; partial 3; failed 1; blocked 1; not_run 0. Среднее время ответа 140.637s, медиана 110.255s по 10 сообщениям (select/book исключены). Самый медленный сценарий: case_04.

LLM calls 145; input 1228864, output 113902, всего 1342766; cached input 394112 (часть input, повторно не суммируется). Токены учтены только по вернувшемуся usage; для timeout неизвестны, не равны нулю. Provider-reported LLM **$0.1427329808**; общий учтённый расход/резервы **$4.4679709808**, pending **$0**, дополнительный неприкосновенный запас до $5 — $0.50.

## Реальные MCP/API business requests

| MCP/API | Вызовов | Успешных | Ошибок | Среднее время | Максимальное время |
|---|---:|---:|---:|---:|---:|
| 2gis | 59 | 52 | 7 | 2.563s | 28.421s |
| geoapify | 14 | 14 | 0 | 1.031s | 1.755s |
| openmeteo | 9 | 9 | 0 | 0.861s | 1.275s |
| opentripmap | 5 | 5 | 0 | 0.997s | 1.704s |
| tavily | 1 | 1 | 0 | 2.310s | 2.310s |
| timepad | 9 | 9 | 0 | 2.981s | 10.643s |
| travelpayouts | 4 | 3 | 1 | 0.951s | 1.295s |
| tutu | 86 | 85 | 1 | 1.936s | 9.984s |

Времена таблицы — network tool request, без MCP initialize/list. Полные логические MCP timings с handshake и retries есть в каждом mcp_calls.json. Предсетевые schema_error/forbidden/tool_limit не считаются фактически отправленными MCP tools/call; они отражены в trace отдельно. REST HTTP-успех может сопровождаться контрактной ошибкой adapter — это не доказательство готового travel result. Яндекс Расписания в этом прогоне не вызывался. Наличие зарегистрированного инструмента не считается проверкой его подключения.

Самое долгое выполнение узла: experience, 90.041s, case_01.

Самый долгий логический MCP: tutu/search_hotels, 37.336s, ok, case_04.

Наиболее частые предупреждения по завершениям делегаций (с учётом repair): agent_limit: 23, finalization_failed: 15, tool_limit: 7, weather_outside_forecast_horizon: 7, unverified_source_ids: 2, tutu:timeout: 2, tutu:schema_error: 1.

Главные подтверждённые проблемы: повторные уточнения уже заданных дат; потеря параметров в patch; недостроенный календарь при большом каталоге POI; ошибки presenter и перепутанные arrival/departure; timeout Tutu. Защита booking не пропускает пакет без обязательного горного дня. PostgreSQL выдержал restart, межпользовательский доступ возвращает 404. Подробности и границы измерений — в case reports, COST_REPORT.md и RECOMMENDATIONS.md.

Offline validation: `.venv/bin/python -m unittest discover -s tests -v` — 194 tests, OK, 8 skipped (17.095s); JS — 17/17 passed. Подробности: [offline_tests.txt](offline_tests.txt).
