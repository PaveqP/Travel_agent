# Case 04: Пересборка при изменении дат

Статус: **partial**. Метод: `backend_http_e2e`. Сессия: `2d769425-db01-4bdc-9195-7560c633c988`. Без fixtures; фактически выполненные LLM/MCP/API вызовы перечислены ниже. Case 05 остановлен до первого внешнего вызова. UI недоступен из-за npm ETIMEDOUT.

## Диалог

### Ход 1

Отправлен: 2026-10-28T19:44:24.223142+00:00; полный ответ: 2026-10-28T19:49:02.781874+00:00; 278.546s, HTTP 200. Token streaming отсутствует; время первого токена N/A.

Пользователь:

Мы вдвоём из Москвы, хотим в Сочи 16–23 ноября 2026. До 100 тысяч рублей на билеты и отель, прогулки у моря и день в горах. Собери варианты.

Ответ:

Все пять вариантов используют один и тот же перелёт «Победы» 16–23 ноября 2026: прилёт в 15:20, обратный вылет в 15:50, 16 396 ₽ за двоих. Тариф базовый: ручная кладь 36×30×27 (1 место), багаж не включён, билет невозвратный и без обмена. Различается только проживание.

Суммы — лишь известная часть (перелёт + отель) по сведениям поставщика tutu: без питания, местного транспорта, экскурсий и дополнительных сборов. Это поисковые тарифы, не подтверждённая бронь; полная стоимость и наличие неизвестны. Поиск частичный (5 вариантов), поэтому это не исчерпывающая выборка и не рейтинг направлений. День в горах пока не входит ни в один вариант — горных дней 0 при нужном 1.

Сейчас отмечен самый дешёвый вариант — с Гостевым домом Море; у него, однако, нет гостевой оценки в данных.
Москва → Сочи, 16.11.2026 — 23.11.2026; взрослых: 2.
Бюджет: 100000 ₽ на группу; предел группы 100000 ₽.

1. Гостевой дом Море — Адлер
Проживание: 2026-11-16 — 2026-11-23.
Поездка: 2026-11-16 — 2026-11-23.
Перелёт: Победа; прибытие 16.11 в 15:20, отправление обратно 23.11 в 15:50 (местное время).
Тариф: Базовый.
Зарегистрированный багаж: 0 кг.
Билеты и проживание: известная сумма 21 786 ₽ на всю группу и весь период.
Подойдёт: Самая низкая известная сумма — 21 786 ₽ за двоих: больше запаса до 100 000 ₽ на день в горах, питание и дорогу.
Компромисс: Гостевой дом в Адлере, без звёзд, рейтинг 0,0 — гостевой оценки в данных нет. Условия проживания не раскрыты.
Горных дней 0, требуется 1

2. Централ Резиденс 3* by Provence — Сочи
Проживание: 2026-11-16 — 2026-11-23.
Поездка: 2026-11-16 — 2026-11-23.
Перелёт: Победа; прибытие 16.11 в 15:20, отправление обратно 23.11 в 15:50 (местное время).
Тариф: Базовый.
Зарегистрированный багаж: 0 кг.
Билеты и проживание: известная сумма 24 896 ₽ на всю группу и весь период.
Подойдёт: 3* в Сочи с рейтингом 9,19; известная сумма 24 896 ₽ — второй результат по дешевизне.
Компромисс: На 3 110 ₽ дороже минимального варианта; условия тарифа отеля (отмена, питание) не показаны.
Горных дней 0, требуется 1

3. Охотник отель by Orion Hotels — Адлер
Проживание: 2026-11-16 — 2026-11-23.
Поездка: 2026-11-16 — 2026-11-23.
Перелёт: Победа; прибытие 16.11 в 15:20, отправление обратно 23.11 в 15:50 (местное время).
Тариф: Базовый.
Зарегистрированный багаж: 0 кг.
Билеты и проживание: известная сумма 31 614 ₽ на всю группу и весь период.
Подойдёт: Отель в Адлере с рейтингом 7,89; известная сумма 31 614 ₽.
Компромисс: Проживание 15 218 ₽ — заметно дороже другого варианта в Адлере при более низком рейтинге; звёздность не указана, условия не раскрыты.
Горных дней 0, требуется 1

