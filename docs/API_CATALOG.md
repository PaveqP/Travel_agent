# Каталог API и MCP

Документальная инвентаризация выполнена 25 октября 2026. Этап 2 завершён: фактические статусы и приоритеты в [API_COMPARISON.md](API_COMPARISON.md), вызовы в [MCP_TEST_RESULTS.md](MCP_TEST_RESULTS.md). Ниже сохранены условия доступа и исходные документальные оценки; успешность определять по отчёту, не по наличию ссылки.

Счётная единица — запись интеграции, не уникальная компания и не успешно работающий сервис. Туту учитывается один раз во всех доменах; Островок/ETG объединены. Четыре Open-Meteo API имеют общую политику использования; community Aviasales MCP — дополнительная обёртка того же Data API. OSM — источник данных, Go — deeplink. Их нельзя выдавать за независимые live API.

Доступ: **no_key** — документирован путь без ключа (для OSM — данные, для Go — ссылки); **self_service** — самостоятельный старт, иногда только sandbox/demo; **partner** — API требует партнёрского процесса/выданного доступа; **unresolved** — доступ не установлен. Бесплатный тестовый доступ не означает коммерческое production-разрешение. Статус self_service не подтверждает возможность регистрации/оплаты из РФ.

Приоритеты в таблице ниже исторические, **предварительные**; итоговые находятся в API_COMPARISON. P0 — первым проверить для MVP, P1 — полезный резерв/дополнение, P2 — факультативно, P3 — не включать в MVP сейчас. Покрытие Сочи, latency, стабильность, цены и наличие оценены отдельно в этапе 2. Неизвестное не заменяется нулём или положительной оценкой. Для карт/погоды бронирование N/A.

Для каждого источника ниже явно указаны доступ, ключи, лимиты, коммерческие ограничения, РФ/Сочи, возможности цен/бронирования и MCP. «MCP не подтверждён» означает результат этого поиска, а не доказательство отсутствия MCP вообще. Все ссылки — документация владельца API, его репозиторий или официальные партнёрские материалы; исключение — размещённое третьей стороной собственное заявление Booking Holdings, обозначенное в записи.

Итого **49 записей**: **13 no_key**, **20 self_service**, **15 partner**, **1 unresolved**.

