# Backend и CLI

Для сдачи и обычного использования запускайте веб и Telegram через Docker:
[быстрый старт](../README.md#быстрый-старт). Ниже — дополнительные режимы
разработки. По умолчанию используется [автономное планирование](AUTONOMOUS_PLANNING.md):
Supervisor делегирует Transport, Stay и Experience, а Python проверяет результат.
География — Россия без фиксированного списка направлений.

## Локальный CLI

Из корня проекта, с Python 3.11+:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
.venv/bin/python chat.py --new
```

Перед диалогом нужны `MODEL`, `TOKEN`, `BASE_URL` в `.env`. Вызовы LLM и источников
используют квоты провайдеров. Docker и PostgreSQL для этого режима не нужны.
Следующий запуск без `--new` продолжает диалог. SQLite в `.travel-agent/`
используется только локальным CLI; веб и Telegram хранят данные в PostgreSQL.

Пример запроса:

> Из Москвы в Казань вдвоём на 5 ночей в следующем месяце. На билеты и отель
> до 80 тысяч рублей. Хотим прогулки и музеи.

Ответ содержит уточнение либо найденные варианты, источники и известную стоимость.
Цены заранее не заданы; при недоступности источника возможен частичный результат.

| Команда | Действие |
|---|---|
| `/show` | Показать текущий план |
| `/select 1` | Выбрать первый вариант текущей выдачи |
| `/book confirm` | Явно подтвердить имитацию оформления выбранного варианта |
| `/quit` | Выйти, сохранив диалог |

Вопросы и изменения отправляются обычным текстом: «Замени отель, билеты оставь».
Для размытого запроса агент может предложить направления; выбор направления
предшествует тарифному поиску. Обязательного ручного выбора каждого компонента
в автономном режиме нет. Прежняя схема `create_app(autonomous=False)` описана
в [истории пошагового режима](SCENARIO_PIPELINE.md).

## Веб без контейнера приложения

Нужны Docker для PostgreSQL, Python 3.11+ и Node.js 22:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
npm ci --prefix frontend
npm run build --prefix frontend
.venv/bin/python scripts/serve_web.py --local-postgres
```

До запуска заполните обязательные поля корневого `.env`, как в README.
Откройте [http://127.0.0.1:8000](http://127.0.0.1:8000). Команда создаёт таблицы
автоматически и использует настроенный `TELEGRAM_BOT_TOKEN`, если он указан.
`--telegram` вместо этого запрашивает токен скрыто для текущего процесса.
Для существующей внешней PostgreSQL задайте `TRAVEL_DATABASE_URL` и уберите
`--local-postgres`. Запускать следует один worker и один polling на токен бота.

Для React с hot reload в другом терминале выполните `npm run dev --prefix frontend`.
Vite проксирует API на `127.0.0.1:8000`. Это режим разработки; обязательный способ
сдачи — `docker compose up --build` на порту `8080`.

## API

В Compose сайт, Swagger `/docs` и `/openapi.json` доступны на
[http://localhost:8080](http://localhost:8080). Веб использует cookie-сессии.
Для внешнего CLI дополнительно задайте `TRAVEL_API_TOKEN` в окружении backend;
после изменения `.env` пересоздайте сервис `app` через `docker compose up -d app`.
Экспортируйте тот же токен в терминале клиента:

```bash
.venv/bin/python -m travel_agent --url http://localhost:8080
```

Клиент читает `TRAVEL_API_TOKEN` из окружения процесса. Bearer-токен соответствует
своему владельцу; он не становится аккаунтом, зарегистрированным через сайт.

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/health` | `{"status":"ok","persistent":true}` при PostgreSQL |
| POST | `/api/auth/register` | `{name, email, password}`, пароль от 10 символов |
| POST | `/api/auth/login` | `{email, password}`, установить cookie-сессию |
| GET | `/trips` | История аккаунта |
| POST | `/trips` | Создать поездку; ответ `{trip_id, revision}` |
| GET | `/trips/{id}` | Состояние, сообщения, предложения и заказ |
| POST | `/trips/{id}/messages` | `{message, revision}` — вопрос или изменение |
| GET | `/trips/{id}/status`, `/trips/{id}/events` | Прогресс и SSE |
| POST | `/trips/{id}/select/{choice_id}?revision=N` | Выбрать актуальное предложение |
| POST | `/trips/{id}/bookings` | `{option_id, revision, confirm, idempotency_key, payment_method}` |
| DELETE | `/trips/{id}` | Удалить свою поездку |
| GET / PUT | `/profile` | Интересы владельца Bearer/cookie-сессии |

Cookie-мутирующие запросы проверяют Origin и Sec-Fetch-Site. Чужая поездка даёт
`404`, устаревшая revision или конфликт оформления — `409`, deadline — `504`.
После таймаута прочитайте состояние перед повтором. Оформление идемпотентно по
ключу; изменение параметров с тем же ключом отклоняется.

В автономном состоянии `autonomous=true`, `options` — совместимые пакеты,
`cards` — предложения источников, `selected` — выбранный пакет, `results` —
проверенные результаты специалистов, `messages` — история. `answer` содержит
ответ, `notice` и `warnings` — ограничения. Частичный результат не означает
отсутствия всех предложений. Полная схема запросов — в OpenAPI; дополнительные
маршруты аккаунта, PDF, сопровождения и Telegram — в [WEB_AND_TELEGRAM.md](WEB_AND_TELEGRAM.md).

## Данные и ограничения

| Роль | Внешние источники |
|---|---|
| Supervisor | Нет внешних tools |
| Transport | Туту Transport, Яндекс Расписания, Travelpayouts, Tavily |
| Stay | Туту Hotel, Tavily |
| Experience | 2ГИС, Geoapify, Open-Meteo, Timepad, OpenTripMap, Tavily |

Allowlist проверяется при регистрации и перед сетевым вызовом. Tutu ID ограничены
продуктом и делегацией. Текст поставщика не меняет системные правила. Checkout,
пассажирские и платёжные методы недоступны.

Деньги передаются строкой Decimal с валютой и `basis`; неизвестная цена — `null`.
Тариф за человека умножается на состав один раз. Кэш, каталог и Tavily не
подтверждают live quote. Истёкшая котировка проверяется перед оформлением.
Изменения повышают revision и инвалидируют зависимые результаты; запоздалые
результаты прежней версии отклоняются. Лимиты автономного режима описаны
в [AUTONOMOUS_PLANNING.md](AUTONOMOUS_PLANNING.md).

Заказ содержит `simulated=true`, `paid=false`, `reserved=false`. Статус
имитации оплаты `payment.status=succeeded` не означает реального списания.
Питание, трансферы, активности и сборы могут оставаться неизвестными.
MVP рассчитан на взрослых, рубли и одну базу проживания. Детские тарифы и поездки
с несколькими отелями не заявлены; наличие и покрытие зависят от поставщиков.

## Проверки

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m pip check
npm test --prefix frontend
npm run build --prefix frontend
```

PostgreSQL-проверки дополнительно включаются через `TRAVEL_TEST_DATABASE_URL`
с отдельной тестовой БД. Live smoke требует явного разрешения и денежного бюджета;
исследовательский `scripts/run_all.py` для проверки запуска не нужен.