4. Ranovsky Park — Сочи
Проживание: 2026-11-16 — 2026-11-23.
Поездка: 2026-11-16 — 2026-11-23.
Перелёт: Победа; прибытие 16.11 в 15:20, отправление обратно 23.11 в 15:50 (местное время).
Тариф: Базовый.
Зарегистрированный багаж: 0 кг.
Билеты и проживание: известная сумма 34 096 ₽ на всю группу и весь период.
Подойдёт: 4* в Сочи с рейтингом 8,21; известная сумма 34 096 ₽.
Компромисс: На 9 200 ₽ дороже минимального варианта — меньше запаса до 100 000 ₽, при этом полная стоимость неизвестна.
Горных дней 0, требуется 1

5. Апартаменты Lux Merilin Monroe — Сочи
Проживание: 2026-11-16 — 2026-11-23.
Поездка: 2026-11-16 — 2026-11-23.
Перелёт: Победа; прибытие 16.11 в 15:20, отправление обратно 23.11 в 15:50 (местное время).
Тариф: Базовый.
Зарегистрированный багаж: 0 кг.
Билеты и проживание: известная сумма 35 936 ₽ на всю группу и весь период.
Подойдёт: Апартаменты в Сочи с рейтингом 8,54.
Компромисс: Самая высокая известная сумма — 35 936 ₽; звёздность не указана, условия проживания и отмены не раскрыты.
Горных дней 0, требуется 1

Программа первого варианта (горных дней: 0):
2026-11-16: дорога / свободное время.
2026-11-17: дорога / свободное время.
2026-11-18: дорога / свободное время.
2026-11-19: дорога / свободное время.
2026-11-20: дорога / свободное время.
2026-11-21: дорога / свободное время.
2026-11-22: дорога / свободное время.
2026-11-23: дорога / свободное время.
Питание, местные переезды, активности и дополнительные сборы не включены. Полная стоимость неизвестна; наличие и бронирование не подтверждены.
Какой вариант обсудим? Можно спросить об отеле или районе, изменить пожелания или выбрать номер варианта.

Что пока не удалось подтвердить:
• Программа по дням пока не подтверждена.
• Не удалось подтвердить требуемое число горных дней.

### Ход 2

Отправлен: 2026-10-28T19:49:14.409541+00:00; полный ответ: 2026-10-28T19:55:14.771513+00:00; 360.030s, HTTP 504. Token streaming отсутствует; время первого токена N/A.

Пользователь:

А если на два дня позже? Сдвинь всю поездку на 18–25 ноября 2026 года. Остальные пожелания сохрани: двое взрослых из Москвы, до 100 тысяч рублей на билеты и отель, прогулки у моря и один день в горах.

Ответ:

(HTTP ошибка, текстового ответа нет)

Действие last_action, HTTP 200: `{"answer": "Вариант выбран. Можно обсудить детали или явно подтвердить имитацию покупки.", "detail": null, "stage": "review", "status": "partial", "simulated": null, "paid": null, "reserved": null, "message": null, "payment": null}`

## Наблюдаемый workflow

