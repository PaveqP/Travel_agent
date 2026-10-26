# Сравнение API: измерения 25.10.2026

Сценарий: 12–16 ноября 2026, 4 ночи, 2 взрослых. Воспроизводимый итог: [integration_results.json](../reports/integration_results.json). Выборка мала: медиана ниже — по неоднородным сценариям, включая ошибки и установку MCP-сессии; это не нагрузочный тест или SLA.

| Источник | Приоритет | Запросов/кейсов | Успешных данных | Медиана, мс | Результат / причина |
|---|---|---:|---:|---:|---|
| Туту: авиа, отели, ж/д, электрички, автобусы | P0 | 14 | 9 | 3522 | measured: connection_error:1, ok:10, call_error:2, empty:1 |
| Aviasales / Travelpayouts Data API | P1 | 3 | 3 | 173 | measured: ok:3 |
| Aviasales Search API | P3 | 0 | 0 | — | partner_access_required: No approved partner scope/contract; public credentials do not grant Search API rights |
| stufently/aviasales-mcp (обёртка Data API) | P2 | 2 | 1 | 1618 | measured: ok:2 |
| Duffel Flights | P3 | 0 | 0 | — | missing_key: DUFFEL_ACCESS_TOKEN |
| Aviationstack | P3 | 0 | 0 | — | missing_key: AVIATIONSTACK_API_KEY |
| AirLabs | P3 | 0 | 0 | — | missing_key: AIRLABS_API_KEY |
| Amadeus | P3 | 0 | 0 | — | not_testable: Официальный SDK https://github.com/amadeus4dev/amadeus-python архивирован; портал не дал содержимого через web. Сообщение о закрытии Self-Service найдено во вторичных источниках, но не принято за самостоятельно подтверждённый официальный статус. Запросить Enterprise условия, не тратить время на старые sandbox keys. |
| MixVel | P3 | 0 | 0 | — | partner_access_required: No approved partner scope/contract; public credentials do not grant Search API rights |
| Сирена-Трэвел | P3 | 0 | 0 | — | partner_access_required: No approved partner scope/contract; public credentials do not grant Search API rights |
| Островок / Emerging Travel Group | P3 | 0 | 0 | — | partner_access_unavailable: User confirmed ETG/Ostrovok credentials unavailable |
| Nuitee Connect / LiteAPI | P2 | 17 | 7 | 877 | measured: ok:9, no_availability:7, dependency_missing:1 |
| Booking.com Demand API | P3 | 0 | 0 | — | partner_access_required: No approved partner scope/contract; public credentials do not grant Search API rights |
| Expedia Rapid | P3 | 0 | 0 | — | partner_access_required: No approved partner scope/contract; public credentials do not grant Search API rights |
| Hotelbeds / HBX | P3 | 0 | 0 | — | missing_key: HOTELBEDS_API_KEY, HOTELBEDS_SECRET |
| Броневик | P3 | 0 | 0 | — | partner_access_required: No approved partner scope/contract; public credentials do not grant Search API rights |
| Яндекс Расписания | P0 | 12 | 6 | 252 | measured: empty:3, dependency_missing:3, ok:6 |
| Яндекс Go deeplinks | P1 | 1 | 0 | — | measured: local_only:1 |
| UFS.travel | P3 | 0 | 0 | — | partner_access_required: No approved partner scope/contract; public credentials do not grant Search API rights |
| Kiwitaxi | P3 | 0 | 0 | — | partner_access_required: No approved partner scope/contract; public credentials do not grant Search API rights |
| Intui.travel | P3 | 0 | 0 | — | partner_access_required: No approved partner scope/contract; public credentials do not grant Search API rights |
| 2ГИС | P0 | 7 | 6 | 1862 | measured: ok:7 |
| Google Maps / Maps Grounding Lite | P3 | 0 | 0 | — | missing_key: GOOGLE_MAPS_API_KEY |
| Mapbox | P3 | 0 | 0 | — | missing_key: MAPBOX_ACCESS_TOKEN |
| OpenStreetMap: данные | P1 | 1 | 0 | — | measured: indirect_data_only:1 |
| Overpass API | P3 | 3 | 0 | 35620 | measured: network_error:3 |
| Nominatim | P1 | 2 | 2 | 651 | measured: ok:2 |
| OpenRouteService / HeiGIT | P1 | 1 | 1 | 910 | measured: ok:1 |
| GraphHopper | P3 | 0 | 0 | — | missing_key: GRAPHHOPPER_API_KEY |
| Geoapify | P0 | 9 | 8 | 1000 | measured: ok:9 |
| GeoNames | P3 | 0 | 0 | — | missing_key: GEONAMES_USERNAME |
| OSRM | P2 | 2 | 1 | 7810 | measured: network_error:1, ok:1 |
| Wikidata Query Service | P3 | 1 | 0 | 726 | measured: forbidden:1 |
| KudaGo | P3 | 3 | 0 | 61 | measured: forbidden:3 |
| Timepad | P1 | 2 | 2 | 5818 | measured: ok:2 |
| OpenTripMap | P2 | 4 | 4 | 70 | measured: ok:4 |
| Sputnik8 | P3 | 0 | 0 | — | partner_access_required: No approved partner scope/contract; public credentials do not grant Search API rights |
| Tripster affiliate API | P3 | 0 | 0 | — | partner_access_required: No approved partner scope/contract; public credentials do not grant Search API rights |
| Viator Partner API | P3 | 0 | 0 | — | partner_access_required: No approved partner scope/contract; public credentials do not grant Search API rights |
| GetYourGuide | P3 | 0 | 0 | — | partner_access_required: No approved partner scope/contract; public credentials do not grant Search API rights |
| Qtickets | P3 | 0 | 0 | — | missing_key: QTICKETS_TOKEN |
| PRO.Культура.РФ export API | P3 | 0 | 0 | — | partner_access_required: No approved partner scope/contract; public credentials do not grant Search API rights |
| Open-Meteo Forecast | P0 | 1 | 1 | 636 | measured: ok:1 |
| Open-Meteo Marine | P1 | 2 | 1 | 7747 | measured: network_error:1, ok:1 |
| Open-Meteo Air Quality | P2 | 1 | 1 | 435 | measured: ok:1 |
| Open-Meteo Elevation | P1 | 1 | 1 | 527 | measured: ok:1 |
| WeatherAPI | P3 | 0 | 0 | — | missing_key: WEATHERAPI_KEY |
| OpenWeather REST / MCP for agents | P3 | 1 | 0 | 76580 | measured: connection_error:1 |
| Курсы валют ЦБ РФ | P1 | 2 | 2 | 355 | measured: ok:2 |