| ID | Источник | Доступ | Приоритет |
|---|---|---|---|
| tutu | [Туту: авиа, отели, ж/д, электрички, автобусы](https://mcp.tutu.ru/mcp) | no_key | P0 |
| travelpayouts_data | [Aviasales / Travelpayouts Data API](https://github.com/travelpayouts/api-docs) | self_service | P1 |
| travelpayouts_search | [Aviasales Search API](https://support.travelpayouts.com/hc/en-us/articles/34788165535250-Search-API-usage-rules) | partner | P3 |
| aviasales_community | [stufently/aviasales-mcp (обёртка Data API)](https://github.com/stufently/aviasales-mcp) | self_service | P2 |
| duffel | [Duffel Flights](https://duffel.com/docs/api/overview/test-your-integration) | self_service | P3 |
| aviationstack | [Aviationstack](https://aviationstack.com/documentation) | self_service | P2 |
| airlabs | [AirLabs](https://airlabs.co/docs/) | self_service | P2 |
| amadeus | [Amadeus](https://developers.amadeus.com/) | unresolved | P3 |
| mixvel | [MixVel](https://docs.mixvel.com/api/) | partner | P2 |
| sirena | [Сирена-Трэвел](https://www.sirena-travel.ru/pomoshh-i-obsluzhivanie/) | partner | P2 |
| etg | [Островок / Emerging Travel Group](https://docs-api.ostrovok.ru/) | partner | P0 |
| liteapi | [Nuitee Connect / LiteAPI](https://docs.liteapi.travel/reference/mcp-server) | self_service | P1 |
| booking | [Booking.com Demand API](https://developers.booking.com/demand/docs/getting-started/prerequisites) | partner | P3 |
| expedia | [Expedia Rapid](https://developers.expediagroup.com/rapid/setup) | partner | P3 |
| hotelbeds | [Hotelbeds / HBX](https://developer.hotelbeds.com/documentation/getting-started/) | self_service | P3 |
| bronevik | [Броневик](https://bronevik.com/ru/api-solutions) | partner | P1 |
| yandex_rasp | [Яндекс Расписания](https://yandex.ru/dev/rasp/doc/ru/concepts/access) | self_service | P0 |
| yandex_go | [Яндекс Go deeplinks](https://yandex.ru/support/taxi-distr/ru/api/deeplinks) | no_key | P1 |
| ufs | [UFS.travel](https://www.ufs-partner.ru/) | partner | P2 |
| kiwitaxi | [Kiwitaxi](https://kiwitaxi.com/en/partner/webmaster/instructions/) | partner | P2 |
| intui | [Intui.travel](https://en.intui.travel/) | partner | P2 |
| 2gis | [2ГИС](https://docs.2gis.com/en/api/ai/mcp-server/cloud) | self_service | P0 |
| google_maps | [Google Maps / Maps Grounding Lite](https://developers.google.com/maps/ai/grounding-lite) | self_service | P2 |
| mapbox | [Mapbox](https://github.com/mapbox/mcp-server) | self_service | P2 |
| osm | [OpenStreetMap: данные](https://www.openstreetmap.org/copyright) | no_key | P1 |
| overpass | [Overpass API](https://dev.overpass-api.de/overpass-doc/en/preface/commons.html) | no_key | P1 |
| nominatim | [Nominatim](https://operations.osmfoundation.org/policies/nominatim/) | no_key | P1 |
| ors | [OpenRouteService / HeiGIT](https://openrouteservice.org/) | self_service | P1 |
| graphhopper | [GraphHopper](https://docs.graphhopper.com/) | self_service | P2 |
| geoapify | [Geoapify](https://apidocs.geoapify.com/) | self_service | P1 |
| geonames | [GeoNames](https://www.geonames.org/export/web-services.html) | self_service | P2 |
| osrm | [OSRM](https://github.com/Project-OSRM/osrm-backend/blob/master/docs/http.md) | no_key | P2 |
| wikidata | [Wikidata Query Service](https://www.mediawiki.org/wiki/Wikidata_Query_Service/User_Manual) | no_key | P2 |
| kudago | [KudaGo](https://docs.kudago.com/api/) | no_key | P1 |
| timepad | [Timepad](https://dev.timepad.ru/api/) | self_service | P1 |
| opentripmap | [OpenTripMap](https://dev.opentripmap.org/product) | self_service | P1 |
| sputnik | [Sputnik8](https://www.sputnik8.com/doc/api/v1/cities.html) | partner | P1 |
| tripster | [Tripster affiliate API](https://tripster.atlassian.net/wiki/spaces/affiliates/pages/3688235009) | partner | P1 |
| viator | [Viator Partner API](https://docs.viator.com/partner-api/technical/) | partner | P3 |
| getyourguide | [GetYourGuide](https://partner.getyourguide.support/hc/en-us/articles/13981133907613-API-integration-and-requirements) | partner | P3 |
| qtickets | [Qtickets](https://qtickets.help/article/rest-api/) | self_service | P3 |
| culture | [PRO.Культура.РФ export API](https://pro.culture.ru/documentation/export_API_PRO.pdf) | partner | P1 |
| openmeteo_forecast | [Open-Meteo Forecast](https://open-meteo.com/en/docs) | no_key | P0 |
| openmeteo_marine | [Open-Meteo Marine](https://open-meteo.com/en/docs/marine-weather-api) | no_key | P1 |
| openmeteo_air | [Open-Meteo Air Quality](https://open-meteo.com/en/docs/air-quality-api) | no_key | P2 |
| openmeteo_elevation | [Open-Meteo Elevation](https://open-meteo.com/en/docs/elevation-api) | no_key | P1 |
| weatherapi | [WeatherAPI](https://www.weatherapi.com/docs/) | self_service | P2 |
| openweather | [OpenWeather REST / MCP for agents](https://openweathermap.org/api) | self_service | P2 |
| cbr | [Курсы валют ЦБ РФ](https://www.cbr.ru/development/sxml/) | no_key | P1 |

## A. Авиабилеты и мультитранспорт

### Туту: авиа, отели, ж/д, электрички, автобусы — P0

- Документация: https://mcp.tutu.ru/mcp
- Протокол: MCP Streamable HTTP. MCP: Официальный: https://mcp.tutu.ru/mcp.
- Доступ: `no_key`. Начало подключения: https://mcp.tutu.ru/mcp.
- Переменные: нет подтверждённых ключевых переменных; см. условия доступа.
- Бесплатный старт/лимиты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.
- РФ / Сочи: Российский сервис; выдача конкретных дат и районов Сочи ещё не проверена.
- Цены, наличие, покупка: Поиск билетов/номеров, переход к покупке заявлены; не подтверждены вызовом.
- Коммерческое использование: Публичное подключение не заменяет согласование коммерческого использования.
- Примечание: Без авторизации прямо указано на странице; initialize/tools/list/tools/call пока не выполнялись. Категории подтверждает https://hackathon2026.tutu.ru/.

### Aviasales / Travelpayouts Data API — P1

- Документация: https://github.com/travelpayouts/api-docs
- Протокол: REST JSON. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `self_service`. Начало подключения: https://www.travelpayouts.com/developers/api.
- Переменные: `TRAVELPAYOUTS_TOKEN`, `TRAVELPAYOUTS_MARKER`.
- Бесплатный старт/лимиты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.
- РФ / Сочи: Россия релевантна; MOW–AER и свежесть конкретной записи проверить.
- Цены, наличие, покупка: Кэш пользовательских поисков, НЕ актуальная доступность. Продажа на стороне партнёра.
- Коммерческое использование: По договору/условиям провайдера; право на хранение и перепубликацию отдельно согласовать.
- Примечание: Маркер — партнёрский ID для атрибуции; авторизация Data API токеном. Документация кэша: https://github.com/travelpayouts/api-docs/blob/master/source/index.html.md.

### Aviasales Search API — P3

- Документация: https://support.travelpayouts.com/hc/en-us/articles/34788165535250-Search-API-usage-rules
- Протокол: REST JSON. MCP: Официальный MCP не подтверждён.
- Доступ: `partner`. Начало подключения: https://support.travelpayouts.com/hc/en-us/requests/new.
- Переменные: `TRAVELPAYOUTS_TOKEN`, `TRAVELPAYOUTS_MARKER`.
- Бесплатный старт/лимиты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.
- РФ / Сочи: Российское направление релевантно; доступ отдельно от Data API.
- Цены, наличие, покупка: Live search и ссылка покупки; действуют ограничения показа.
- Коммерческое использование: Только после одобрения, с обязательными правилами.
- Примечание: Каждый поиск инициирует пользователь, полная выдача, booking link только после клика. Запрещены автоматический сбор и объединение с API других авиаметапоисков. Не включать в общий сравнительный прогон. Точный порог трафика здесь не подтверждён первоисточником.

### stufently/aviasales-mcp (обёртка Data API) — P2

- Документация: https://github.com/stufently/aviasales-mcp
- Протокол: MCP stdio / HTTP. MCP: Сторонний; репозиторий указан в документации..
- Доступ: `self_service`. Начало подключения: https://www.travelpayouts.com/developers/api.
- Переменные: `TRAVELPAYOUTS_TOKEN`.
- Бесплатный старт/лимиты: Лимиты upstream Data API.
- РФ / Сочи: Те же ограничения, что у Data API.
- Цены, наличие, покупка: Кэш; наличие мест не доказывает.
- Коммерческое использование: GPL-3.0-or-later для кода; лицензия данных Travelpayouts отдельно.
- Примечание: Python >=3.12; fastmcp>=3.1,<4, httpx, pydantic, pydantic-settings, starlette. Последний push 2026-10-24. Не установлен, полный аудит исходников ещё не выполнен; запускать в отдельном venv (ограничения starlette отличаются).

### Duffel Flights — P3

- Документация: https://duffel.com/docs/api/overview/test-your-integration
- Протокол: REST JSON. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `self_service`. Начало подключения: https://app.duffel.com/join.
- Переменные: `DUFFEL_ACCESS_TOKEN`.
- Бесплатный старт/лимиты: Test mode; live коммерческие условия: https://duffel.com/pricing.
- РФ / Сочи: Российская регистрация/оплата и фактическая выдача Сочи не подтверждены; глобальное покрытие не является доказательством.
- Цены, наличие, покупка: Offers/orders есть; тестовые предложения не доказывают реальные рейсы РФ.
- Коммерческое использование: По договору/условиям провайдера; право на хранение и перепубликацию отдельно согласовать.
- Примечание: Начать только с test token. Production требует активации бизнеса. https://duffel.com/guides/getting-started

### Aviationstack — P2

- Документация: https://aviationstack.com/documentation
- Протокол: REST JSON. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `self_service`. Начало подключения: https://aviationstack.com/signup/free.
- Переменные: `AVIATIONSTACK_API_KEY`.
- Бесплатный старт/лимиты: Free: 100 запросов/месяц, non-commercial; HTTPS указан на https://aviationstack.com/pricing.
- РФ / Сочи: Российская регистрация/оплата и фактическая выдача Сочи не подтверждены; глобальное покрытие не является доказательством.
- Цены, наличие, покупка: Статусы/расписания/справочники; НЕ цены билетов и НЕ бронирование.
- Коммерческое использование: Free только некоммерческий; commercial — платный тариф.

### AirLabs — P2

- Документация: https://airlabs.co/docs/
- Протокол: REST JSON + MCP stdio. MCP: Официальный: https://github.com/airlabs-co/airlabs-mcp.
- Доступ: `self_service`. Начало подключения: https://airlabs.co/signup.
- Переменные: `AIRLABS_API_KEY`.
- Бесплатный старт/лимиты: Бесплатный ключ заявлен; точную квоту проверить в кабинете.
- РФ / Сочи: Российская регистрация/оплата и фактическая выдача Сочи не подтверждены; глобальное покрытие не является доказательством.
- Цены, наличие, покупка: Авиаданные/статусы; не тарифы и не бронирование.
- Коммерческое использование: По договору/условиям провайдера; право на хранение и перепубликацию отдельно согласовать.
- Примечание: https://airlabs.co/mcp-server-flight-data; MIT, Node >=18, @modelcontextprotocol/sdk. Push 2026-06-25; код не запускался.

### Amadeus — P3

- Документация: https://developers.amadeus.com/
- Протокол: Enterprise API; прежний Self-Service OAuth2. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `unresolved`. Начало подключения: https://developers.amadeus.com/.
- Переменные: нет подтверждённых ключевых переменных; см. условия доступа.
- Бесплатный старт/лимиты: Новый Self-Service доступ не подтверждён; старые инструкции регистрации не использовать.
- РФ / Сочи: Российская регистрация/оплата и фактическая выдача Сочи не подтверждены; глобальное покрытие не является доказательством.
- Цены, наличие, покупка: Enterprise возможности зависят от контракта; live РФ не подтверждён.
- Коммерческое использование: По договору/условиям провайдера; право на хранение и перепубликацию отдельно согласовать.
- Примечание: Официальный SDK https://github.com/amadeus4dev/amadeus-python архивирован; портал не дал содержимого через web. Сообщение о закрытии Self-Service найдено во вторичных источниках, но не принято за самостоятельно подтверждённый официальный статус. Запросить Enterprise условия, не тратить время на старые sandbox keys.

### MixVel — P2

- Документация: https://docs.mixvel.com/api/
- Протокол: HTTPS POST XML, NDC-подобный. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `partner`. Начало подключения: https://mixvel.com/.
- Переменные: нет подтверждённых ключевых переменных; см. условия доступа.
- Бесплатный старт/лимиты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.
- РФ / Сочи: Российский поставщик; конкретный набор авиакомпаний/Сочи по договору.
- Цены, наличие, покупка: AirShopping и order flow документированы.
- Коммерческое использование: По договору/условиям провайдера; право на хранение и перепубликацию отдельно согласовать.
- Примечание: Схему учётных данных получить вместе с доступом; переменные наугад не вводятся.

### Сирена-Трэвел — P2

- Документация: https://www.sirena-travel.ru/pomoshh-i-obsluzhivanie/
- Протокол: Партнёрский интерфейс; спецификацию запросить. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `partner`. Начало подключения: https://www.sirena-travel.ru/.
- Переменные: нет подтверждённых ключевых переменных; см. условия доступа.
- Бесплатный старт/лимиты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.
- РФ / Сочи: Российский GDS; конкретное покрытие по контракту.
- Цены, наличие, покупка: Агентские продажи; методы и доступ нужно получить от поставщика.
- Коммерческое использование: По договору/условиям провайдера; право на хранение и перепубликацию отдельно согласовать.
- Примечание: Не использовать внутренние endpoints сайтов авиакомпаний.

## B. Отели

### Островок / Emerging Travel Group — P0

- Документация: https://docs-api.ostrovok.ru/
- Протокол: REST JSON / Basic Auth. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `partner`. Начало подключения: https://ostrovok.ru/affiliate/.
- Переменные: `ETG_KEY_ID`, `ETG_API_KEY`, `ETG_BASE_URL`.
- Бесплатный старт/лимиты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.
- РФ / Сочи: Российский поставщик — основной кандидат. Выдача номеров Сочи на даты НЕ проверена.
- Цены, наличие, покупка: Каталог, тарифы, наличие, prebook/book; sandbox только тестовые объекты.
- Коммерческое использование: По договору/условиям провайдера; право на хранение и перепубликацию отдельно согласовать.
- Примечание: Одна семья интеграций, не два независимых источника. https://docs.emergingtravel.com/docs/certification/ ; https://help.b2b.ostrovok.ru/ru/articles/9330513 ; ключи и endpoint из контракта. Уточнить тип Affiliate/B2B, whitelist IP и вид sandbox у организаторов хакатона.

### Nuitee Connect / LiteAPI — P1

- Документация: https://docs.liteapi.travel/reference/mcp-server
- Протокол: REST JSON + MCP. MCP: Официальный: https://mcp.liteapi.travel/api/mcp.
- Доступ: `self_service`. Начало подключения: https://dashboard.liteapi.travel/.
- Переменные: `LITEAPI_API_KEY`.
- Бесплатный старт/лимиты: MCP docs: default 500 requests/sec; это rate limit, НЕ бесплатная квота. Billing по endpoints.
- РФ / Сочи: Российская регистрация/оплата и фактическая выдача Сочи не подтверждены; глобальное покрытие не является доказательством.
- Цены, наличие, покупка: Каталог/тарифы/доступность/prebook/book; sandbox не подтверждает live-наличие.
- Коммерческое использование: Production/монетизация по условиям аккаунта.
- Примечание: Для REST X-API-Key, MCP документирует apiKey в query: URL никогда не логировать. Запросить sand_ ключ и проверить бесплатные лимиты до тестов.

### Booking.com Demand API — P3

- Документация: https://developers.booking.com/demand/docs/getting-started/prerequisites
- Протокол: REST JSON. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `partner`. Начало подключения: https://developers.booking.com/demand/docs.
- Переменные: `BOOKING_API_KEY`, `BOOKING_AFFILIATE_ID`.
- Бесплатный старт/лимиты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.
- РФ / Сочи: В заявлении Booking Holdings приостановлены travel services в РФ; исключён из MVP Сочи.
- Цены, наличие, покупка: Demand: search/look/redirect или book, зависит от доступа.
- Коммерческое использование: По договору/условиям провайдера; право на хранение и перепубликацию отдельно согласовать.
- Примечание: Нужны Managed Affiliate Partner, договор, Partner Centre. Официальное заявление компании: https://www.business-humanrights.org/en/latest-news/booking-holdings-response/ (хостинг заявления третьей стороной). Официальный публичный MCP для Demand не подтверждён; scraping-обёртки не подходят.

### Expedia Rapid — P3

- Документация: https://developers.expediagroup.com/rapid/setup
- Протокол: REST JSON, подписанные запросы. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `partner`. Начало подключения: https://partner.expediagroup.com/en-us/solutions/build-your-travel-experience/rapid-api.
- Переменные: `EXPEDIA_API_KEY`, `EXPEDIA_SHARED_SECRET`.
- Бесплатный старт/лимиты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.
- РФ / Сочи: Российская регистрация/оплата и фактическая выдача Сочи не подтверждены; глобальное покрытие не является доказательством.
- Цены, наличие, покупка: Lodging availability/rates/booking; sandbox отдельный.
- Коммерческое использование: Договор и review перед production.
- Примечание: Не рекомендован для Сочи без подтверждения разрешённого российского inventory. Проверенный onboarding: https://developers.expediagroup.com/rapid/setup. Не утверждаем текущее покрытие по старым новостям.

### Hotelbeds / HBX — P3

- Документация: https://developer.hotelbeds.com/documentation/getting-started/
- Протокол: REST JSON, подпись SHA256. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `self_service`. Начало подключения: https://developer.hotelbeds.com/.
- Переменные: `HOTELBEDS_API_KEY`, `HOTELBEDS_SECRET`.
- Бесплатный старт/лимиты: Evaluation: 50 запросов/день; production после сертификации.
- РФ / Сочи: Российская регистрация/оплата и фактическая выдача Сочи не подтверждены; глобальное покрытие не является доказательством.
- Цены, наличие, покупка: Hotel Booking/Content, также Activities/Transfers. Sandbox не реальные номера.
- Коммерческое использование: По договору/условиям провайдера; право на хранение и перепубликацию отдельно согласовать.
- Примечание: В группу самостоятельной регистрации включён ТОЛЬКО evaluation; production — партнёрский.

### Броневик — P1

- Документация: https://bronevik.com/ru/api-solutions
- Протокол: SOAP/XML. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `partner`. Начало подключения: https://bronevik.com/ru/api-solutions.
- Переменные: нет подтверждённых ключевых переменных; см. условия доступа.
- Бесплатный старт/лимиты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.
- РФ / Сочи: Официально ориентирован на РФ; Сочи на датах проверить.
- Цены, наличие, покупка: Контент, цены брутто/нетто, заказы, дополнительные услуги.
- Коммерческое использование: По договору/условиям провайдера; право на хранение и перепубликацию отдельно согласовать.
- Примечание: Схему credentials и sandbox запросить через форму; не выдавать supply/channel-manager API за поиск всех отелей.

## C. Локальный транспорт и трансферы

### Яндекс Расписания — P0

- Документация: https://yandex.ru/dev/rasp/doc/ru/concepts/access
- Протокол: REST JSON/XML. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `self_service`. Начало подключения: https://developer.tech.yandex.ru/.
- Переменные: `YANDEX_RASP_API_KEY`.
- Бесплатный старт/лимиты: Числовые лимиты и разрешённый сценарий сверить с условиями продукта.
- РФ / Сочи: Российские расписания; станции Сочи/Адлер/Роза Хутор проверить.
- Цены, наличие, покупка: Расписание; цены могут отсутствовать. Не API продажи билетов.
- Коммерческое использование: По условиям API; не считать ключ разрешением на любую перепубликацию.

### Яндекс Go deeplinks — P1

- Документация: https://yandex.ru/support/taxi-distr/ru/api/deeplinks
- Протокол: HTTPS deeplink. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `no_key`. Начало подключения: https://yandex.ru/support/taxi-distr/ru/api/deeplinks.
- Переменные: нет подтверждённых ключевых переменных; см. условия доступа.
- Бесплатный старт/лимиты: Для построения ссылки запрос API не требуется.
- РФ / Сочи: Передача координат поездки; доступность поездки определяет приложение.
- Цены, наличие, покупка: Ссылка открытия маршрута, НЕ подтверждённая цена/заказ.
- Коммерческое использование: По условиям программы; статистика/вознаграждения отдельно.
- Примечание: Публичный API цен такси/корпоративный API не равен deeplink; доступ согласуется отдельно.

### UFS.travel — P2

- Документация: https://www.ufs-partner.ru/
- Протокол: Партнёрский API; актуальную схему запросить. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `partner`. Начало подключения: https://www.ufs-partner.ru/.
- Переменные: нет подтверждённых ключевых переменных; см. условия доступа.
- Бесплатный старт/лимиты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.
- РФ / Сочи: Российские ж/д, авиа, автобусы; Сочи на датах не проверен.
- Цены, наличие, покупка: Справочники, расписания, места/продажи по доступу.
- Коммерческое использование: По договору/условиям провайдера; право на хранение и перепубликацию отдельно согласовать.

### Kiwitaxi — P2

- Документация: https://kiwitaxi.com/en/partner/webmaster/instructions/
- Протокол: Партнёрский API / deeplinks. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `partner`. Начало подключения: https://kiwitaxi.com/en/partner/.
- Переменные: нет подтверждённых ключевых переменных; см. условия доступа.
- Бесплатный старт/лимиты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.
- РФ / Сочи: Конкретные трансферы AER–курорты и условия РФ проверить.
- Цены, наличие, покупка: Трансферы, ссылки; актуальность тарифа и доступа уточнить.
- Коммерческое использование: По договору/условиям провайдера; право на хранение и перепубликацию отдельно согласовать.
- Примечание: Наличие регистрации в партнёрке не доказывает автоматическую выдачу API.

### Intui.travel — P2

- Документация: https://en.intui.travel/
- Протокол: Партнёрский API. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `partner`. Начало подключения: https://en.intui.travel/.
- Переменные: нет подтверждённых ключевых переменных; см. условия доступа.
- Бесплатный старт/лимиты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.
- РФ / Сочи: Российская регистрация/оплата и фактическая выдача Сочи не подтверждены; глобальное покрытие не является доказательством.
- Цены, наличие, покупка: Официально заявлены live availability, net pricing, booking.
- Коммерческое использование: По договору/условиям провайдера; право на хранение и перепубликацию отдельно согласовать.
- Примечание: Запросить BUYER API. fleet.intui.travel API IN предназначен перевозчикам и не заменяет поиск трансферов для путешественников.

## D. Карты и геоданные

### 2ГИС — P0

- Документация: https://docs.2gis.com/en/api/ai/mcp-server/cloud
- Протокол: REST + MCP Streamable HTTP. MCP: Официальный: https://mcp-2gis.api.2gis.com/mcp.
- Доступ: `self_service`. Начало подключения: https://platform.2gis.ru/.
- Переменные: `TWOGIS_API_KEY`.
- Бесплатный старт/лимиты: Демо 30 дней с ограничениями; точная квота в кабинете.
- РФ / Сочи: Российские POI/маршруты; Адлер и горный кластер проверить.
- Цены, наличие, покупка: POI, не свободные номера/бронирование.
- Коммерческое использование: Демо для проверки; production подписка и условия хранения данных.
- Примечание: Нужны Places, Geocoder, Routing, Matrix; Static по необходимости. Bearer/X-2GIS-API-Key. server_info без ключа не считается проверкой полезных геоинструментов.

### Google Maps / Maps Grounding Lite — P2

- Документация: https://developers.google.com/maps/ai/grounding-lite
- Протокол: REST + MCP. MCP: Официальный: https://mapstools.googleapis.com/mcp.
- Доступ: `self_service`. Начало подключения: https://console.cloud.google.com/apis/credentials.
- Переменные: `GOOGLE_MAPS_API_KEY`.
- Бесплатный старт/лимиты: Demo key для прототипа документирован; production billing/SKU квоты проверить.
- РФ / Сочи: Российская регистрация/оплата и фактическая выдача Сочи не подтверждены; глобальное покрытие не является доказательством.
- Цены, наличие, покупка: Цены/наличие/бронирование: не применимо.
- Коммерческое использование: По Google Maps Platform terms; есть ограничения хранения/атрибуции и региональные billing ограничения.
- Примечание: X-Goog-Api-Key; включить Maps Grounding Lite. Maps Code Assist MCP — документация для разработчика, не live POI. Grounding может возвращать AI summaries, сохранять provenance.

### Mapbox — P2

- Документация: https://github.com/mapbox/mcp-server
- Протокол: REST + MCP. MCP: Официальный: https://mcp.mapbox.com/mcp.
- Доступ: `self_service`. Начало подключения: https://account.mapbox.com/.
- Переменные: `MAPBOX_ACCESS_TOKEN`.
- Бесплатный старт/лимиты: Квоты различаются по API: https://www.mapbox.com/pricing; не универсальный free limit.
- РФ / Сочи: Россия присутствует в официальной таблице покрытия https://docs.mapbox.com/help/dive-deeper/mapbox-data/. Регистрация/оплата из РФ и качество Сочи не проверены.
- Цены, наличие, покупка: Цены/наличие/бронирование: не применимо.
- Коммерческое использование: По тарифу и лицензии API; MIT относится лишь к MCP-коду.
- Примечание: MIT; Node >=22; SDK v2, zod, Turf, OpenTelemetry; push 2026-10-23. Перед локальным запуском проверить scripts и telemetry.

### OpenStreetMap: данные — P1

- Документация: https://www.openstreetmap.org/copyright
- Протокол: OSM XML/PBF, выгрузки. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `no_key`. Начало подключения: https://www.openstreetmap.org/.
- Переменные: нет подтверждённых ключевых переменных; см. условия доступа.
- Бесплатный старт/лимиты: Не считать основной OSM editing API поисковым backend приложения.
- РФ / Сочи: Глобальные данные; полноту POI Сочи проверить.
- Цены, наличие, покупка: Цены/наличие/бронирование: не применимо.
- Коммерческое использование: ODbL, атрибуция и применимые share-alike требования.
- Примечание: В подсчёте отдельный источник данных; для запросов использовать Overpass/Nominatim, не дублировать их результаты как независимое подтверждение.

### Overpass API — P1

- Документация: https://dev.overpass-api.de/overpass-doc/en/preface/commons.html
- Протокол: HTTP + Overpass QL / JSON. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `no_key`. Начало подключения: https://overpass-api.de/.
- Переменные: нет подтверждённых ключевых переменных; см. условия доступа.
- Бесплатный старт/лимиты: Fair-use, динамические квоты/load shedding, без SLA.
- РФ / Сочи: OSM POI; часы работы/контакты могут отсутствовать.
- Цены, наличие, покупка: Цены/наличие/бронирование: не применимо.
- Коммерческое использование: ODbL + политика конкретного публичного инстанса.

### Nominatim — P1

- Документация: https://operations.osmfoundation.org/policies/nominatim/
- Протокол: REST JSON. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `no_key`. Начало подключения: https://nominatim.openstreetmap.org/.
- Переменные: нет подтверждённых ключевых переменных; см. условия доступа.
- Бесплатный старт/лимиты: Абсолютный максимум 1 запрос/с суммарно на приложение; User-Agent, кэш; без autocomplete/систематической выгрузки.
- РФ / Сочи: Геокодинг OSM; не полный ресторанный каталог.
- Цены, наличие, покупка: Цены/наличие/бронирование: не применимо.
- Коммерческое использование: ODbL и usage policy; массовый production — свой или коммерческий сервис.

### OpenRouteService / HeiGIT — P1

- Документация: https://openrouteservice.org/
- Протокол: REST JSON. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `self_service`. Начало подключения: https://account.heigit.org/.
- Переменные: `ORS_API_KEY`.
- Бесплатный старт/лимиты: Бесплатный Standard key; актуальные квоты в новом кабинете. Старый /plans возвращает 404.
- РФ / Сочи: OSM-маршруты; глобальные данные, Сочи/тропы проверить.
- Цены, наличие, покупка: Цены/наличие/бронирование: не применимо.
- Коммерческое использование: Проверить действующие условия HeiGIT и атрибуцию.
- Примечание: Официальная страница сообщает сбой сайта, но работающие API/кабинет. Не считать недоступность docs отказом API.

### GraphHopper — P2

- Документация: https://docs.graphhopper.com/
- Протокол: REST JSON. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `self_service`. Начало подключения: https://graphhopper.com/dashboard/#/signup.
- Переменные: `GRAPHHOPPER_API_KEY`.
- Бесплатный старт/лимиты: Free для non-commercial; квоты на https://www.graphhopper.com/pricing/.
- РФ / Сочи: Российская регистрация/оплата и фактическая выдача Сочи не подтверждены; глобальное покрытие не является доказательством.
- Цены, наличие, покупка: Цены/наличие/бронирование: не применимо.
- Коммерческое использование: Commercial — платный тариф; self-hosted engine лицензируется отдельно.

### Geoapify — P1

- Документация: https://apidocs.geoapify.com/
- Протокол: REST JSON. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `self_service`. Начало подключения: https://myprojects.geoapify.com/.
- Переменные: `GEOAPIFY_API_KEY`.
- Бесплатный старт/лимиты: Free 3000 credits/day, до 5 requests/sec; credits не всегда равны requests.
- РФ / Сочи: OSM и другие данные; конкретные POI/маршруты Сочи проверить.
- Цены, наличие, покупка: Цены/наличие/бронирование: не применимо.
- Коммерческое использование: Free допускает commercial при соблюдении квот и атрибуции: https://www.geoapify.com/pricing/.

### GeoNames — P2

- Документация: https://www.geonames.org/export/web-services.html
- Протокол: HTTP JSON/XML. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `self_service`. Начало подключения: https://www.geonames.org/login.
- Переменные: `GEONAMES_USERNAME`.
- Бесплатный старт/лимиты: Кредиты по методу: https://www.geonames.org/export/credits.html; квоты сверить в аккаунте.
- РФ / Сочи: Глобальный справочник топонимов; не бизнес-каталог.
- Цены, наличие, покупка: Цены/наличие/бронирование: не применимо.
- Коммерческое использование: Данные CC BY, условия webservice отдельно.
- Примечание: Это username, не API secret; включить Free Web Services в профиле.

### OSRM — P2

- Документация: https://github.com/Project-OSRM/osrm-backend/blob/master/docs/http.md
- Протокол: REST JSON. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `no_key`. Начало подключения: https://project-osrm.org/.
- Переменные: нет подтверждённых ключевых переменных; см. условия доступа.
- Бесплатный старт/лимиты: Demo только умеренное использование; production свой сервер/провайдер.
- РФ / Сочи: OSM маршруты; car profile не доказывает проход по горным тропам.
- Цены, наличие, покупка: Цены/наличие/бронирование: не применимо.
- Коммерческое использование: BSD-2-Clause движок, ODbL данные, политика demo отдельно.
- Примечание: Дополнительный резерв маршрутизации; публичный demo не SLA и не live пробки.

### Wikidata Query Service — P2

- Документация: https://www.mediawiki.org/wiki/Wikidata_Query_Service/User_Manual
- Протокол: SPARQL / JSON. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `no_key`. Начало подключения: https://query.wikidata.org/.
- Переменные: нет подтверждённых ключевых переменных; см. условия доступа.
- Бесплатный старт/лимиты: Публичный query timeout 60 с; уважать throttling/Retry-After.
- РФ / Сочи: Глобальные объекты; полноту русских описаний проверить.
- Цены, наличие, покупка: Цены/наличие/бронирование: не применимо.
- Коммерческое использование: Структурированные данные CC0; изображения/тексты имеют отдельные лицензии.

## E. Достопримечательности и события

### KudaGo — P1

- Документация: https://docs.kudago.com/api/
- Протокол: REST JSON. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `no_key`. Начало подключения: https://docs.kudago.com/api/.
- Переменные: нет подтверждённых ключевых переменных; см. условия доступа.
- Бесплатный старт/лимиты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.
- РФ / Сочи: sochi указан в документации; это не доказательство наличия будущих событий.
- Цены, наличие, покупка: Места/события, иногда текст цены; НЕ live inventory билетов.
- Коммерческое использование: Условия использования и ссылки на источник проверить перед коммерческим запуском.

### Timepad — P1

- Документация: https://dev.timepad.ru/api/
- Протокол: REST JSON. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `self_service`. Начало подключения: https://timepad.ru/.
- Переменные: `TIMEPAD_TOKEN`.
- Бесплатный старт/лимиты: 60 запросов/IP/мин; при превышении следующая минута блокируется.
- РФ / Сочи: Поиск событий с cities; наличие ближайших мероприятий Сочи не проверено.
- Цены, наличие, покупка: События/регистрация; доступ к билетным данным зависит от scope.
- Коммерческое использование: Права токена и условия Timepad; данные заказов/участников не запрашивать.
- Примечание: https://dev.timepad.ru/api/swagger-doc/ ; токен для чтения публичных событий, не широкий токен заказов.

### OpenTripMap — P1

- Документация: https://dev.opentripmap.org/product
- Протокол: REST JSON/GeoJSON. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `self_service`. Начало подключения: https://dev.opentripmap.org/price.
- Переменные: `OPENTRIPMAP_API_KEY`.
- Бесплатный старт/лимиты: Free: 5000/day, 10/sec, non-commercial.
- РФ / Сочи: Открытые глобальные POI и российские источники; Сочи проверить.
- Цены, наличие, покупка: POI/описания/изображения; не тарифы экскурсий/наличие.
- Коммерческое использование: Free non-commercial; commercial требует условий провайдера.
- Примечание: Актуальный dev-портал dev.opentripmap.org. Сторонний gateway найден, но не рекомендован без аудита и условий передачи ключа: https://pipeworx.io/packs/opentripmap/. Код/лицензия этой обёртки не подтверждены.

### Sputnik8 — P1

- Документация: https://www.sputnik8.com/doc/api/v1/cities.html
- Протокол: REST JSON. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `partner`. Начало подключения: https://www.sputnik8.com/ru/affiliate/new.
- Переменные: `SPUTNIK_API_KEY`, `SPUTNIK_USERNAME`.
- Бесплатный старт/лимиты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.
- РФ / Сочи: Сочи прямо указан в партнёрских материалах; даты/доступность проверить.
- Цены, наличие, покупка: Каталог экскурсий и партнёрские ссылки; slots/цены проверить в предоставленной версии API.
- Коммерческое использование: По договору/условиям провайдера; право на хранение и перепубликацию отдельно согласовать.
- Примечание: Запросить индивидуальный доступ. Публичные примеры с credentials не копировать в .env и не воспроизводить в отчётах. Партнёрская регистрация не равна одобрению любого API-сценария.

### Tripster affiliate API — P1

- Документация: https://tripster.atlassian.net/wiki/spaces/affiliates/pages/3688235009
- Протокол: Партнёрский API. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `partner`. Начало подключения: https://experience.tripster.ru/partner/.
- Переменные: `TRIPSTER_PARTNER_ID`.
- Бесплатный старт/лимиты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.
- РФ / Сочи: Российские экскурсии; Сочи на датах проверить.
- Цены, наличие, покупка: Каталог/партнёрский переход; live slots по выданной документации.
- Коммерческое использование: По договору/условиям провайдера; право на хранение и перепубликацию отдельно согласовать.
- Примечание: Документация требует вход в кабинет. Точный auth дополнить после одобрения. Guides API — заказы собственных экскурсий и не подходит для общего поиска. Не использовать HTTP с credentials.

### Viator Partner API — P3

- Документация: https://docs.viator.com/partner-api/technical/
- Протокол: REST JSON. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `partner`. Начало подключения: https://partnerresources.viator.com/.
- Переменные: `VIATOR_API_KEY`.
- Бесплатный старт/лимиты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.
- РФ / Сочи: Российская регистрация/оплата и фактическая выдача Сочи не подтверждены; глобальное покрытие не является доказательством.
- Цены, наличие, покупка: Контент/availability/booking в зависимости от уровня партнёрства.
- Коммерческое использование: По договору/условиям провайдера; право на хранение и перепубликацию отдельно согласовать.
- Примечание: Не рекомендован для Сочи без подтверждения покрытия. Официальный публичный MCP не подтверждён, сторонние варианты не запускались.

### GetYourGuide — P3

- Документация: https://partner.getyourguide.support/hc/en-us/articles/13981133907613-API-integration-and-requirements
- Протокол: Партнёрский API. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `partner`. Начало подключения: https://partner.getyourguide.com/.
- Переменные: нет подтверждённых ключевых переменных; см. условия доступа.
- Бесплатный старт/лимиты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.
- РФ / Сочи: Российская регистрация/оплата и фактическая выдача Сочи не подтверждены; глобальное покрытие не является доказательством.
- Цены, наличие, покупка: Basic teaser не availability; Reading добавляет availability; Masterbill — booking.
- Коммерческое использование: По договору/условиям провайдера; право на хранение и перепубликацию отдельно согласовать.
- Примечание: Basic: 100k visits/month или 50k app downloads; Reading: 1M visits и для текущих Basic 300 bookings/month. Для нового хакатонного проекта нецелесообразно.

### Qtickets — P3

- Документация: https://qtickets.help/article/rest-api/
- Протокол: REST JSON Bearer. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `self_service`. Начало подключения: https://qtickets.ru/.
- Переменные: `QTICKETS_TOKEN`.
- Бесплатный старт/лимиты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.
- РФ / Сочи: Российский сервис; токен продавца НЕ гарантирует афишу всего Сочи.
- Цены, наличие, покупка: Собственные мероприятия/билетные операции; не публичный агрегатор всех событий.
- Коммерческое использование: По договору продавца и полномочиям на контент.
- Примечание: Токен: кабинет продавца → Настройки → Основное. Без роли организатора оставить пустым.

### PRO.Культура.РФ export API — P1

- Документация: https://pro.culture.ru/documentation/export_API_PRO.pdf
- Протокол: HTTP JSON. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `partner`. Начало подключения: https://pro.culture.ru/.
- Переменные: `CULTURE_API_KEY`.
- Бесплатный старт/лимиты: По партнёрскому доступу.
- РФ / Сочи: Российские культурные события; Сочи и свежесть проверить.
- Цены, наличие, покупка: События, текстовые цены/ссылки; не live inventory.
- Коммерческое использование: Инфопартнёрские условия.
- Примечание: Ключ по договорённости с partners@team.culture.ru. Письма не отправлялись.

## F. Погода и контекст

### Open-Meteo Forecast — P0

- Документация: https://open-meteo.com/en/docs
- Протокол: REST JSON. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `no_key`. Начало подключения: https://open-meteo.com/en/pricing.
- Переменные: нет подтверждённых ключевых переменных; см. условия доступа.
- Бесплатный старт/лимиты: Общая free политика: 600/min, 5000/hour, 10000/day, 300000/month; не умножать квоту на число API.
- РФ / Сочи: Глобальные координатные модели; побережье/горы и заполненность полей проверить.
- Цены, наличие, покупка: Цены/наличие/бронирование: не применимо.
- Коммерческое использование: Open-access non-commercial; production подписка. Лицензия данных и атрибуция отдельно.
- Примечание: До 16 дней, не вся поездка через 2–3 недели. Температура/осадки/ветер по координатам.

### Open-Meteo Marine — P1

- Документация: https://open-meteo.com/en/docs/marine-weather-api
- Протокол: REST JSON. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `no_key`. Начало подключения: https://open-meteo.com/en/pricing.
- Переменные: нет подтверждённых ключевых переменных; см. условия доступа.
- Бесплатный старт/лимиты: Общая free политика: 600/min, 5000/hour, 10000/day, 300000/month; не умножать квоту на число API.
- РФ / Сочи: Глобальные координатные модели; побережье/горы и заполненность полей проверить.
- Цены, наличие, покупка: Цены/наличие/бронирование: не применимо.
- Коммерческое использование: Open-access non-commercial; production подписка. Лицензия данных и атрибуция отдельно.
- Примечание: Волны/морские условия; выбирать морскую ячейку, null не означает безопасное море.

### Open-Meteo Air Quality — P2

- Документация: https://open-meteo.com/en/docs/air-quality-api
- Протокол: REST JSON. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `no_key`. Начало подключения: https://open-meteo.com/en/pricing.
- Переменные: нет подтверждённых ключевых переменных; см. условия доступа.
- Бесплатный старт/лимиты: Общая free политика: 600/min, 5000/hour, 10000/day, 300000/month; не умножать квоту на число API.
- РФ / Сочи: Глобальные координатные модели; побережье/горы и заполненность полей проверить.
- Цены, наличие, покупка: Цены/наличие/бронирование: не применимо.
- Коммерческое использование: Open-access non-commercial; production подписка. Лицензия данных и атрибуция отдельно.
- Примечание: Состав загрязнений, модель/горизонт зависят от региона.

### Open-Meteo Elevation — P1

- Документация: https://open-meteo.com/en/docs/elevation-api
- Протокол: REST JSON. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `no_key`. Начало подключения: https://open-meteo.com/en/pricing.
- Переменные: нет подтверждённых ключевых переменных; см. условия доступа.
- Бесплатный старт/лимиты: Общая free политика: 600/min, 5000/hour, 10000/day, 300000/month; не умножать квоту на число API.
- РФ / Сочи: Глобальные координатные модели; побережье/горы и заполненность полей проверить.
- Цены, наличие, покупка: Цены/наличие/бронирование: не применимо.
- Коммерческое использование: Open-access non-commercial; production подписка. Лицензия данных и атрибуция отдельно.
- Примечание: Рельеф 90 м; статические высоты, не прогноз и не статус троп.

### WeatherAPI — P2

- Документация: https://www.weatherapi.com/docs/
- Протокол: REST JSON + MCP stdio. MCP: Официальный: https://github.com/weatherapicom/weatherapi-mcp.
- Доступ: `self_service`. Начало подключения: https://www.weatherapi.com/signup.aspx.
- Переменные: `WEATHERAPI_KEY`.
- Бесплатный старт/лимиты: Free: 100k/month, forecast 3 дня: https://www.weatherapi.com/pricing.
- РФ / Сочи: Российская регистрация/оплата и фактическая выдача Сочи не подтверждены; глобальное покрытие не является доказательством.
- Цены, наличие, покупка: Цены/наличие/бронирование: не применимо.
- Коммерческое использование: По terms и выбранному плану; проверить атрибуцию.
- Примечание: Node >=18, SDK ^1.0.0; push 2026-03-22. package.json заявляет MIT, GitHub API не распознал LICENSE — до локального запуска уточнить лицензию.

### OpenWeather REST / MCP for agents — P2

- Документация: https://openweathermap.org/api
- Протокол: REST JSON + MCP Streamable HTTP. MCP: Ссылка на MCP подтверждена официальной страницей: https://mcp.openweathermap.org/mcp.
- Доступ: `self_service`. Начало подключения: https://home.openweathermap.org/users/sign_up.
- Переменные: `OPENWEATHER_API_KEY`.
- Бесплатный старт/лимиты: Бесплатные REST продукты по подписке; One Call pay-per-call, не подключать автоматически.
- РФ / Сочи: Российская регистрация/оплата и фактическая выдача Сочи не подтверждены; глобальное покрытие не является доказательством.
- Цены, наличие, покупка: Цены/наличие/бронирование: не применимо.
- Коммерческое использование: Условия REST и отдельного агентоориентированного сервиса различаются.
- Примечание: https://mcp.openweathermap.org/ : отдельный агентный аккаунт/data key/баланс The Bot Forum. Обычный REST key не считать MCP-key. Нет расходов/авторегистрации; бесплатное tools/list не доказывает бесплатную погоду.

### Курсы валют ЦБ РФ — P1

- Документация: https://www.cbr.ru/development/sxml/
- Протокол: HTTP XML. MCP: Не подтверждён в проверенных официальных материалах.
- Доступ: `no_key`. Начало подключения: https://www.cbr.ru/development/sxml/.
- Переменные: нет подтверждённых ключевых переменных; см. условия доступа.
- Бесплатный старт/лимиты: Открытый XML; публичный численный SLA/лимит не подтверждён.
- РФ / Сочи: Официальный источник рублёвых курсов.
- Цены, наличие, покупка: Цены/наличие/бронирование: не применимо.
- Коммерческое использование: Указывать источник/дату; условия сайта.
- Примечание: Учитывать Nominal и дату действия. Курс ЦБ не гарантирует банковский курс оплаты.

## Дополнительный контекст без подтверждённого публичного API

Эти три группы НЕ включены в число API/MCP и не будут парситься через скрытые endpoints:

| Источник | Подтверждено | Ограничение |
|---|---|---|
| [Роза Хутор](https://rosakhutor.ru/skiing/lifts/) | Официальная страница состояния подъёмников | Публичный документированный API не найден; ссылка и ручная проверка, либо договор |
| [Красная Поляна](https://ww3.krasnayapolyanaresort.ru/) | Статусы канатных дорог на сайте курорта | Не обещать доступ к внутренним JSON; статус меняется в течение дня |
| [МЧС Краснодарского края](https://23.mchs.gov.ru/deyatelnost/press-centr/operativnaya-informaciya/shtormovye-i-ekstrennye-preduprezhdeniya/5843464) | Официальные предупреждения для Сочи/Сириуса с периодом действия | Пример относится к 16–17 октября, не текущему дню. Общий API закрытия пляжей не подтверждён |

Отсутствие предупреждения в ответе погоды не означает открытый пляж или работающий подъёмник. Источники состояния должны иметь время публикации, срок действия и ссылку.

## MCP: что подключать первым после подтверждения

1. Туту: официальный remote без ключа, сначала получить реальную схему, затем безопасный поиск.
2. 2ГИС: официальный remote и демо-ключ; POI и маршрут важнее служебного server_info.
3. LiteAPI: официальный remote только с подходящим sandbox и проверенной стоимостью; каталог ≠ доступность.
4. Mapbox / Google Maps: официальные remote, только при разрешённых регионе, тарифе и квотах.
5. AirLabs / WeatherAPI: официальные локальные MCP, предварительно проверить полный код и зафиксировать commit, отдельное окружение, минимальные права.
6. Community Aviasales: найден конкретный репозиторий, GPL, зависимости и push date; это ещё НЕ аудит безопасности. Не устанавливался.
7. OpenWeather MCP: официальный сайт ведёт на отдельный платёжный продукт; не передавать обычный ключ и не создавать аккаунт автоматически.

MCP-обёртки Booking/Viator/OpenTripMap, найденные только в каталогах, не объявляются официальными и работающими. Для OpenTripMap найден сторонний gateway без подтверждённого репозитория/лицензии — исключён из непосредственного подключения. Каталог MCP не заменяет проверку владельца, исходников, лицензии и реального tools/call.

## Выводы, влияющие на будущий эксперимент

- Реальные цены и номера Сочи пока **ни у одного** поставщика не подтверждены. Основные кандидаты: Туту, Островок/ETG; резерв Броневик, экспериментальный LiteAPI.
- Aviasales Data — вспомогательная оценка бюджета, не live quote. Search API нельзя автоматически включать в сравнение метапоисков.
- Не использовать supplier API (управление своими отелями/экскурсиями/такси) вместо demand API общего поиска.
- Для следующего этапа даты вычислять от дня запуска: +14…21 день, 4 ночи, 2 взрослых. Погодные даты отдельно ограничить реальным горизонтом API.
- Таблицы оценок 0–5, измеренные задержки, MCP tools/schema и окончательный стек появятся после этапа 2. Сейчас баллы за непроведённые проверки не выставляются.

## Уточнения по результатам тестирования

- Timepad: публичный `GET /v1/events` не требует аутентификации по [описанию метода](https://dev.timepad.ru/api/get-v1-events/); токен нужен для иных прав. Общая страница API и документация метода различаются по формулировке. В стенде предоставленный токен проверен; исходная категория self_service сохранена для общего доступа API.
- Geoapify имеет [официальный MCP](https://apidocs.geoapify.com/docs/mcp/), реально обнаружено 12 инструментов.
- Tutu: 17 инструментов, реальные поиски выполнены; временные ConnectTimeout не скрыты.
- ETG доступ исключён пользователем; LiteAPI sandbox не дал тарифов Сочи.
- Дополнительные официальные контекстные сайты, не считающиеся API: [CONTEXT_SOURCES.md](CONTEXT_SOURCES.md).