| Узел | Начало/конец | Время, s | Переход/исход |
|---|---|---:|---|
| supervisor | 2026-10-28T19:44:34.897606+00:00 (конец) | 10.668 | delegate |
| delegate | 2026-10-28T19:44:34.898796+00:00 (конец) | 0.000 | completed |
| transport | 2026-10-28T19:45:20.570843+00:00 (конец) | 45.671 | completed |
| experience | 2026-10-28T19:45:55.127590+00:00 (конец) | 80.215 | completed |
| evaluate | 2026-10-28T19:45:55.130391+00:00 (конец) | 0.002 | delegate |
| delegate | 2026-10-28T19:45:55.134101+00:00 (конец) | 0.000 | completed |
| stays | 2026-10-28T19:47:17.976603+00:00 (конец) | 82.842 | completed |
| evaluate | 2026-10-28T19:47:18.061918+00:00 (конец) | 0.084 | repair |
| repair | 2026-10-28T19:47:25.045896+00:00 (конец) | 6.982 | delegate |
| delegate | 2026-10-28T19:47:25.047017+00:00 (конец) | 0.000 | completed |
| experience | 2026-10-28T19:48:39.915187+00:00 (конец) | 74.864 | completed |
| evaluate | 2026-10-28T19:48:40.126401+00:00 (конец) | 0.210 | respond |
| respond | 2026-10-28T19:49:02.515726+00:00 (конец) | 22.387 | completed |
| finish | 2026-10-28T19:49:02.516778+00:00 (конец) | 0.000 | completed |
| supervisor | 2026-10-28T19:49:36.379978+00:00 (конец) | 21.920 | delegate |
| delegate | 2026-10-28T19:49:36.382948+00:00 (конец) | 0.002 | completed |
| stays | 2026-10-28T19:50:45.353818+00:00 (конец) | 68.938 | completed |
| transport | 2026-10-28T19:51:01.494214+00:00 (конец) | 85.110 | completed |
| evaluate | 2026-10-28T19:51:01.500675+00:00 (конец) | 0.006 | delegate |
| delegate | 2026-10-28T19:51:01.506160+00:00 (конец) | 0.003 | completed |
| experience | 2026-10-28T19:52:31.524832+00:00 (конец) | 90.018 | completed |
| evaluate | 2026-10-28T19:52:32.071406+00:00 (конец) | 0.546 | repair |
| repair | 2026-10-28T19:52:47.674011+00:00 (конец) | 15.600 | delegate |
| delegate | 2026-10-28T19:52:47.675195+00:00 (конец) | 0.000 | completed |
| experience | 2026-10-28T19:53:36.083768+00:00 (конец) | 48.350 | completed |
| transport | 2026-10-28T19:53:40.873662+00:00 (конец) | 53.197 | completed |
| evaluate | 2026-10-28T19:53:40.883140+00:00 (конец) | 0.009 | delegate |
| delegate | 2026-10-28T19:53:40.891190+00:00 (конец) | 0.005 | completed |
| stays | 2026-10-28T19:55:01.380125+00:00 (конец) | 80.488 | completed |
| evaluate | 2026-10-28T19:55:01.889792+00:00 (конец) | 0.509 | respond |
| respond | 2026-10-28T19:55:14.437805+00:00 (конец) | 12.545 | CancelledError |
| supervisor | 2026-10-28T19:55:46.072655+00:00 (конец) | 0.000 | finish |
| finish | 2026-10-28T19:55:46.074078+00:00 (конец) | 0.000 | completed |

Это времена конкретных выполнений узлов; параллельные durations не суммируются в время хода. Case 01 использует раннюю версию инструментализации: нет отдельных длительностей delegate/answer и исходного TurnPlan, есть post-validation supervisor_decision и сетевые/агентные события. В cases 02–05 дополнительно записываются все эти узлы и typed_supervisor_decision. Ничего не восстанавливалось из приватных рассуждений.

| Роль LLM | LLM calls | ReAct tool starts |
|---|---:|---:|
| supervisor | 6 | 0 |
| transport | 21 | 30 |
| experience | 18 | 41 |
| stays | 13 | 26 |
| presenter | 2 | 0 |

Роли LLM получены из реального UsageLogger по usage/run ID; при наличии совпадения сопоставлены с HTTP usage. Финализатор относится к модели специалиста, presenter — отдельная роль отображения.

Финальные warnings: `{"transport": ["agent_limit", "unverified_source_ids"], "experience": ["weather_outside_forecast_horizon", "tool_limit", "agent_limit", "finalization_failed"], "stays": ["agent_limit", "finalization_failed"]}`.

## Реальные источники