## Интерпретация сценариев

Ниже — зафиксированная интерпретация исходного прогона 25.10.2026; при повторном запуске актуальные числа проверять в JSON и таблице выше.
A: Tutu дал 10 round-trip предложений за всю группу; минимальная цена первого поиска 14 018 RUB. Travelpayouts дал кэш DP6941 3 194 RUB и UT268 3 600 RUB за взрослого, на двоих 13 588 RUB. Это разные типы котировки; разница не доказывает выгоду при покупке. Багаж/возврат есть у вариантов Tutu; в Data API отсутствуют. Смена дат Tutu на 13–17 ноября дала 3 предложения, первое 14 368 RUB за двоих туда-обратно.
B: Tutu: по 10 отелей для четырёх геозапросов, 32 уникальных ID, тарифы за 4 ночи на двоих, фотографии/рейтинги/условия завтрака/отмены и ссылки. Геопоиск может расширять район (Красная Поляна разрешилась в курорт); проверять координаты. LiteAPI: 40 строк, 30 уникальных объектов каталога, ноль тарифов Сочи в sandbox, в том числе при смене RUB на USD. Контроль Boston вернул sandbox-тарифы. Это не доказательство постоянного отсутствия России в production.
C: 2GIS, Geoapify, ORS дали маршруты и POI. Первый маршрут 2GIS: 44 500 м / 2 666 с; Geoapify: 44 180 м / 2 233.569 с. OSRM после первого таймаута: 41 761.2 м / 2 661.6 с. Начало — Адлер, не центр Сочи. У ORS/Geoapify/OSRM общий OSM, независимыми картографическими свидетельствами их считать нельзя. Поиск POI в радиусе 1 км около Marriott проверен двумя поставщиками.
D: Timepad вернул 4 события, из них три даты стендап-экскурсии по 1 390 RUB/билет; остаток мест не подтверждён. Бесплатное бизнес-событие не подменяет туристическую активность. OpenTripMap проверен отдельно; KudaGo HTTP403, Wikidata HTTP403, Overpass таймауты — не отсутствие POI в Сочи.
E: Яндекс Расписания: suburban в nearest_stations дал пустой список; train,suburban позволил найти станции. Адлер s9613054 → Роза Хутор s9812791: 15 сегментов, пример 6101 07:49–08:19, 30 минут, 300 RUB/место. Расписание и тариф не подтверждают свободные места. Tutu etrain вернул пустой offers для Адлер→Роза Хутор; это не успешное расписание, рабочий источник здесь Яндекс. Yandex Go только построение документированного deeplink, приложение/заказ не тестировались.
F: Open-Meteo прогноз 25–31 октября, не даты ноябрьской поездки. Проверены температура, осадки, ветер для побережья и гор; Marine после таймаута успешно вернул волны, Air Quality и Elevation также проверены. Сетка модели не является измерением непосредственно у отеля.

