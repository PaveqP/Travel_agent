# Эксперименты с LLM

Настройки MODEL/TOKEN/BASE_URL не изменены. Подтверждён Chat Completions и native function calling. Responses API не тестировался. Модель получает очищенные снимки настоящих API-ответов с временем получения: это воспроизведение результатов, не выполнение новых внешних запросов при каждом tool call. Эти три прогона предшествуют нормализации Tutu; проверка объединения с Tutu приведена отдельно, если есть llm_tutu_update.json.

| Прогон | Эксперимент | Автопроверка | Вызванные инструменты |
|---|---|---|
| llm_experiments_baseline.json | selection | failed_or_partial | search_flights, get_weather |
| llm_experiments_baseline.json | two_sources | failed_or_partial | search_hotels, search_restaurants, search_restaurants |
| llm_experiments_baseline.json | weather | failed_or_partial | get_weather |
| llm_experiments_baseline.json | fallback | failed_or_partial | primary_places, fallback_places |
| llm_experiments_baseline.json | complex | failed_or_partial | get_trip_evidence |
| llm_experiments_structured.json | selection | passed | search_flights, get_weather |
| llm_experiments_structured.json | two_sources | failed_or_partial |  |
| llm_experiments_structured.json | weather | failed_or_partial |  |
| llm_experiments_structured.json | fallback | failed_or_partial |  |
| llm_experiments_structured.json | complex | failed_or_partial |  |
| llm_experiments.json | selection | passed | search_flights |
| llm_experiments.json | two_sources | failed_or_partial | search_hotels, search_restaurants |
| llm_experiments.json | weather | passed | get_weather |
| llm_experiments.json | fallback | passed | primary_places, fallback_places |
| llm_experiments.json | complex | passed | get_trip_evidence |

Сумма usage.cost и консервативного резерва неразобранного Tutu-запроса с исходным smoke: $0.0659956566; разрешено до $5. Для первого Tutu synthesis ответ не разобран, usage не сохранён: учтён верхний расчётный резерв $0.053398, не фактический счёт. Остальные стоимости — usage.cost.

Baseline: модель вызывала инструменты, но нарушала JSON-формат; были неподтверждённые утверждения. Structured auto: схема помогла формату, но 4/5 сценариев не вызвали необходимые инструменты; в weather модель написала «запросил» без вызова. Orchestrated: задана последовательность разрешённых tool calls, затем отдельный structured ответ; это не доказательство автономного выбора. 4/5 прошли формальные проверки. Two_sources выбрал отель без измеренного nearby snapshot и честно сообщил отсутствие; автоматическое восстановление не реализовано.
Ручная проверка выявила дефект даже у формально passed complex: модель назвала маршрут Адлер→Красная Поляна маршрутом из Сочи. Weather добавил сезонные предположения вне предоставленных фактов. Поэтому boolean-флаги и валидный JSON недостаточны: выпуск требует проверки географии, чисел и дат по ID источников. Формальный passed не равен готовности продукта. Ошибка primary_places в fallback искусственная и явно помечена simulated, резервные данные настоящие.

Финальный merge Tutu: {"status": "passed", "checks": {"flight_basis_correct": true, "total_unknown": true, "route_origin_correct": true, "forecast_horizon_correct": true, "missing_costs_reported": true, "reported_sums_match_python": true}, "answer": {"weather_covers_trip": false, "trip_total_rub": null, "route_origin": "Адлер", "missing_costs": ["restaurants", "local_transport", "activities", "lifts", "extra_fees"], "flight_party_total_rub": 14018.0, "answer": "Варианты: 1) 14018 + 8600 = 22618 RUB; 2) 19228 + 9000 = 28228 RUB; 3) 30146 + 53610 = 83756 RUB. Полная цена неизвестна."}, "usage": {"prompt_tokens": 7282, "completion_tokens": 2701, "total_tokens": 9983, "cost": 0.001416964, "is_byok": false, "prompt_tokens_details": {"cached_tokens": 7168, "cache_write_tokens": 0, "audio_tokens": 0, "video_tokens": 0}, "cost_details": {"upstream_inference_cost": 0.001416964, "upstream_inference_prompt_cost": 6.6464e-05, "upstream_inference_completions_cost": 0.0013505}, "completion_tokens_details": {"reasoning_tokens": 2539, "image_tokens": 0, "audio_tokens": 0}}, "actual_cost_usd": "0.001416964", "latency_ms": 22044, "mode": "Direct Python merge of real snapshots, structured LLM explanation; not autonomous tool choice", "manual_review": "Correct arithmetic and structured fields, but prose omits hotel names and fare explanations; not a finished itinerary. Do not treat formal pass as product readiness."}
