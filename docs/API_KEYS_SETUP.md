> Этап 2 выполнен. Ключи из согласованного списка проверены, ETG отсутствует по решению пользователя. Актуальные отсутствующие переменные и причины пропуска — в `reports/integration_results.json`; исходные инструкции получения ключей ниже сохраняются. Timepad public events доступны без токена по документации конкретного метода.

# Получение ключей — этап 1

Проверено 25 октября 2026. `.env` не изменён. В нём найдены только заполненные `MODEL`, `TOKEN`, `BASE_URL`; все дополнительные переменные шаблона отсутствуют. Значения ключей в чат не присылайте.

## Что стоит подготовить в первую очередь

Достаточно доступной части списка — отсутствие партнёрского ключа не блокирует проверку остальных источников. Создавайте только бесплатный/demo/sandbox доступ; не включайте платные подписки, автопополнение или pay-per-call. Подтверждение «Ключи добавлены, продолжай» не будет трактоваться как неограниченное разрешение расходов.

| Переменные | Действие | Зачем |
|---|---|---|
| `TWOGIS_API_KEY` | [Platform Manager 2ГИС](https://platform.2gis.ru/) → бесплатный demo key на 30 дней; Places, Geocoder, Routing, Matrix (Static при необходимости) | Основные POI, рестораны и маршруты |
| `YANDEX_RASP_API_KEY` | [Кабинет разработчика Яндекса](https://developer.tech.yandex.ru/) → Все продукты → Ещё → API Яндекс Расписаний → Подключить → Ключи | Электрички и расписания |
| `TRAVELPAYOUTS_TOKEN`, `TRAVELPAYOUTS_MARKER` | [Travelpayouts API](https://www.travelpayouts.com/developers/api) → регистрация/вход → API token; marker из партнёрского профиля | Кэш цен Aviasales; Search API отдельно не активируется |
| `ETG_KEY_ID`, `ETG_API_KEY`, `ETG_BASE_URL` | Через организаторов хакатона/куратора Островка запросить sandbox/test Affiliate или B2B API; скопировать credentials и endpoint из настроек контракта | Приоритетный отельный поставщик, но партнёрский доступ |
| `LITEAPI_API_KEY` | [Nuitee Connect dashboard](https://dashboard.liteapi.travel/) → регистрация → sandbox key; убедиться в бесплатности тестовых endpoints | Альтернативный официальный гостиничный MCP, покрытие РФ пока неизвестно |
| `GEOAPIFY_API_KEY` | [Geoapify Projects](https://myprojects.geoapify.com/) → аккаунт → проект → API key, план Free | Резерв POI/маршрутов, commercial free с атрибуцией |
| `ORS_API_KEY` | [HeiGIT account](https://account.heigit.org/) → регистрация → бесплатный Standard key | Резерв маршрутизации |
| `OPENTRIPMAP_API_KEY` | [OpenTripMap Free](https://dev.opentripmap.org/price) → Sign up for free → ключ | Достопримечательности; free только non-commercial |
| `TIMEPAD_TOKEN` | [Timepad](https://timepad.ru/) → аккаунт; получить токен по [API документации](https://dev.timepad.ru/api/) для чтения публичных событий | Мероприятия, если scope допускает общий поиск |

Прямой публичной ссылки на создание токена Timepad в исследованных материалах не подтверждено; не заменять это выдуманным URL. Используйте [интерактивную документацию](https://api.timepad.ru/doc/interactive), раздел авторизации/получения токена; если доступ выдаёт поддержка — запросите его там.

Добавьте вручную в существующий `.env` только полученные значения:

```dotenv
TWOGIS_API_KEY=
YANDEX_RASP_API_KEY=
TRAVELPAYOUTS_TOKEN=
TRAVELPAYOUTS_MARKER=
ETG_KEY_ID=
ETG_API_KEY=
ETG_BASE_URL=
LITEAPI_API_KEY=
GEOAPIFY_API_KEY=
ORS_API_KEY=
OPENTRIPMAP_API_KEY=
TIMEPAD_TOKEN=
```

Пустые строки выше — места для заполнения, не готовые ключи. `ETG_BASE_URL` — адрес, не секрет, но он должен соответствовать типу ключа. Не менять `MODEL`, `TOKEN`, `BASE_URL` и не копировать `.env.example` поверх `.env`.

## Все остальные ключи и способы доступа

Для сервисов без публично подтверждённой схемы credentials сначала получите документацию в партнёрском кабинете. Не требуется придумывать значения, покупать тариф или регистрироваться во всех сервисах ради числа интеграций. В каталоге приведены технические возможности и ограничения; ниже — действия получения доступа для каждой записи с ключом/партнёрским барьером.

### Aviasales / Travelpayouts Data API (P1)

[Страница начала подключения](https://www.travelpayouts.com/developers/api) · [Документация](https://github.com/travelpayouts/api-docs).

Переменные: `TRAVELPAYOUTS_TOKEN`, `TRAVELPAYOUTS_MARKER`.

Зарегистрироваться, получить API token и партнёрский marker. Это доступ к кэшу, не к live Search.

Лимиты/затраты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.

### Aviasales Search API (P3)

[Страница начала подключения](https://support.travelpayouts.com/hc/en-us/requests/new) · [Документация](https://support.travelpayouts.com/hc/en-us/articles/34788165535250-Search-API-usage-rules).

Переменные: `TRAVELPAYOUTS_TOKEN`, `TRAVELPAYOUTS_MARKER`.

Подать отдельную заявку в поддержку, получить актуальные требования и согласовать сценарий. Не запускать пакетные сравнения с другими метапоисками.

Лимиты/затраты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.

### stufently/aviasales-mcp (обёртка Data API) (P2)

[Страница начала подключения](https://www.travelpayouts.com/developers/api) · [Документация](https://github.com/stufently/aviasales-mcp).

Переменные: `TRAVELPAYOUTS_TOKEN`.

Использует тот же TRAVELPAYOUTS_TOKEN, отдельный ключ не нужен. Перед запуском аудит кода, зафиксированный commit, отдельный venv; не выполнять uvx/npx latest вслепую.

Лимиты/затраты: Лимиты upstream Data API.

### Duffel Flights (P3)

[Страница начала подключения](https://app.duffel.com/join) · [Документация](https://duffel.com/docs/api/overview/test-your-integration).

Переменные: `DUFFEL_ACCESS_TOKEN`.

Создать аккаунт, в dashboard создать test access token. Live business verification отложить; тестовая цена не считается реальной.

Лимиты/затраты: Test mode; live коммерческие условия: https://duffel.com/pricing.

### Aviationstack (P2)

[Страница начала подключения](https://aviationstack.com/signup/free) · [Документация](https://aviationstack.com/documentation).

Переменные: `AVIATIONSTACK_API_KEY`.

Выбрать Free, получить Access Key в dashboard; проверить, что тариф не сменился на платный. 100 запросов/месяц, некоммерческий режим.

Лимиты/затраты: Free: 100 запросов/месяц, non-commercial; HTTPS указан на https://aviationstack.com/pricing.

### AirLabs (P2)

[Страница начала подключения](https://airlabs.co/signup) · [Документация](https://airlabs.co/docs/).

Переменные: `AIRLABS_API_KEY`.

Создать аккаунт, получить API key; записать оставшуюся бесплатную квоту и доступные endpoints. MCP использует тот же upstream key.

Лимиты/затраты: Бесплатный ключ заявлен; точную квоту проверить в кабинете.

### Amadeus (P3)

[Страница начала подключения](https://developers.amadeus.com/) · [Документация](https://developers.amadeus.com/).

Переменные пока не определены: сначала выданная поставщиком спецификация доступа.

Не заполнять старые AMADEUS_CLIENT_ID/SECRET по устаревшим tutorials. Официальный Python SDK архивирован, актуальная self-service регистрация не подтверждена. Уточнять Enterprise у поставщика.

Лимиты/затраты: Новый Self-Service доступ не подтверждён; старые инструкции регистрации не использовать.

### MixVel (P2)

[Страница начала подключения](https://mixvel.com/) · [Документация](https://docs.mixvel.com/api/).

Переменные пока не определены: сначала выданная поставщиком спецификация доступа.

Через официальный сайт запросить агентское подключение, sandbox и credentials по актуальной NDC/XML документации. Не подставлять произвольные token URL.

Лимиты/затраты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.

### Сирена-Трэвел (P2)

[Страница начала подключения](https://www.sirena-travel.ru/) · [Документация](https://www.sirena-travel.ru/pomoshh-i-obsluzhivanie/).

Переменные пока не определены: сначала выданная поставщиком спецификация доступа.

Через официальный сайт запросить агентский договор/техническую спецификацию; публичной self-service выдачи ключей не подтверждено.

Лимиты/затраты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.

### Островок / Emerging Travel Group (P0)

[Страница начала подключения](https://ostrovok.ru/affiliate/) · [Документация](https://docs-api.ostrovok.ru/).

Переменные: `ETG_KEY_ID`, `ETG_API_KEY`, `ETG_BASE_URL`.

Запросить тестовый ключ у куратора/организаторов. После выдачи открыть Настройки контракта → API. ID ключа = Basic Auth login, токен = password. Взять endpoint для своего окружения. Для live требуется сертификация; test inventory не доказывает цены на Сочи.

Лимиты/затраты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.

### Nuitee Connect / LiteAPI (P1)

[Страница начала подключения](https://dashboard.liteapi.travel/) · [Документация](https://docs.liteapi.travel/reference/mcp-server).

Переменные: `LITEAPI_API_KEY`.

В dashboard создать sandbox key; проверить условия и оставшиеся бесплатные квоты. Для REST X-API-Key, для MCP документирован query apiKey; URL с ключом не сохранять в отчёт.

Лимиты/затраты: MCP docs: default 500 requests/sec; это rate limit, НЕ бесплатная квота. Billing по endpoints.

### Booking.com Demand API (P3)

[Страница начала подключения](https://developers.booking.com/demand/docs) · [Документация](https://developers.booking.com/demand/docs/getting-started/prerequisites).

Переменные: `BOOKING_API_KEY`, `BOOKING_AFFILIATE_ID`.

Подать заявку Managed Affiliate Partner, подписать соглашение, получить Partner Centre от менеджера. В нём создать token и взять X-Affiliate-Id. Для Сочи ключ не нужен: источник исключён из MVP.

Лимиты/затраты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.

### Expedia Rapid (P3)

[Страница начала подключения](https://partner.expediagroup.com/en-us/solutions/build-your-travel-experience/rapid-api) · [Документация](https://developers.expediagroup.com/rapid/setup).

Переменные: `EXPEDIA_API_KEY`, `EXPEDIA_SHARED_SECRET`.

Заявка Rapid → менеджер → тестовые credentials (API key и shared secret) → review перед production. Для MVP Сочи не приоритет.

Лимиты/затраты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.

### Hotelbeds / HBX (P3)

[Страница начала подключения](https://developer.hotelbeds.com/) · [Документация](https://developer.hotelbeds.com/documentation/getting-started/).

Переменные: `HOTELBEDS_API_KEY`, `HOTELBEDS_SECRET`.

В developer portal нажать регистрацию Free API Key, выбрать Hotel suite. Скопировать Key и Secret; evaluation только 50 запросов/день. Production не включать.

Лимиты/затраты: Evaluation: 50 запросов/день; production после сертификации.

### Броневик (P1)

[Страница начала подключения](https://bronevik.com/ru/api-solutions) · [Документация](https://bronevik.com/ru/api-solutions).

Переменные пока не определены: сначала выданная поставщиком спецификация доступа.

Оставить заявку на API solutions, указать demand-поиск/продажу отелей; запросить договор, sandbox, SOAP schema и credentials. Точные имена env добавить после выдачи схемы.

Лимиты/затраты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.

### Яндекс Расписания (P0)

[Страница начала подключения](https://developer.tech.yandex.ru/) · [Документация](https://yandex.ru/dev/rasp/doc/ru/concepts/access).

Переменные: `YANDEX_RASP_API_KEY`.

Кабинет разработчика → API Яндекс Расписаний → Подключить → Ключи. В запросах предпочтителен Authorization header, а не URL query.

Лимиты/затраты: Числовые лимиты и разрешённый сценарий сверить с условиями продукта.

### UFS.travel (P2)

[Страница начала подключения](https://www.ufs-partner.ru/) · [Документация](https://www.ufs-partner.ru/).

Переменные пока не определены: сначала выданная поставщиком спецификация доступа.

Через официальный партнёрский сайт запросить API для ж/д/автобусов, договор, sandbox и документацию авторизации.

Лимиты/затраты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.

### Kiwitaxi (P2)

[Страница начала подключения](https://kiwitaxi.com/en/partner/) · [Документация](https://kiwitaxi.com/en/partner/webmaster/instructions/).

Переменные пока не определены: сначала выданная поставщиком спецификация доступа.

Зарегистрироваться как партнёр/webmaster и уточнить API-доступ у менеджера. Реферальная ссылка не является live quotation API.

Лимиты/затраты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.

### Intui.travel (P2)

[Страница начала подключения](https://en.intui.travel/) · [Документация](https://en.intui.travel/).

Переменные пока не определены: сначала выданная поставщиком спецификация доступа.

Через Get API Intui на клиентском сайте запросить buyer API и sandbox. Не запрашивать fleet/supplier API IN.

Лимиты/затраты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.

### 2ГИС (P0)

[Страница начала подключения](https://platform.2gis.ru/) · [Документация](https://docs.2gis.com/en/api/ai/mcp-server/cloud).

Переменные: `TWOGIS_API_KEY`.

Оформить demo key 30 дней с Places, Geocoder, Routing, Matrix. В официальном MCP передавать Bearer или X-2GIS-API-Key.

Лимиты/затраты: Демо 30 дней с ограничениями; точная квота в кабинете.

### Google Maps / Maps Grounding Lite (P2)

[Страница начала подключения](https://console.cloud.google.com/apis/credentials) · [Документация](https://developers.google.com/maps/ai/grounding-lite).

Переменные: `GOOGLE_MAPS_API_KEY`.

Создать Cloud project, включить Maps Grounding Lite и нужные API, создать ограниченный API key в Credentials. Сначала использовать документированный demo-путь, если доступен. Если регион/платёжные условия не подходят — пропустить, не обходить.

Лимиты/затраты: Demo key для прототипа документирован; production billing/SKU квоты проверить.

### Mapbox (P2)

[Страница начала подключения](https://account.mapbox.com/) · [Документация](https://github.com/mapbox/mcp-server).

Переменные: `MAPBOX_ACCESS_TOKEN`.

Зарегистрироваться в account.mapbox.com, создать ограниченный access token; сверить доступные бесплатные квоты по API. При billing-барьере пропустить.

Лимиты/затраты: Квоты различаются по API: https://www.mapbox.com/pricing; не универсальный free limit.

### OpenRouteService / HeiGIT (P1)

[Страница начала подключения](https://account.heigit.org/) · [Документация](https://openrouteservice.org/).

Переменные: `ORS_API_KEY`.

Создать HeiGIT account, получить бесплатный Standard key. Основной сайт сообщает проблему PHP, но даёт ссылку на действующий кабинет.

Лимиты/затраты: Бесплатный Standard key; актуальные квоты в новом кабинете. Старый /plans возвращает 404.

### GraphHopper (P2)

[Страница начала подключения](https://graphhopper.com/dashboard/#/signup) · [Документация](https://docs.graphhopper.com/).

Переменные: `GRAPHHOPPER_API_KEY`.

Зарегистрироваться в dashboard, создать API key Free; free non-commercial. Платный план не включать.

Лимиты/затраты: Free для non-commercial; квоты на https://www.graphhopper.com/pricing/.

### Geoapify (P1)

[Страница начала подключения](https://myprojects.geoapify.com/) · [Документация](https://apidocs.geoapify.com/).

Переменные: `GEOAPIFY_API_KEY`.

Создать проект на Free, скопировать key; 3000 credits/day. Запретить автоматический платный upgrade.

Лимиты/затраты: Free 3000 credits/day, до 5 requests/sec; credits не всегда равны requests.

### GeoNames (P2)

[Страница начала подключения](https://www.geonames.org/login) · [Документация](https://www.geonames.org/export/web-services.html).

Переменные: `GEONAMES_USERNAME`.

Зарегистрироваться, подтвердить email, включить Free Web Services в профиле; указать username, не пароль.

Лимиты/затраты: Кредиты по методу: https://www.geonames.org/export/credits.html; квоты сверить в аккаунте.

### Timepad (P1)

[Страница начала подключения](https://timepad.ru/) · [Документация](https://dev.timepad.ru/api/).

Переменные: `TIMEPAD_TOKEN`.

Получить read-only токен по dev.timepad.ru/api и интерактивной документации. Не использовать доступ к персональным данным участников.

Лимиты/затраты: 60 запросов/IP/мин; при превышении следующая минута блокируется.

### OpenTripMap (P1)

[Страница начала подключения](https://dev.opentripmap.org/price) · [Документация](https://dev.opentripmap.org/product).

Переменные: `OPENTRIPMAP_API_KEY`.

Sign up for free на dev.opentripmap.org; получить API key. 5000/day, 10/sec; non-commercial.

Лимиты/затраты: Free: 5000/day, 10/sec, non-commercial.

### Sputnik8 (P1)

[Страница начала подключения](https://www.sputnik8.com/ru/affiliate/new) · [Документация](https://www.sputnik8.com/doc/api/v1/cities.html).

Переменные: `SPUTNIK_API_KEY`, `SPUTNIK_USERNAME`.

Подключить партнёрскую программу; запросить персональные API key и username, условия каталога/расписания/ссылок. Не копировать общие credentials из документационных примеров.

Лимиты/затраты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.

### Tripster affiliate API (P1)

[Страница начала подключения](https://experience.tripster.ru/partner/) · [Документация](https://tripster.atlassian.net/wiki/spaces/affiliates/pages/3688235009).

Переменные: `TRIPSTER_PARTNER_ID`.

Вступить в партнёрскую программу, получить partner ID и доступ к закрытой API-документации. Уточнить актуальную авторизацию. Token для guides orders не заменяет affiliate API.

Лимиты/затраты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.

### Viator Partner API (P3)

[Страница начала подключения](https://partnerresources.viator.com/) · [Документация](https://docs.viator.com/partner-api/technical/).

Переменные: `VIATOR_API_KEY`.

Подать заявку на affiliate/merchant API через Partner Resources. Уточнить content vs availability vs booking, получить API key после одобрения. До подтверждения РФ не приоритет.

Лимиты/затраты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.

### GetYourGuide (P3)

[Страница начала подключения](https://partner.getyourguide.com/) · [Документация](https://partner.getyourguide.support/hc/en-us/articles/13981133907613-API-integration-and-requirements).

Переменные пока не определены: сначала выданная поставщиком спецификация доступа.

Регистрация партнёра не гарантирует API. Basic требует 100k посещений/месяц или 50k app downloads; Reading — существенно выше. Схему credentials получить только при одобрении.

Лимиты/затраты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.

### Qtickets (P3)

[Страница начала подключения](https://qtickets.ru/) · [Документация](https://qtickets.help/article/rest-api/).

Переменные: `QTICKETS_TOKEN`.

Только для собственного кабинета продавца: Настройки → Основное → токен API. Не создавать организацию ради мнимого доступа к афише всего города.

Лимиты/затраты: Публичный численный лимит не подтверждён; проверить кабинет/договор до запросов.

### PRO.Культура.РФ export API (P1)

[Страница начала подключения](https://pro.culture.ru/) · [Документация](https://pro.culture.ru/documentation/export_API_PRO.pdf).

Переменные: `CULTURE_API_KEY`.

Запросить инфопартнёрский экспорт у partners@team.culture.ru, получить ключ и действующую спецификацию. Сообщения никому автоматически не отправлялись.

Лимиты/затраты: По партнёрскому доступу.

### WeatherAPI (P2)

[Страница начала подключения](https://www.weatherapi.com/signup.aspx) · [Документация](https://www.weatherapi.com/docs/).

Переменные: `WEATHERAPI_KEY`.

Выбрать Free, взять API key из аккаунта. Записать в WEATHERAPI_KEY — это имя, ожидаемое официальным MCP.

Лимиты/затраты: Free: 100k/month, forecast 3 дня: https://www.weatherapi.com/pricing.

### OpenWeather REST / MCP for agents (P2)

[Страница начала подключения](https://home.openweathermap.org/users/sign_up) · [Документация](https://openweathermap.org/api).

Переменные: `OPENWEATHER_API_KEY`.

Создать обычный REST аккаунт, получить ключ в API keys. Не подключать One Call/pay-per-call. Официальный MCP for agents имеет отдельную регистрацию и funded balance; его секреты пока НЕ нужны.

Лимиты/затраты: Бесплатные REST продукты по подписке; One Call pay-per-call, не подключать автоматически.

## Где ключи не требуются

Туту MCP, Open-Meteo Forecast/Marine/Air Quality/Elevation (исследовательский open-access), Overpass, Nominatim, KudaGo, Wikidata, XML ЦБ. OSM доступен как открытые данные, OSRM имеет demo/self-hosted путь, Go deeplink формируется локально. Это **документальный статус**, не успешные тесты. Для коммерческого Open-Meteo потребуется отдельная подписка позже.

## Повторение проверки окружения

PyCharm: выбрать interpreter `<проект>/.venv/bin/python`. Исходный shell указывал на venv другого проекта; он не изменялся.

Первичная установка с зафиксированными версиями (Python 3.13.7 использован в исследовании):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
```

Одна команда безопасной инвентаризации, без платной генерации и без туристических API:

```bash
.venv/bin/python scripts/check_environment.py
```

Точное повторение одного минимального LLM-теста — **дополнительный потенциально платный запрос**, запускать осознанно:

```bash
.venv/bin/python scripts/check_environment.py --llm-smoke
```

Проверяется только существующий OpenRouter endpoint, не меняются значения MODEL/TOKEN/BASE_URL. Raw responses, Authorization, exception text и ключи не логируются. Smoke сохраняет лишь статус, проверку OK, latency и usage. Нет retries платного POST. Для остальных этапов единая команда сценариев будет создана после подтверждения; сейчас нельзя выдавать её за готовые интеграционные тесты.

## Точка остановки

Этап 2 не запущен. После добавления полученных ключей напишите: **«Ключи добавлены, продолжай»**. Если конкретному ключу доступна только платная квота, не разрешённая отдельно, такой источник будет пропущен. Бронирования и покупки запрещены независимо от наличия credentials.