## Оценки 0–5

Порядок: покрытие / полезность / актуальность / цены / простота / стабильность / MCP / лимиты / коммерция / агент. T — экспертная оценка на основании теста; D — предварительная по документации; ? — нет достаточных оснований. — для цен непрофильных API означает N/A. Лимиты/коммерция оценены предварительно только для выбранных источников: 5 — наиболее простой доступ, 4 — доступно с оговорками, 3 — существенные квоты/условия, 2 — demo/noncommercial/public-instance ограничения; это не разрешение использования. Условия в API_CATALOG, тест квоты не подтверждает лицензию. Покрытие 4 означает проверен Сочи, не весь мир; стабильность 4 означает успешную малую выборку, не SLA. Итоговый средний балл не считается из неизвестных значений.

| Источник | 10 оценок с основанием |
|---|---|
| Туту: авиа, отели, ж/д, электрички, автобусы | 4(T) / 5(T) / 4(T) / 4(T) / 5(D) / 3(T) / 5(T) / 4(D:conditional on terms) / ? / 4(D) |
| Aviasales / Travelpayouts Data API | 4(T) / 4(T) / 2(T) / 2(T) / 3(D) / 4(T) / ? / 3(D:conditional on terms) / 3(D:conditional on terms) / 4(D) |
| Aviasales Search API | ? / 2(D) / ? / ? / 1(D) / ? / ? / ? / ? / 2(D) |
| stufently/aviasales-mcp (обёртка Data API) | 4(T) / 4(T) / 2(T) / 2(T) / 3(D) / 4(T) / 5(T) / 3(D:conditional on terms) / 2(D:conditional on terms) / 2(D) |
| Duffel Flights | ? / 2(D) / ? / ? / 3(D) / ? / ? / ? / ? / 2(D) |
| Aviationstack | ? / 2(D) / ? / ? / 3(D) / ? / ? / ? / ? / 2(D) |
| AirLabs | ? / 2(D) / ? / ? / 3(D) / ? / ? / ? / ? / 2(D) |
| Amadeus | ? / 2(D) / ? / ? / 1(D) / ? / ? / ? / ? / 2(D) |
| MixVel | ? / 2(D) / ? / ? / 1(D) / ? / ? / ? / ? / 2(D) |
| Сирена-Трэвел | ? / 2(D) / ? / ? / 1(D) / ? / ? / ? / ? / 2(D) |
| Островок / Emerging Travel Group | ? / 2(D) / ? / ? / 1(D) / ? / ? / ? / ? / 2(D) |
| Nuitee Connect / LiteAPI | 3(T) / 4(T) / 2(T) / 0(T:Sochi sandbox only) / 3(D) / 4(T) / 5(T) / 3(D:conditional on terms) / 3(D:conditional on terms) / 2(D) |
| Booking.com Demand API | ? / 2(D) / ? / ? / 1(D) / ? / ? / ? / ? / 2(D) |
| Expedia Rapid | ? / 2(D) / ? / ? / 1(D) / ? / ? / ? / ? / 2(D) |
| Hotelbeds / HBX | ? / 2(D) / ? / ? / 3(D) / ? / ? / ? / ? / 2(D) |
| Броневик | ? / 2(D) / ? / ? / 1(D) / ? / ? / ? / ? / 2(D) |
| Яндекс Расписания | 4(T) / 5(T) / 4(T) / 2(T) / 3(D) / 4(T) / ? / 3(D:conditional on terms) / 3(D:conditional on terms) / 4(D) |
| Яндекс Go deeplinks | ? / 4(D) / ? / ? / 5(D) / ? / ? / ? / ? / 4(D) |
| UFS.travel | ? / 2(D) / ? / ? / 1(D) / ? / ? / ? / ? / 2(D) |
| Kiwitaxi | ? / 2(D) / ? / ? / 1(D) / ? / ? / ? / ? / 2(D) |
| Intui.travel | ? / 2(D) / ? / ? / 1(D) / ? / ? / ? / ? / 2(D) |
| 2ГИС | 4(T) / 5(T) / 4(T) / — / 3(D) / 4(T) / 5(T) / 3(D:conditional on terms) / 4(D:conditional on terms) / 4(D) |
| Google Maps / Maps Grounding Lite | ? / 2(D) / ? / — / 3(D) / ? / ? / ? / ? / 2(D) |
| Mapbox | ? / 2(D) / ? / — / 3(D) / ? / ? / ? / ? / 2(D) |
| OpenStreetMap: данные | ? / 4(D) / ? / — / 5(D) / ? / ? / ? / ? / 4(D) |
| Overpass API | ? / 2(D) / ? / — / 5(D) / ? / ? / ? / ? / 2(D) |
| Nominatim | 4(T) / 4(T) / 4(T) / — / 5(D) / 4(T) / ? / 2(D:conditional on terms) / 2(D:conditional on terms) / 4(D) |
| OpenRouteService / HeiGIT | 4(T) / 4(T) / 4(T) / — / 3(D) / 4(T) / ? / 3(D:conditional on terms) / 3(D:conditional on terms) / 4(D) |
| GraphHopper | ? / 2(D) / ? / — / 3(D) / ? / ? / ? / ? / 2(D) |
| Geoapify | 4(T) / 5(T) / 4(T) / — / 3(D) / 4(T) / 5(T) / 4(D:conditional on terms) / 4(D:conditional on terms) / 4(D) |
| GeoNames | ? / 2(D) / ? / — / 3(D) / ? / ? / ? / ? / 2(D) |
| OSRM | 4(T) / 4(T) / 4(T) / — / 5(D) / 3(T) / ? / 2(D:conditional on terms) / 2(D:conditional on terms) / 2(D) |
| Wikidata Query Service | ? / 2(D) / ? / — / 5(D) / ? / ? / ? / ? / 2(D) |
| KudaGo | ? / 2(D) / ? / ? / 5(D) / ? / ? / ? / ? / 2(D) |
| Timepad | 4(T) / 4(T) / 4(T) / 2(T) / 3(D) / 4(T) / ? / 4(D:conditional on terms) / 3(D:conditional on terms) / 4(D) |
| OpenTripMap | 4(T) / 4(T) / 4(T) / ? / 3(D) / 4(T) / ? / 4(D:conditional on terms) / 2(D:conditional on terms) / 2(D) |
| Sputnik8 | ? / 2(D) / ? / ? / 1(D) / ? / ? / ? / ? / 2(D) |
| Tripster affiliate API | ? / 2(D) / ? / ? / 1(D) / ? / ? / ? / ? / 2(D) |
| Viator Partner API | ? / 2(D) / ? / ? / 1(D) / ? / ? / ? / ? / 2(D) |
| GetYourGuide | ? / 2(D) / ? / ? / 1(D) / ? / ? / ? / ? / 2(D) |
| Qtickets | ? / 2(D) / ? / ? / 3(D) / ? / ? / ? / ? / 2(D) |
| PRO.Культура.РФ export API | ? / 2(D) / ? / ? / 1(D) / ? / ? / ? / ? / 2(D) |
| Open-Meteo Forecast | 4(T) / 5(T) / 4(T) / — / 5(D) / 4(T) / ? / 4(D:conditional on terms) / 2(D:conditional on terms) / 4(D) |
| Open-Meteo Marine | 4(T) / 4(T) / 4(T) / — / 5(D) / 3(T) / ? / 4(D:conditional on terms) / 2(D:conditional on terms) / 4(D) |
| Open-Meteo Air Quality | 4(T) / 4(T) / 4(T) / — / 5(D) / 4(T) / ? / 4(D:conditional on terms) / 2(D:conditional on terms) / 2(D) |
| Open-Meteo Elevation | 4(T) / 4(T) / 4(T) / — / 5(D) / 4(T) / ? / 4(D:conditional on terms) / 2(D:conditional on terms) / 4(D) |
| WeatherAPI | ? / 2(D) / ? / — / 3(D) / ? / ? / ? / ? / 2(D) |
| OpenWeather REST / MCP for agents | ? / 2(D) / ? / — / 3(D) / ? / ? / ? / ? / 2(D) |
| Курсы валют ЦБ РФ | 4(T) / 4(T) / 4(T) / — / 5(D) / 4(T) / ? / 5(D:conditional on terms) / 4(D:conditional on terms) / 4(D) |
