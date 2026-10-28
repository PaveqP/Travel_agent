import asyncio
import contextlib
import logging
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import quote

import httpx

from travel_agent.accounts import AccountProfile
from travel_agent.config import environment
from travel_agent.support import GUIDES
from travel_agent.tools import public_url

LOGGER = logging.getLogger(__name__)
BOT_NAME = "ostrovok_helper_ryadom_bot"
PROGRESS_INTERVAL = 15
STAGES = {"scenarios": "Идея поездки", "transport": "Билеты", "stays": "Проживание", "itinerary": "Программа", "review": "Проверка и оплата", "booked": "Поездка собрана"}
COMMANDS = [
    ("start", "Начать и открыть меню"), ("new", "Новая поездка"), ("trips", "История поездок"),
    ("show", "Текущий план и варианты"), ("plan", "Полные варианты поездки"),
    ("hotels", "Отели и фотографии"), ("tickets", "Билеты туда и обратно"),
    ("history", "Переписка с агентом"), ("cancel", "Отменить ввод"), ("back", "Вернуться на шаг назад"), ("profile", "Личный кабинет"),
    ("pay", "Проверить имитацию оплаты"), ("pdf", "Скачать маршрутный лист"),
    ("track", "План и отметки по поездке"), ("map", "Отель и места на карте"), ("help", "Помощь и шаблоны писем"),
    ("site", "Продолжить на сайте с теми же поездками"),
    ("orders", "Сохранённые имитационные заказы"),
]


def split_text(text: str, limit: int = 3800) -> list[str]:
    chunks = []
    while text:
        units = 0
        end = 0
        for char in text:
            size = 2 if ord(char) > 0xFFFF else 1
            if units + size > limit:
                break
            units += size
            end += 1
        if end < len(text):
            boundary = text.rfind("\n", 0, end)
            if boundary > end // 2:
                end = boundary + 1
        chunks.append(text[:end])
        text = text[end:]
    return chunks or ["Готово"]