| MCP/API | Tool/endpoint | HTTP | Outcome | Элементов | Время запроса, s | Полное логическое время MCP, s |
|---|---|---:|---|---:|---:|---:|
| tutu | search_rail | 200 | ok | 0 | 1.028 | 1.699 |
| tutu | search_rail | 200 | ok | 5 | 1.084 | 1.841 |
| openmeteo | /v1/forecast | 200 | http_ok | None | 0.713 | 0.000 |
| timepad | /v1/events | 200 | http_ok | 5 | 0.830 | 0.000 |
| travelpayouts | /aviasales/v3/prices_for_dates | 200 | http_ok | None | 0.910 | 0.000 |
| 2gis | search_places | 200 | ok | 10 | 4.039 | 6.027 |
| tutu | search_etrain | 200 | ok | 0 | 0.129 | 0.875 |
| 2gis | search_places | 200 | ok | 5 | 0.535 | 5.399 |
| tutu | search_avia | 200 | ok | 10 | 1.888 | 2.569 |
| geoapify | /v2/places | 200 | http_ok | 10 | 0.957 | 0.000 |
| 2gis | search_places | 200 | ok | 9 | 0.689 | 2.384 |
| 2gis | search_places | 200 | schema_error | None | 0.559 | 2.319 |
| 2gis | search_places | 200 | ok | 10 | 0.531 | 2.510 |
| tutu | search_avia | 200 | ok | 10 | 2.366 | 3.203 |
| 2gis | search_places | 200 | ok | 10 | 0.470 | 3.175 |
| 2gis | search_places | None | network_error | None | 24.061 | 0.000 |
| 2gis | search_places | 200 | ok | 10 | 0.457 | 32.254 |
| tutu | search_hotels | 200 | ok | 10 | 0.655 | 1.516 |
| tutu | search_hotels | 200 | ok | 10 | 3.293 | 4.208 |
| tutu | search_hotels | 200 | ok | 10 | 1.272 | 37.336 |
| tutu | get_offer_details | 200 | ok | None | 1.698 | 3.265 |
| tutu | get_offer_details | 200 | ok | None | 5.315 | 7.244 |
| tutu | get_offer_details | 200 | ok | None | 4.854 | 6.731 |
| tutu | get_offer_details | 200 | ok | None | 1.813 | 3.754 |
| tutu | get_offer_details | 200 | ok | None | 4.708 | 6.614 |
| 2gis | search_places | 200 | ok | 10 | 0.595 | 3.200 |
| 2gis | search_places | None | network_error | None | 27.376 | 0.000 |
| 2gis | search_places | 200 | ok | 10 | 0.563 | 3.250 |
| 2gis | search_places | 200 | ok | 2 | 0.537 | 3.152 |
| 2gis | search_places | 200 | ok | 10 | 0.490 | 32.332 |
| 2gis | search_places | 200 | ok | 2 | 0.440 | 32.350 |
| geoapify | /v2/places | 200 | http_ok | 10 | 1.094 | 0.000 |
| geoapify | /v2/places | 200 | http_ok | 9 | 1.060 | 0.000 |
| 2gis | search_places | 200 | ok | 10 | 0.469 | 2.233 |
| 2gis | search_places | 200 | ok | 10 | 0.765 | 8.681 |
| tutu | search_rail | 200 | ok | 4 | 0.522 | 1.511 |
| tutu | search_avia | 200 | ok | 10 | 9.984 | 10.996 |
| tutu | search_rail | 200 | ok | 5 | 1.120 | 2.135 |
| tutu | search_hotels | 200 | ok | 10 | 1.062 | 1.973 |
| tutu | search_hotels | 200 | ok | 10 | 0.862 | 1.763 |
| tutu | get_offer_details | 200 | ok | None | 0.029 | 1.072 |
| tutu | search_hotels | 200 | ok | 10 | 2.841 | 19.710 |
| tutu | get_offer_details | 200 | ok | None | 5.033 | 6.021 |
| tutu | get_offer_details | 200 | ok | None | 0.468 | 1.482 |
| tutu | get_offer_details | 200 | ok | None | 5.369 | 6.434 |
| tutu | get_offer_details | 200 | ok | None | 0.031 | 17.109 |
| tutu | get_offer_details | 200 | ok | None | 0.028 | 17.149 |
| tutu | search_avia | 200 | ok | 10 | 0.110 | 1.157 |
| tutu | search_avia | 200 | ok | 10 | 2.315 | 3.079 |
| tutu | search_avia | 200 | ok | 10 | 1.817 | 2.652 |
| 2gis | search_places | None | network_error | None | 28.347 | 0.000 |
| 2gis | search_places | 200 | ok | 2 | 0.542 | 32.329 |
| 2gis | search_places | 200 | ok | 10 | 0.512 | 32.543 |
| 2gis | search_places | 200 | ok | 10 | 3.681 | 5.304 |
| 2gis | search_places | 200 | ok | 10 | 0.484 | 2.234 |
| openmeteo | /v1/forecast | 200 | http_ok | None | 0.746 | 0.000 |
| timepad | /v1/events | 200 | http_ok | 7 | 1.122 | 0.000 |
| 2gis | search_places | None | network_error | None | 0.864 | 0.000 |
| openmeteo | /v1/forecast | 200 | http_ok | None | 0.831 | 0.000 |
| timepad | /v1/events | 200 | http_ok | 7 | 0.933 | 0.000 |
| 2gis | search_places | 200 | ok | 3 | 0.465 | 2.282 |
| 2gis | search_places | 200 | ok | 10 | 0.607 | 2.484 |
| geoapify | /v2/places | 200 | http_ok | 10 | 0.806 | 0.000 |
| tutu | search_rail | 200 | ok | 5 | 1.040 | 7.305 |
| tutu | search_avia | 200 | ok | 10 | 2.345 | 8.653 |
| tutu | search_rail | 200 | ok | 4 | 0.631 | 6.910 |
| 2gis | search_places | 200 | ok | 10 | 0.472 | 2.682 |
| 2gis | build_route | 200 | ok | None | 0.442 | 2.875 |
| tutu | search_avia | 200 | ok | 10 | 0.051 | 0.709 |
| 2gis | search_places | 200 | ok | 10 | 0.662 | 11.305 |
| opentripmap | /0.1/ru/places/radius | 200 | http_ok | 10 | 1.012 | 0.000 |
| tutu | search_etrain | 200 | ok | 0 | 0.282 | 1.339 |
| tutu | get_offer_details | 200 | ok | None | 0.026 | 1.171 |
| 2gis | search_places | 200 | ok | 10 | 0.527 | 2.403 |
| tutu | search_hotels | 200 | ok | 10 | 1.095 | 1.850 |
| tutu | search_hotels | 200 | ok | 10 | 0.479 | 31.412 |
| tutu | get_offer_details | 200 | ok | None | 2.773 | 4.216 |
| tutu | get_offer_details | 200 | ok | None | 4.598 | 6.016 |
| tutu | get_offer_details | 200 | ok | None | 3.275 | 4.732 |
| tutu | get_offer_details | 200 | ok | None | 0.736 | 2.191 |
| tutu | get_offer_details | 200 | ok | None | 3.012 | 4.468 |