def safe_url(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return value if public_url(value) else None
    except ValueError:
        return None


def money(value: str | Decimal | None, currency: str = "RUB") -> str:
    if value is None:
        return "уточняется"
    return f"{Decimal(str(value)):,.2f}".replace(",", " ").replace(".", ",") + (" ₽" if currency == "RUB" else " " + currency)


def trip_summary(state: dict) -> str:
    trip = state.get("constraints", {})
    lines = [f"{trip.get('origin') or 'Город отправления уточняется'} → {trip.get('destination', 'Россия')}"]
    if trip.get("start") or trip.get("travel_month"):
        lines.append(f"{trip.get('start') or trip.get('travel_month')} — {trip.get('end') or 'даты уточняются'}")
    if trip.get("adults"):
        lines.append(f"Взрослых: {trip['adults']}")
    if trip.get("budget"):
        lines.append("Бюджет: " + money(trip["budget"]) + (" на человека" if trip.get("budget_basis") == "person" else " на всех"))
    return " · ".join(lines)


def offers(state: dict, kind: str) -> list[dict]:
    if kind == "p":
        return state.get("options", [])
    if kind == "s":
        return state.get("scenarios") or state.get("choices", [])
    role = "stays" if kind == "h" else "transport"
    candidates = state.get("results", {}).get(role, {}).get("candidates", [])
    if state.get("focus") == role and state.get("cards"):
        by_id = {c["id"]: c for c in candidates}
        return [{**card, **by_id.get(card["id"], {})} for card in state["cards"] if card.get("kind") == role]
    items = [o.get("stay" if kind == "h" else "transport") for o in state.get("options", [])]
    items.extend(candidates)
    return list({item["id"]: item for item in items if item}.values())


def scenario_text(item: dict) -> str:
    return "\n".join(filter(None, [item.get("title", "Идея поездки"), item.get("destination"), item.get("purpose") or item.get("details"),
                                      ", ".join(item.get("interests", [])), item.get("tradeoff"), "Цены и наличие ещё не проверены."]))


def candidate_text(item: dict, *, detailed: bool = False) -> str:
    role = item.get("role") or item.get("kind")
    dates = item.get("dates", item)
    source = item.get("source", {})
    lines = [item.get("name") or item.get("title", "Предложение")]
    if role == "transport":
        legs = item.get("legs") or [
            {"origin": item.get("origin"), "destination": item.get("destination"), "departure_at": dates.get("departure_at"),
             "arrival_at": dates.get("arrival_at"), "start": dates.get("start"), "duration_minutes": item.get("duration_minutes"), "transfers": item.get("transfers")},
            {"origin": item.get("destination"), "destination": item.get("origin"), "departure_at": item.get("return_departure_at") or dates.get("return_departure_at"),
             "arrival_at": item.get("return_arrival_at"), "start": dates.get("end")}]
        if len(legs) == 1:
            legs = [*legs, {"origin": item.get("destination"), "destination": item.get("origin"), "start": dates.get("end"),
                            "departure_at": item.get("return_departure_at"), "arrival_at": item.get("return_arrival_at")}]
        for index, leg in enumerate(legs):
            departure = (leg.get("departure_at") or leg.get("start") or "время уточняется").replace("T", " ")
            arrival = (leg.get("arrival_at") or "время уточняется").replace("T", " ")
            lines.append(f"{'Туда' if index == 0 else 'Обратно' if index == 1 else 'Сегмент'}: {leg.get('origin') or '?'} → {leg.get('destination') or '?'}\n{departure} → {arrival} (местное время)")
            if leg.get("duration_minutes") is not None:
                lines.append(f"В пути: {leg['duration_minutes']} мин")
            if leg.get("transfers") is not None:
                lines.append(f"Пересадок: {leg['transfers']}")
        lines.append("Багаж: " + {True: "включён", False: "не включён", None: "условия уточняются"}[item.get("baggage_included")])
    else:
        lines.append(f"Проживание: {dates.get('start') or '?'} — {dates.get('end') or '?'}" if role == "stays" else "Место программы")
        if item.get("stars") is not None:
            lines.append(f"Звёзд: {item['stars']}")
        if item.get("rating") is not None:
            lines.append(f"Рейтинг: {item['rating']}/10" + (f" · отзывов: {item['review_count']}" if item.get("review_count") is not None else ""))
        if item.get("address") or item.get("area"):
            lines.append(item.get("address") or item["area"])
        if detailed and item.get("amenities"):
            lines.append("Услуги: " + ", ".join(item["amenities"]))
    price = item.get("price")
    basis = {"party": "за всех и весь период", "person": "на человека", "ticket": "за билет", "room_stay": "за проживание", "unknown": "основа цены не подтверждена"}
    lines.append("Цена: " + (money(price["amount"], price["currency"]) + " · " + basis.get(price.get("basis"), basis["unknown"]) if price else "источник не указал"))
    if item.get("adults"):
        lines.append(f"Цена для взрослых: {item['adults']}")
    evidence = source.get("evidence") or item.get("evidence")
    lines.append("Источник: " + (source.get("provider") or item.get("aggregator") or item.get("provider") or "уточняется"))
    lines.append("Поисковая котировка; резерв не подтверждён." if evidence == "live" else "Справочные данные; цена и наличие требуют проверки.")
    expires = source.get("expires_at")
    if expires and datetime.fromisoformat(expires) <= datetime.now(timezone.utc):
        lines.append("Цена устарела. Обновите поиск перед выбором.")
    warnings = {"over_budget": "Цена выше вашего бюджета.", "alternate_dates": "Вариант на соседние даты.",
                "different_party": "Цена для другого состава гостей.", "required_baggage_unverified": "Требуемый багаж не подтверждён.",
                "direct_flight_unverified": "Прямой рейс не подтверждён.", "outside_search_window": "Даты вне текущего диапазона.",
                "different_area": "Другой район.", "different_hotel": "Отель отличается от запрошенного."}
    lines.extend(warnings[w] for w in item.get("warnings", []) if w in warnings)
    if detailed:
        if item.get("description"):
            lines.append(item["description"])
        if source.get("retrieved_at") or item.get("retrieved_at"):
            lines.append("Данные получены: " + (source.get("retrieved_at") or item["retrieved_at"]))
        if item.get("conditions"):
            labels = {"fare_family": "Тариф", "baggage": "Багаж", "refund": "Возврат", "cancellation": "Отмена", "meal": "Питание"}
            for key, value in item["conditions"].items():
                if key in labels and value is not None:
                    lines.append(labels[key] + ": " + str(value))
        url = safe_url(item.get("url") or source.get("source_url"))
        if url:
            lines.append(url)
    return "\n".join(lines)


def fresh_quote(item: dict) -> bool:
    source = item.get("source", {})
    expires = source.get("expires_at")
    return item.get("price") is not None and source.get("evidence") == "live" and bool(expires) and datetime.fromisoformat(expires) > datetime.now(timezone.utc)


def checkout_available(option: dict, state: dict) -> bool:
    return option.get("revision") == state.get("revision") and all(fresh_quote(option.get(key) or {}) for key in ("transport", "stay"))


def package_text(option: dict, state: dict, *, detailed: bool = False) -> str:
    transport, stay = option.get("transport"), option.get("stay")
    budget = option.get("budget", {})
    lines = [("✓ Выбранный план" if option["id"] == state.get("selected") else "План поездки"),
             "Билеты: " + (transport["name"] if transport else "пока не найдены"),
             "Отель: " + (stay["name"] if stay else "пока не найден"),
             "Известная сумма: " + money(budget.get("known_subtotal"), budget.get("currency", "RUB")) + " за всех"]
    adults = state.get("constraints", {}).get("adults")
    if adults and budget.get("known_subtotal") is not None:
        lines.append("На человека: " + money(Decimal(str(budget["known_subtotal"])) / adults, budget.get("currency", "RUB")))
    if transport:
        lines.append(f"Поездка: {transport.get('start') or '?'} — {transport.get('end') or '?'}")
    if stay:
        lines.append(f"Проживание: {stay.get('start') or '?'} — {stay.get('end') or '?'}")
    if detailed:
        for item in (transport, stay):
            if item:
                lines.append("\n" + candidate_text(item, detailed=True))
    days = option.get("days", [])
    if days:
        lines.append("\nПрограмма по дням:")
        for day in days if detailed else days[:3]:
            places = ", ".join(c["name"] for c in day.get("candidates", [])) or "Дорога / свободное время"
            lines.append(day["date"] + ": " + places)
            if detailed:
                for place in day.get("candidates", []):
                    url = safe_url(place.get("url") or place.get("source", {}).get("source_url"))
                    if url:
                        lines.append(url)
                lines.extend(day.get("warnings", []))
        if not detailed and len(days) > 3:
            lines.append("Все дни — в подробностях плана.")
    if detailed:
        lines.extend(option.get("warnings", []))
    lines.append("Питание, местный транспорт, активности и сборы не включены. Полная стоимость неизвестна. Покупка — только имитация.")
    return "\n".join(lines)


class TelegramError(RuntimeError):
    def __init__(self, message: str, status: int = 0, retry_after: int = 3):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


class TelegramBot:
    def __init__(self, app, client: httpx.AsyncClient, token: str):
        self.app = app
        self.client = client
        self.base = "https://api.telegram.org/bot" + token + "/"
        self.ready = False
        self.username = BOT_NAME

    async def call(self, method: str, data: dict, document: bytes | None = None):
        if method not in {"getMe", "getWebhookInfo", "getUpdates", "setMyCommands", "sendMessage", "sendDocument", "sendPhoto", "answerCallbackQuery"}:
            raise ValueError("Unsupported Telegram method")
        for attempt in range(2):
            if document is not None:
                response = await self.client.post(self.base + method, data=data, files={"document": ("ostrovok-itinerary.pdf", document, "application/pdf")})
            else:
                response = await self.client.post(self.base + method, json=data)
            try:
                payload = response.json()
            except ValueError:
                raise TelegramError("Telegram invalid JSON", response.status_code if response.status_code >= 400 else 502) from None
            if isinstance(payload, dict) and payload.get("ok"):
                return payload.get("result")
            status = payload.get("error_code", response.status_code) if isinstance(payload, dict) else response.status_code
            parameters = payload.get("parameters") if isinstance(payload, dict) else None
            retry_after = parameters.get("retry_after", 3) if isinstance(parameters, dict) else 3
            retry_after = retry_after if isinstance(retry_after, int) else 3
            if status == 429 and attempt == 0 and 0 < retry_after <= 30:
                await asyncio.sleep(retry_after)
                continue
            raise TelegramError(f"Telegram HTTP {status}", status, retry_after)

    async def send(self, chat_id: int, text: str, buttons: list[list[dict]] | None = None) -> None:
        chunks = split_text(text)
        for index, chunk in enumerate(chunks):
            data = {"chat_id": chat_id, "text": chunk, "link_preview_options": {"is_disabled": True}}
            if buttons and index == len(chunks) - 1:
                data["reply_markup"] = {"inline_keyboard": buttons}
            await self.call("sendMessage", data)

    @staticmethod
    def button(label: str, action: str) -> dict:
        if len(action.encode()) > 64:
            raise ValueError("Telegram callback is too long")
        return {"text": label[:60], "callback_data": action}

    async def acknowledge(self, callback: dict) -> None:
        try:
            await self.call("answerCallbackQuery", {"callback_query_id": callback["id"]})
        except TelegramError as exc:
            if exc.status != 400:
                raise

    async def poll(self) -> None:
        pending: dict[int, asyncio.Task] = {}
        chats: dict[int, asyncio.Task] = {}
        slots = asyncio.Semaphore(8)

        async def process(update: dict, previous: asyncio.Task | None) -> None:
            if previous:
                await previous
            async with slots:
                try:
                    await self.handle(update, acknowledge=False)
                except (TelegramError, httpx.HTTPError) as exc:
                    LOGGER.warning("telegram update skipped outcome=%s", type(exc).__name__)

        try:
            while True:
                try:
                    identity = await self.call("getMe", {})
                    if not isinstance(identity, dict) or not identity.get("username"):
                        raise TelegramError("Invalid bot identity")
                    self.username = identity["username"]
                    webhook = await self.call("getWebhookInfo", {})
                    if webhook.get("url"):
                        raise TelegramError("Existing webhook prevents polling; it was preserved")
                    await self.call("setMyCommands", {"commands": [{"command": key, "description": label} for key, label in COMMANDS]})
                    break
                except httpx.TransportError:
                    LOGGER.warning("telegram startup outcome=network_error; reconnecting")
                except TelegramError as exc:
                    if exc.status != 429 and exc.status < 500:
                        raise
                    LOGGER.warning("telegram startup outcome=temporary_error status=%s", exc.status)
                    await asyncio.sleep(min(max(exc.retry_after, 1), 30))
                    continue
                await asyncio.sleep(3)
            self.ready = True
            offset = await self.app.state.accounts.bot_offset()
            while True:
                for update_id, task in list(pending.items()):
                    if not task.done():
                        break
                    await task
                    offset = update_id + 1
                    await self.app.state.accounts.bot_offset(offset)
                    del pending[update_id]
                chats = {key: task for key, task in chats.items() if not task.done()}
                try:
                    updates = await self.call("getUpdates", {"offset": offset, "timeout": 25, "limit": 100, "allowed_updates": ["message", "callback_query"]})
                    if not isinstance(updates, list):
                        raise TelegramError("Telegram invalid updates")
                    added = False
                    for update in updates:
                        update_id = int(update["update_id"])
                        if update_id in pending or update_id < offset:
                            continue
                        if len(pending) >= 32:
                            break
                        callback = update.get("callback_query")
                        if callback:
                            await self.acknowledge(callback)
                        message = callback.get("message", {}) if callback else update.get("message", {})
                        chat_id = message.get("chat", {}).get("id", 0)
                        task = asyncio.create_task(process(update, chats.get(chat_id)))
                        pending[update_id] = chats[chat_id] = task
                        added = True
                    if pending and not added:
                        running = [task for task in pending.values() if not task.done()]
                        if running:
                            await asyncio.wait(running, timeout=1, return_when=asyncio.FIRST_COMPLETED)
                except httpx.TransportError:
                    LOGGER.warning("telegram outcome=network_error")
                    await asyncio.sleep(3)
                except TelegramError as exc:
                    if exc.status != 429 and exc.status < 500:
                        raise
                    LOGGER.warning("telegram outcome=temporary_error status=%s", exc.status)
                    await asyncio.sleep(min(max(exc.retry_after, 1), 30))
        except (TelegramError, httpx.HTTPError) as exc:
            LOGGER.error("telegram stopped outcome=%s", str(exc) if isinstance(exc, TelegramError) else type(exc).__name__)
        finally:
            self.ready = False
            for task in pending.values():
                task.cancel()
            await asyncio.gather(*pending.values(), return_exceptions=True)

    async def stop(self, task: asyncio.Task) -> None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def handle(self, update: dict, *, acknowledge: bool = True) -> None:
        callback = update.get("callback_query")
        message = callback.get("message", {}) if callback else update.get("message", {})
        actor = (callback or message).get("from", {})
        chat = message.get("chat", {})
        if chat.get("type") != "private" or not isinstance(actor.get("id"), int) or chat.get("id") != actor["id"]:
            return
        chat_id = actor["id"]
        text = message.get("text", "") if not callback else ""
        if not isinstance(text, str) or len(text) > 4000:
            await self.send(chat_id, "Отправьте текст до 4000 символов.")
            return
        if callback and acknowledge:
            await self.acknowledge(callback)
        if not callback and not text.strip():
            await self.send(chat_id, "Пока понимаю текстовые сообщения. Напишите запрос или откройте /show.")
            return
        link = text.removeprefix("/start link_") if text.startswith("/start link_") else None
        try:
            user = await self.app.state.accounts.telegram_owner(chat_id, actor.get("first_name", "Путешественник"), link)
        except ValueError as exc:
            await self.send(chat_id, str(exc))
            return
        token = await self.app.state.accounts.session(user)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://telegram.internal", headers={"Authorization": "Bearer " + token}, timeout=430) as api:
                await self.interact(api, chat_id, user, text, callback.get("data", "") if callback else None)
        except (httpx.HTTPError, TelegramError) as exc:
            LOGGER.warning("telegram update outcome=%s", type(exc).__name__)
            with contextlib.suppress(TelegramError, httpx.HTTPError):
                await self.send(chat_id, "Связь прервалась. Сохранённый план доступен через /show. Перед повтором проверьте результат.")
        finally:
            await self.app.state.accounts.revoke(token)

    async def request(self, api: httpx.AsyncClient, chat_id: int, method: str, path: str, **kwargs) -> dict | list | bytes | None:
        response = await api.request(method, path, **kwargs)
        if response.status_code >= 400:
            messages = {401: "Сессия завершена. Начните с /start.", 404: "Эта поездка недоступна. Откройте /trips.",
                        409: "План или котировки изменились. Откройте /show и выберите актуальный вариант. Обновить поиск можно сообщением агенту.",
                        422: "Проверьте введённые данные.", 504: "Поиск занял больше времени. Откройте /show перед повтором."}
            await self.send(chat_id, messages.get(response.status_code, "Не удалось выполнить действие. Повторите позднее."))
            return None
        if response.headers.get("content-type", "").startswith("application/pdf"):
            return response.content
        return response.json() if response.content else {}

    def navigation(self, trip_id: str, state: dict) -> list[list[dict]]:
        rows = [[self.button("🧳 Планы", "plan"), self.button("🏨 Отели", "hotels"), self.button("🎫 Билеты", "tickets")]]
        if state.get("stage") == "review" and state.get("selected"):
            rows.append([self.button("💳 Проверить заказ (имитация)", "pay")])
        if state.get("options") or state.get("receipt"):
            rows.append([self.button("📄 PDF", "pdf"), self.button("🧭 В пути", "track"), self.button("📍 Карта", "map")])
        if state.get("autonomous"):
            rows.append([self.button("Изменить пожелания", "edit")])
        elif state.get("stage", "scenarios") != "scenarios":
            rows.append([self.button("← Назад", "back")])
        rows.extend([[self.button("Переписка", "history"), self.button("Мои поездки", "trips")],
                     [self.button("Новая поездка", "new"), self.button("Помощь", "help")]])
        rows.append([self.button("Сохранённые заказы", "orders"), self.button("Удалить поездку", f"remove:{trip_id}")])
        return rows

    def offer_buttons(self, trip_id: str, state: dict, kind: str, index: int, item: dict) -> list[list[dict]]:
        prefix = f"{trip_id}:{state.get('revision', 0)}"
        rows = [[self.button("Подробнее", f"d:{prefix}:{kind}:{index}")]]
        choice_index = next((i for i, c in enumerate(state.get("choices", [])) if c["id"] == item["id"]), None)
        card = next((c for c in state.get("cards", []) if c["id"] == item["id"]), {})
        if choice_index is not None and card.get("selectable", True) and card.get("freshness") != "expired" and (not item.get("source") or fresh_quote(item)):
            rows[0].append(self.button("Выбрать", f"c:{prefix}:{choice_index}"))
        hotel = item.get("stay") or item
        if hotel.get("photos"):
            rows.append([self.button("📷 Фотографии отеля", f"f:{prefix}:{kind}:{index}")])
        url = safe_url(item.get("url") or item.get("source", {}).get("source_url"))
        if url:
            rows.append([{"text": "Открыть у источника", "url": url}])
        coordinates = hotel.get("coordinates")
        if coordinates:
            rows.append([{"text": "📍 На карте", "url": "https://yandex.ru/maps/?pt=" + quote(f"{coordinates['lon']},{coordinates['lat']}") + "&z=16&l=map"}])
        return rows

    async def show(self, chat_id: int, trip_id: str, state: dict, kind: str | None = None, *, reply: bool = False, page: int = 0) -> None:
        answer = state.get("answer") or "Опишите поездку: откуда, когда, с кем и какой отдых хочется. Планируем поездки по России."
        if reply and answer != state.get("plan_answer"):
            await self.send(chat_id, answer, self.navigation(trip_id, state))
            return
        kind = kind or ("s" if state.get("stage") == "scenarios" and state.get("choices") else
                        "h" if state.get("focus") == "stays" or state.get("stage") == "stays" else "t" if state.get("focus") == "transport" or state.get("stage") == "transport" else "p")
        entries = offers(state, kind)
        title = {"p": "Варианты поездки", "h": "Отели", "t": "Билеты туда и обратно", "s": "Идеи поездки"}[kind]
        lines = ["О! рядом · " + title, trip_summary(state)]
        if state.get("notice"):
            lines.append(state["notice"])
        if state.get("feedback"):
            lines.append("План требует уточнений. Найденное сохранено; обсудите недостающие компоненты с агентом.")
        if state.get("stage") == "booked":
            lines.append("Заказ оформлен в режиме имитации. Деньги не списаны, места не зарезервированы. /orders — состав заказов.")
        if entries:
            lines.append("Откройте детали или выберите вариант. Вопрос агенту можно написать обычным сообщением.")
        else:
            lines.append(answer if kind == "p" else "В сохранённом плане пока нет таких предложений.")
        await self.send(chat_id, "\n\n".join(line for line in lines if line))
        for index, item in enumerate(entries):
            if not page <= index < page + 5:
                continue
            content = package_text(item, state) if kind == "p" else scenario_text(item) if kind == "s" else candidate_text(item)
            if item["id"] in (state.get("selected_stay"), state.get("selected_transport")):
                content = "✓ Выбрано\n" + content
            await self.send(chat_id, f"{index + 1}. {content}", self.offer_buttons(trip_id, state, kind, index, item))
        buttons = self.navigation(trip_id, state)
        paging = []
        if page:
            paging.append(self.button("← Предыдущие", f"v:{trip_id}:{state['revision']}:{kind}:{max(0, page - 5)}"))
        if len(entries) > page + 5:
            paging.append(self.button("Следующие →", f"v:{trip_id}:{state['revision']}:{kind}:{page + 5}"))
        if paging:
            buttons.insert(0, paging)
        shown = {item["id"] for item in entries}
        buttons[:0] = [[self.button(choice["title"], f"c:{trip_id}:{state['revision']}:{index}")]
                       for index, choice in enumerate(state.get("choices", [])) if choice["id"] not in shown and not state.get("autonomous")]
        if kind in ("h", "t"):
            buttons.insert(0, [self.button("Новый поиск " + ("отелей" if kind == "h" else "билетов"), "search:" + ("stays" if kind == "h" else "transport")),
                               self.button("Добавить к полному плану", "extend")])
        elif not entries:
            buttons.insert(0, [self.button("Собрать полный план", "extend")])
            buttons.insert(1, [self.button("Подобрать отели", "search:stays"), self.button("Найти билеты", "search:transport")])
        if state.get("plan_answer"):
            buttons.append([self.button("Объяснение агента", "explain")])
        await self.send(chat_id, "Продолжим? Напишите вопрос или новые пожелания агенту.", buttons)

    async def search(self, api: httpx.AsyncClient, chat_id: int, trip_id: str, state: dict, text: str) -> dict | None:
        await self.send(chat_id, "Запрос принят. Подбираю варианты…")
        task = asyncio.create_task(self.request(api, chat_id, "POST", f"/trips/{trip_id}/messages", json={"message": text, "revision": state["revision"]}))
        label = ""
        try:
            while not task.done():
                await asyncio.wait([task], timeout=PROGRESS_INTERVAL)
                if task.done():
                    break
                response = await api.get(f"/trips/{trip_id}/status")
                if response.is_success:
                    progress = response.json()
                    current = progress.get("label", "")
                    if current and current != label:
                        previews = [card.get("title", "") for cards in progress.get("previews", {}).values() for card in cards[:2]]
                        await self.send(chat_id, current + ("\n\nПредварительно найдено:\n" + "\n".join(previews) if previews else ""))
                        label = current
            return await task
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def interact(self, api: httpx.AsyncClient, chat_id: int, user: str, text: str, action: str | None) -> None:
        trip_id, pending = await self.app.state.accounts.bot_state(chat_id)
        command = action or (text.split(maxsplit=1)[0].split("@")[0].removeprefix("/") if text.startswith("/") else "")
        if text == "/start web_login":
            command = "site"
        if command == "start":
            await self.app.state.accounts.bot_state(chat_id, trip_id, write=True)
            await self.send(chat_id, "Привет! Я О! рядом — ваш помощник в России.\n\nПодберу полные варианты поездки с билетами, отелем и программой. Можно искать только отели или только билеты. Можно менять выбор и задавать вопросы в любой момент. После оформления помогу в пути.\n\nПокупка и оплата — имитация. Начнём?", [
                [self.button("✦ Спланировать поездку", "new")], [self.button("🏨 Найти отели", "search:stays"), self.button("🎫 Найти билеты", "search:transport")], [self.button("Мои поездки", "trips"), self.button("Личный кабинет", "profile")], [self.button("Помощь и письма", "help")]])
            return
        if command == "new":
            result = await self.request(api, chat_id, "POST", "/trips")
            if result:
                await self.app.state.accounts.bot_state(chat_id, result["trip_id"], write=True)
                await self.send(chat_id, "Куда отправимся в России? Расскажите, какой отдых хочется. Например: «Из Москвы вдвоём в Сочи на 5 ночей в декабре, море и прогулки, до 120 000 ₽ на всех». Даты уточним в диалоге.", [[self.button("Только отели", "search:stays"), self.button("Только билеты", "search:transport")]])
            return
        if command in ("hotels", "tickets") and not trip_id:
            command = "search:" + ("stays" if command == "hotels" else "transport")
        if command.startswith("search:") and command[7:] in ("stays", "transport"):
            if not trip_id:
                created = await self.request(api, chat_id, "POST", "/trips")
                if not created:
                    return
                trip_id = created["trip_id"]
            await self.app.state.accounts.bot_state(chat_id, trip_id, command, write=True)
            await self.send(chat_id, "Напишите город, даты, число гостей и пожелания к отелю." if command == "search:stays" else "Напишите откуда и куда едем, даты туда и обратно, число пассажиров и пожелания к багажу.", [[self.button("Отмена", "cancel")]])
            return
        if command == "site":
            token = await self.app.state.accounts.web_login_link(user)
            url = environment().get("TRAVEL_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")
            await self.send(chat_id, "Продолжим на сайте с этим же аккаунтом и поездками.\n\nОдноразовая ссылка действует 10 минут. Не пересылайте её другим.", [[{"text": "Открыть мои поездки на сайте", "url": url + "/#login/" + token}]])
            return
        if command == "trips" or command.startswith("trips:"):
            page = int(command[6:]) if command.startswith("trips:") and command[6:].isdigit() else 0
            trips = await self.request(api, chat_id, "GET", "/trips")
            if trips is not None:
                buttons = [[self.button(f"{t['state'].get('constraints', {}).get('destination', 'Новая поездка')} · {t['state'].get('constraints', {}).get('start') or t['created_at'][:10]} · {STAGES.get(t['state'].get('stage'), 'Начало')}", "t:" + t["trip_id"])] for t in trips[page:page + 10]]
                if page:
                    buttons.append([self.button("← Предыдущие", f"trips:{max(0, page - 10)}")])
                if len(trips) > page + 10:
                    buttons.append([self.button("Следующие →", f"trips:{page + 10}")])
                await self.send(chat_id, "Ваши поездки" if trips else "Пока нет поездок. Создайте первую.", buttons + [[self.button("+ Новая поездка", "new")]])
            return
        if command.startswith("t:"):
            target = command[2:]
            state = await self.request(api, chat_id, "GET", "/trips/" + target)
            if state is not None:
                await self.app.state.accounts.bot_state(chat_id, target, write=True)
                await self.show(chat_id, target, state)
            return
        if command == "profile":
            account = await self.app.state.accounts.account(user)
            await self.app.state.accounts.bot_state(chat_id, trip_id, write=True)
            await self.send(chat_id, f"Личный кабинет\n\nИмя: {account['name']}\nГород: {account['city'] or 'не указан'}\nТелефон: {account['phone'] or 'не указан'}\nИнтересы: {', '.join(account['interests']) or 'не указаны'}\n\n/site — продолжить на сайте с теми же поездками. Для связи с существующим аккаунтом сайта откройте там «Профиль → Подключить Telegram». История разных аккаунтов автоматически не объединяется.", [
                [self.button("Изменить имя", "p:name"), self.button("Город", "p:city")], [self.button("Телефон", "p:phone"), self.button("Интересы", "p:interests")],
                [self.button("Отключить Telegram", "unlink")], [self.button("Удалить аккаунт и данные", "delete")]])
            return
        if command.startswith("p:"):
            field = command[2:]
            if field not in ("name", "city", "phone", "interests"):
                return
            await self.app.state.accounts.bot_state(chat_id, trip_id, "profile:" + field, write=True)
            await self.send(chat_id, {"name": "Введите имя (до 80 символов).", "city": "Введите город. Отправьте «-», чтобы очистить.", "phone": "Введите телефон. Отправьте «-», чтобы очистить.", "interests": "Введите до 10 интересов через запятую. Отправьте «-», чтобы очистить."}[field] + "\n/cancel — отменить")
            return
        if command == "cancel":
            await self.app.state.accounts.bot_state(chat_id, trip_id, write=True)
            await self.send(chat_id, "Действие отменено.")
            return
        if command in ("delete", "unlink"):
            await self.app.state.accounts.bot_state(chat_id, trip_id, command + ":" + user, write=True)
            await self.send(chat_id, "Удалить аккаунт и все поездки без возможности восстановления?" if command == "delete" else "Отключить Telegram от аккаунта? История сохранится в прежнем аккаунте; следующий /start создаст отдельный.", [[self.button("Подтвердить", command + "-confirm"), self.button("Отмена", "cancel")]])
            return
        if command in ("delete-confirm", "unlink-confirm"):
            if pending != command.removesuffix("-confirm") + ":" + user:
                await self.send(chat_id, "Подтверждение устарело. Откройте /profile и выберите действие заново.")
                return
            result = await self.request(api, chat_id, "DELETE", "/api/account" if command == "delete-confirm" else "/api/telegram/link", **({"json": {"confirmation": "УДАЛИТЬ"}} if command == "delete-confirm" else {}))
            if result is not None:
                await self.send(chat_id, "Готово. /start — начать снова.")
            return
        if pending and pending.startswith("profile:") and not command:
            field = pending.split(":")[1]
            account = await self.app.state.accounts.account(user)
            data = {k: account[k] for k in AccountProfile.model_fields}
            value = "" if text == "-" else text
            data[field] = [s.strip() for s in value.split(",") if s.strip()] if field == "interests" else value
            result = await self.request(api, chat_id, "PUT", "/api/account", json=data)
            if result is not None:
                await self.app.state.accounts.bot_state(chat_id, trip_id, write=True)
                await self.send(chat_id, "Сохранено. /profile — личный кабинет.")
            return
        if command == "help":
            await self.send(chat_id, "Рядом, когда планы меняются\n\nВыберите ситуацию: покажу порядок действий и подготовлю письмо с деталями поездки. Письма отправляете вы. Также можно написать вопрос обычным сообщением.", [[self.button(g.title, "h:" + g.id)] for g in GUIDES])
            return
        if command.startswith("h:"):
            if not trip_id:
                await self.send(chat_id, "Сначала создайте или откройте поездку: /new или /trips.")
                return
            guide = await self.request(api, chat_id, "GET", f"/trips/{trip_id}/support/{command[2:]}")
            if guide:
                await self.send(chat_id, guide["title"] + "\n\n" + "\n".join(f"{i+1}. {s}" for i, s in enumerate(guide["steps"])) + "\n\nЧерновик. Заполните поля в скобках.\nТема: " + guide["subject"] + "\n\n" + guide["letter"] + "\n\nПисьмо не отправлено.")
            return
        if not trip_id:
            if command:
                await self.send(chat_id, "Сначала создайте поездку /new или откройте /trips.")
                return
            result = await self.request(api, chat_id, "POST", "/trips")
            if not result:
                return
            trip_id = result["trip_id"]
            await self.app.state.accounts.bot_state(chat_id, trip_id, write=True)
        state = await self.request(api, chat_id, "GET", "/trips/" + trip_id)
        if state is None:
            return
        result = None
        if command == "orders":
            bookings = list(state.get("bookings", {}).values())
            if not bookings:
                await self.send(chat_id, "Пока нет оформленных имитационных заказов.")
            for booking in bookings:
                details = "\n".join(f"{item['name']} · {item.get('details', {}).get('start', '?')} — {item.get('details', {}).get('end', '?')}" for item in booking.get("items", []))
                program = "\n".join(day['date'] + ': ' + (', '.join(c['name'] for c in day.get('candidates', [])) or 'Свободное время и переезды') for day in booking.get('itinerary', []))
                await self.send(chat_id, f"Заказ {booking['id'][:8]} · версия {booking['revision']}\n\n{details}\n\nИзвестная сумма: {booking.get('payment', {}).get('amount', '?')} ₽\n\n{program}\n\nИмитация. Деньги не списаны, места не зарезервированы.")
            return
        if command.startswith("remove:"):
            if command != "remove:" + trip_id:
                await self.send(chat_id, "Эта поездка уже не открыта. Откройте /trips.")
                return
            await self.app.state.accounts.bot_state(chat_id, trip_id, "remove:" + trip_id, write=True)
            await self.send(chat_id, "Удалить эту поездку, переписку и отметки без возможности восстановления?", [[self.button("Удалить", "rm:" + trip_id), self.button("Отмена", "cancel")]])
            return
        if command.startswith("rm:"):
            if command != "rm:" + trip_id or pending != "remove:" + trip_id:
                await self.send(chat_id, "Подтверждение устарело. Откройте /show.")
                return
            removed = await self.request(api, chat_id, "DELETE", "/trips/" + trip_id)
            if removed is not None:
                await self.app.state.accounts.bot_state(chat_id, None, write=True)
                await self.send(chat_id, "Поездка удалена. /trips — остальные поездки, /new — начать новую.")
            return
        if command in ("plan", "hotels", "tickets"):
            await self.show(chat_id, trip_id, state, {"plan": "p", "hotels": "h", "tickets": "t"}[command])
            return
        if command in ("edit", "back") and state.get("autonomous"):
            await self.send(chat_id, "Напишите, что изменить: даты, бюджет, отель, билеты или программу. Агент обновит зависимые части плана; остальные сохранит.", self.navigation(trip_id, state))
            return
        if command == "history" or command.startswith("history:"):
            messages = state.get("messages", [])
            if not messages:
                await self.send(chat_id, "Переписка пока пуста. Напишите агенту пожелания к поездке.")
            end = int(command[8:]) if command.startswith("history:") and command[8:].isdigit() else len(messages)
            end = min(end, len(messages))
            for message in messages[max(0, end - 5):end]:
                await self.send(chat_id, ("Вы" if message["role"] == "user" else "Агент") + ":\n" + message["text"])
            buttons = []
            if end > 5:
                buttons.append([self.button("← Ранее", f"history:{end - 5}")])
            if end < len(messages):
                buttons.append([self.button("Позднее →", f"history:{min(len(messages), end + 5)}")])
            await self.send(chat_id, "Переписка сохранена. Напишите агенту, чтобы продолжить.", buttons + self.navigation(trip_id, state))
            return
        if command == "map":
            option = next((o for o in state.get("options", []) if o["id"] == state.get("selected")), None)
            option = option or next(iter(state.get("options", [])), {})
            receipt = state.get("receipt") if state.get("stage") == "booked" else None
            stay = next(({**item.get("details", {}), **item} for item in receipt.get("items", []) if item["kind"] == "stays"), None) if receipt else option.get("stay")
            days = receipt.get("itinerary", []) if receipt else option.get("days", [])
            places = [stay, *[c for day in days for c in day.get("candidates", [])]]
            points = {place.get("id") or place["name"]: place for place in places if place and place.get("coordinates")}
            if not points:
                await self.send(chat_id, "Источник пока не предоставил координаты отеля и мест. Адреса можно посмотреть в подробностях карточек.")
                return
            coordinates = "~".join(f"{place['coordinates']['lon']},{place['coordinates']['lat']}" for place in points.values())
            await self.send(chat_id, "Отель и места программы:\n\n" + "\n".join(place["name"] for place in points.values()), [[{"text": "Открыть все места на Яндекс Картах", "url": "https://yandex.ru/maps/?l=map&pt=" + quote(coordinates)}]])
            return
        if command == "explain":
            await self.send(chat_id, state.get("plan_answer") or state.get("answer") or "Пока нет объяснения.", self.navigation(trip_id, state))
            return
        if command.startswith(("d:", "f:", "v:")):
            parts = command.split(":")
            if len(parts) != 5 or parts[1] != trip_id or parts[2] != str(state["revision"]) or parts[3] not in ("p", "h", "t", "s") or not parts[4].isdigit():
                await self.send(chat_id, "Эта карточка устарела. Откройте /show.")
                return
            entries = offers(state, parts[3])
            index = int(parts[4])
            if index >= len(entries):
                await self.send(chat_id, "Эта карточка устарела. Откройте /show.")
                return
            if parts[0] == "v":
                await self.show(chat_id, trip_id, state, parts[3], page=index)
                return
            item = entries[index]
            if parts[0] == "f":
                hotel = item.get("stay") or item
                photos = list(dict.fromkeys(url for value in hotel.get("photos", []) if (url := safe_url(value))))
                for url in photos[:10]:
                    try:
                        await self.call("sendPhoto", {"chat_id": chat_id, "photo": url, "caption": hotel.get("name", "Фотография отеля")[:300]})
                    except TelegramError as exc:
                        if exc.status != 400:
                            raise
                        await self.send(chat_id, "Telegram не смог загрузить фото. Откройте фотографию у источника.", [[{"text": "Открыть фотографию", "url": url}]])
                if not photos:
                    await self.send(chat_id, "Источник не предоставил фотографий этого отеля.")
            else:
                content = package_text(item, state, detailed=True) if parts[3] == "p" else scenario_text(item) if parts[3] == "s" else candidate_text(item, detailed=True)
                await self.send(chat_id, content, self.offer_buttons(trip_id, state, parts[3], index, item))
            return
        if command in ("show", "back"):
            if command == "back":
                stages = list(STAGES)
                index = stages.index(state.get("stage", "scenarios"))
                if index:
                    state = await self.request(api, chat_id, "POST", f"/trips/{trip_id}/back", json={"stage": stages[index - 1], "revision": state["revision"]})
            if state:
                await self.show(chat_id, trip_id, state)
            return
        if command.startswith("c:"):
            parts = command.split(":")
            if len(parts) != 4 or parts[1] != trip_id or not parts[2].isdigit() or not parts[3].isdigit() or int(parts[2]) != state["revision"] or int(parts[3]) >= len(state.get("choices", [])):
                await self.send(chat_id, "Эта карточка устарела. Откройте /show.")
                return
            choice = state["choices"][int(parts[3])]["id"]
            await self.send(chat_id, "Выбор принят. Подбираю следующий шаг…")
            result = await self.request(api, chat_id, "POST", f"/trips/{trip_id}/select/{quote(choice, safe='')}", params={"revision": state["revision"]})
        elif command == "pay":
            if state.get("stage") != "review" or not state.get("selected"):
                await self.send(chat_id, "Сначала согласуйте билеты, отель и программу. /show — текущий этап.")
                return
            option = next((o for o in state["options"] if o["id"] == state["selected"]), None)
            if not option or not option.get("transport") or not option.get("stay"):
                await self.send(chat_id, "Вариант пока неполный. Попросите агента дополнить поездку.")
                return
            if not checkout_available(option, state):
                await self.send(chat_id, "Котировки устарели или не подтверждены для этой версии плана. Попросите агента обновить поиск перед оформлением.")
                return
            option_index = state["options"].index(option)
            await self.send(chat_id, package_text(option, state, detailed=True))
            await self.send(chat_id, f"Проверка заказа\n\nБилеты: {option['transport']['name']}\nОтель: {option['stay']['name']}\nИзвестная сумма за всех: {option['budget']['known_subtotal']} ₽\n\nНе включены: питание, местный транспорт, активности и дополнительные сборы.\n\nЭто имитация. Деньги не списываются, места не резервируются. Нажатие кнопки подтверждает только имитацию оплаты выбранным способом.", [[self.button("Подтвердить · карта", f"b:{trip_id}:{state['revision']}:{option_index}:card")], [self.button("Подтвердить · СБП", f"b:{trip_id}:{state['revision']}:{option_index}:sbp")]])
            return
        elif command.startswith("b:"):
            method = command.rsplit(":", 1)[-1]
            option_index = next((i for i, option in enumerate(state.get("options", [])) if option["id"] == state.get("selected")), None)
            if method not in ("card", "sbp") or option_index is None or command != f"b:{trip_id}:{state['revision']}:{option_index}:{method}" or state.get("stage") != "review":
                await self.send(chat_id, "Состав заказа изменился. Откройте /pay.")
                return
            booked = await self.request(api, chat_id, "POST", f"/trips/{trip_id}/bookings", json={"option_id": state["selected"], "revision": state["revision"], "confirm": True, "idempotency_key": f"checkout-{state['revision']}-{state['selected']}", "payment_method": method})
            if booked:
                result = await self.request(api, chat_id, "GET", "/trips/" + trip_id)
        elif command == "pdf":
            pdf = await self.request(api, chat_id, "GET", f"/trips/{trip_id}/itinerary.pdf")
            if pdf:
                await self.call("sendDocument", {"chat_id": chat_id, "caption": "Ваш маршрут · О! рядом. Заказ и оплата — имитация."}, pdf)
            return
        elif command == "track" or command.startswith(("done:", "track:")):
            progress = await self.request(api, chat_id, "GET", f"/trips/{trip_id}/progress")
            if not progress:
                return
            page = int(command[6:]) if command.startswith("track:") and command[6:].isdigit() else 0
            if command.startswith("done:"):
                parts = command.split(":")
                if len(parts) != 4 or parts[1] != trip_id or not parts[2].isdigit() or int(parts[2]) != state["revision"] or not parts[3].isdigit() or int(parts[3]) >= len(progress["items"]):
                    await self.send(chat_id, "Пункт изменился. Откройте /track.")
                    return
                page = int(parts[3]) // 10 * 10
                key = progress["items"][int(parts[3])]["id"]
                progress["completed"][key] = not progress["completed"].get(key, False)
                progress = await self.request(api, chat_id, "PUT", f"/trips/{trip_id}/progress", json={"completed": {k: v for k, v in progress["completed"].items() if k in {c['id'] for c in progress['items']}}})
                if not progress:
                    return
            rows = [[self.button(("✓ " if progress["completed"].get(item["id"]) else "○ ") + (item.get("date") + " · " if item.get("date") else "") + item["title"], f"done:{trip_id}:{state['revision']}:{i}")] for i, item in enumerate(progress["items"]) if page <= i < page + 10]
            if page:
                rows.append([self.button("← Ранее", f"track:{max(0, page - 10)}")])
            if len(progress["items"]) > page + 10:
                rows.append([self.button("Далее →", f"track:{page + 10}")])
            await self.send(chat_id, "Ваша поездка под рукой\n\nОтмечайте готовность и посещённые места. Статусы рейсов проверяйте у перевозчика — автоматического мониторинга здесь нет.", rows + [[self.button("Помощь в пути", "help")]])
            return
        elif command == "extend":
            result = await self.search(api, chat_id, trip_id, state, "Собери полную поездку с билетами, проживанием и программой на основе сохранённых пожеланий и выбранных компонентов. Если данных недостаточно, уточни их.")
        elif command:
            await self.send(chat_id, "Команда не найдена. /show — поездка, /help — помощь, /cancel — отмена ввода.")
            return
        elif text.strip():
            if pending in ("search:stays", "search:transport"):
                prefix = "Подбери только отели. " if pending == "search:stays" else "Подбери только билеты туда и обратно. "
                text = prefix + text
                if len(text) > 4000:
                    await self.send(chat_id, "Сократите запрос до 3900 символов.")
                    return
            result = await self.search(api, chat_id, trip_id, state, text)
            if result is not None and pending in ("search:stays", "search:transport"):
                await self.app.state.accounts.bot_state(chat_id, trip_id, write=True)
        if result:
            await self.show(chat_id, trip_id, result, reply=not command or command == "extend")