MCP business requests учитываются по фактическим HTTP tools/call; initialize/list/notifications исключены из числа поисков, но сохранены в trace. MCP status/count взяты из ближайшего matching runtime result; retries указаны в JSON. При отмене без итогового protocol result outcome — network_error и count неизвестен. Корреляция wire → runtime result временная по роли/tool/безопасным параметрам, а не по сквозному MCP ID; исходные runtime events сохранены в trace, неоднозначность не считается доказательством точной связи. REST http_ok означает HTTP-успех, а не доказательство валидного продукта; реальный tool outcome отдельно в trace.

## Стоимость и длительность

Токены ниже известны только по вернувшемуся usage; при timeout они неизвестны, стоимость покрывается полным резервом.

Сумма ожидания пользовательских ходов/действий: 639.206s. LLM calls: 60; prompt 592940, completion 35911, cached input 221952. Provider-reported LLM: $0.0571950686; общий консервативный учёт с API/неполным биллингом: **$2.2711270686**. Общий ledger единый для всех кейсов, см. COST_REPORT.md.

После timeout результат проверен отдельным GET публичной поездки: ограничения и варианты доступны. Это восстановление чтением, а не полученный ответ на исходный POST.

## Проверка фактов и денег

Проверки ниже вычислены по ответу публичного API; TripState не изменялся. Внешние вызовы подтверждаются trace/MCP protocol, но независимый повторный поиск цен не делался, чтобы не расходовать бюджет и не сравнивать разные котировки. Полный контроль числовых исходных quotes для case 01 ограничен ранней инструментализацией; для последующих случаев safe quotes записываются в mcp_calls.json.

```json
[
  {
    "option_id": "082a930e054769f9",
    "transport": "НордСтар",
    "stay": "Гостевой дом Море",
    "price_transport_rub": "13562.0",
    "price_stay_rub": "5390.0",
    "known_subtotal_rub": "18952.0",
    "sum_correct": true,
    "basis_correct": true,
    "currency_correct": true,
    "party_correct": true,
    "arrival_matches_stay": true,
    "dates": {
      "transport": [
        "2026-11-18",
        "2026-11-25"
      ],
      "stay": [
        "2026-11-18",
        "2026-11-25"
      ]
    },
    "sources": {
      "transport": {
        "provider": "tutu",
        "source_url": "https://mcp.tutu.ru/mcp",
        "retrieved_at": "2026-10-28T19:52:58.513046Z",
        "evidence": "live",
        "source_updated_at": null,
        "expires_at": "2026-10-28T20:02:58.513046Z"
      },
      "stay": {
        "provider": "tutu",
        "source_url": "https://mcp.tutu.ru/mcp",
        "retrieved_at": "2026-10-28T19:50:01.029739Z",
        "evidence": "live",
        "source_updated_at": null,
        "expires_at": "2026-10-28T20:00:01.029739Z"
      }
    },
    "day_count": 8,
    "populated_days": 0,
    "missing_costs": [
      "meals",
      "local_transport",
      "activities",
      "extra_fees"
    ],
    "fresh_at_response": true
  },
  {
    "option_id": "1d56d00ca36ba5b2",
    "transport": "НордСтар",
    "stay": "Централ Резиденс 3* by Provence",
    "price_transport_rub": "13562.0",
    "price_stay_rub": "8500.0",
    "known_subtotal_rub": "22062.0",
    "sum_correct": true,
    "basis_correct": true,
    "currency_correct": true,
    "party_correct": true,
    "arrival_matches_stay": true,
    "dates": {
      "transport": [
        "2026-11-18",
        "2026-11-25"
      ],
      "stay": [
        "2026-11-18",
        "2026-11-25"
      ]
    },
    "sources": {
      "transport": {
        "provider": "tutu",
        "source_url": "https://mcp.tutu.ru/mcp",
        "retrieved_at": "2026-10-28T19:52:58.513046Z",
        "evidence": "live",
        "source_updated_at": null,
        "expires_at": "2026-10-28T20:02:58.513046Z"
      },
      "stay": {
        "provider": "tutu",
        "source_url": "https://mcp.tutu.ru/mcp",
        "retrieved_at": "2026-10-28T19:53:57.924864Z",
        "evidence": "live",
        "source_updated_at": null,
        "expires_at": "2026-10-28T20:03:57.924864Z"
      }
    },
    "day_count": 8,
    "populated_days": 0,
    "missing_costs": [
      "meals",
      "local_transport",
      "activities",
      "extra_fees"
    ],
    "fresh_at_response": true
  },
  {
    "option_id": "ab328ca7851e1f65",
    "transport": "НордСтар",
    "stay": "Малекон",
    "price_transport_rub": "13562.0",
    "price_stay_rub": "9320.0",
    "known_subtotal_rub": "22882.0",
    "sum_correct": true,
    "basis_correct": true,
    "currency_correct": true,
    "party_correct": true,
    "arrival_matches_stay": true,
    "dates": {
      "transport": [
        "2026-11-18",
        "2026-11-25"
      ],
      "stay": [
        "2026-11-18",
        "2026-11-25"
      ]
    },
    "sources": {
      "transport": {
        "provider": "tutu",
        "source_url": "https://mcp.tutu.ru/mcp",
        "retrieved_at": "2026-10-28T19:52:58.513046Z",
        "evidence": "live",
        "source_updated_at": null,
        "expires_at": "2026-10-28T20:02:58.513046Z"
      },
      "stay": {
        "provider": "tutu",
        "source_url": "https://mcp.tutu.ru/mcp",
        "retrieved_at": "2026-10-28T19:54:27.499051Z",
        "evidence": "live",
        "source_updated_at": null,
        "expires_at": "2026-10-28T20:04:27.499051Z"
      }
    },
    "day_count": 8,
    "populated_days": 0,
    "missing_costs": [
      "meals",
      "local_transport",
      "activities",
      "extra_fees"
    ],
    "fresh_at_response": true
  },
  {
    "option_id": "011362e01979ebd6",
    "transport": "НордСтар",
    "stay": "Аквамарин Парк",
    "price_transport_rub": "13562.0",
    "price_stay_rub": "9600.0",
    "known_subtotal_rub": "23162.0",
    "sum_correct": true,
    "basis_correct": true,
    "currency_correct": true,
    "party_correct": true,
    "arrival_matches_stay": true,
    "dates": {
      "transport": [
        "2026-11-18",
        "2026-11-25"
      ],
      "stay": [
        "2026-11-18",
        "2026-11-25"
      ]
    },
    "sources": {
      "transport": {
        "provider": "tutu",
        "source_url": "https://mcp.tutu.ru/mcp",
        "retrieved_at": "2026-10-28T19:52:58.513046Z",
        "evidence": "live",
        "source_updated_at": null,
        "expires_at": "2026-10-28T20:02:58.513046Z"
      },
      "stay": {
        "provider": "tutu",
        "source_url": "https://mcp.tutu.ru/mcp",
        "retrieved_at": "2026-10-28T19:49:43.305542Z",
        "evidence": "live",
        "source_updated_at": null,
        "expires_at": "2026-10-28T19:59:43.305542Z"
      }
    },
    "day_count": 8,
    "populated_days": 0,
    "missing_costs": [
      "meals",
      "local_transport",
      "activities",
      "extra_fees"
    ],
    "fresh_at_response": true
  },
  {
    "option_id": "785cd08fcdd3dbb2",
    "transport": "НордСтар",
    "stay": "Гостевой дом Бастион",
    "price_transport_rub": "13562.0",
    "price_stay_rub": "10354.0",
    "known_subtotal_rub": "23916.0",
    "sum_correct": true,
    "basis_correct": true,
    "currency_correct": true,
    "party_correct": true,
    "arrival_matches_stay": true,
    "dates": {
      "transport": [
        "2026-11-18",
        "2026-11-25"
      ],
      "stay": [
        "2026-11-18",
        "2026-11-25"
      ]
    },
    "sources": {
      "transport": {
        "provider": "tutu",
        "source_url": "https://mcp.tutu.ru/mcp",
        "retrieved_at": "2026-10-28T19:52:58.513046Z",
        "evidence": "live",
        "source_updated_at": null,
        "expires_at": "2026-10-28T20:02:58.513046Z"
      },
      "stay": {
        "provider": "tutu",
        "source_url": "https://mcp.tutu.ru/mcp",
        "retrieved_at": "2026-10-28T19:54:27.499051Z",
        "evidence": "live",
        "source_updated_at": null,
        "expires_at": "2026-10-28T20:04:27.499051Z"
      }
    },
    "day_count": 8,
    "populated_days": 0,
    "missing_costs": [
      "meals",
      "local_transport",
      "activities",
      "extra_fees"
    ],
    "fresh_at_response": true
  }
]
```

## Что работает

- Первоначально получены пять пакетов на 16–23 ноября с реальными котировками Tutu.
- Публичный GET после timeout подтвердил пять новых пакетов на 18–25 ноября; старые даты в новые options не попали.
- Двое взрослых, Москва, бюджет 100000, прогулки и mountain_days=1 сохранены. Выбор обновлённого пакета через API завершился HTTP 200.

## Проблемы и невыполненные требования

- Начальный план: 0 горных дней при требовании 1; календарь пуст после встроенного repair.
- В объяснении Ranovsky Park сказано, что 34 096 ₽ на 9 200 ₽ дороже минимального варианта 21 786 ₽. Фактическая разница 12 310 ₽; суммы пакетов корректны, арифметика свободного текста presenter не проверена.
- Пересборка завершилась HTTP 504 через 360.030s: пользователь не получил итогового ответа, хотя новые варианты уже сохранены в checkpoint.
- Обязательный горный день по-прежнему не собран. Поздний запрос выбора работает после timeout, но нормальный диалог пересборки не завершён.

## Рекомендации

- Разницы и сравнения цен вычислять в существующем engine и передавать presenter готовыми числами.
- Сохранять предпочтения и инвалидировать только зависимые от новых дат данные.
- Перед общим deadline завершать ход с текущим partial планом и явной причиной, сохраняя финальный ответ; не продлевать бесконтрольные tool/LLM циклы.
