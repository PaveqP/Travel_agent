import asyncio
import contextlib
import json
import logging

import httpx

from travel_agent.accounts import AccountProfile
from travel_agent.config import environment
from travel_agent.support import GUIDES

LOGGER = logging.getLogger(__name__)
BOT_NAME = "ostrovok_helper_ryadom_bot"
STAGES = {"scenarios": "Идея поездки", "transport": "Билеты", "stays": "Проживание", "itinerary": "Программа", "review": "Проверка и оплата", "booked": "Поездка собрана"}
COMMANDS = [
    ("start", "Начать и открыть меню"), ("new", "Новая поездка"), ("trips", "История поездок"),
    ("show", "Текущий шаг и варианты"), ("back", "Вернуться на шаг назад"), ("profile", "Личный кабинет"),
    ("pay", "Проверить имитацию оплаты"), ("pdf", "Скачать маршрутный лист"),
    ("track", "План и отметки по поездке"), ("help", "Помощь и шаблоны писем"),
    ("site", "Продолжить на сайте с теми же поездками"),
    ("orders", "Сохранённые имитационные заказы"),
]


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

    async def call(self, method: str, data: dict, document: bytes | None = None):
        if method not in {"getMe", "getWebhookInfo", "getUpdates", "setMyCommands", "sendMessage", "sendDocument", "answerCallbackQuery"}:
            raise ValueError("Unsupported Telegram method")
        if document is not None:
            response = await self.client.post(self.base + method, data=data, files={"document": ("ostrovok-itinerary.pdf", document, "application/pdf")})
        else:
            response = await self.client.post(self.base + method, json=data)
        try:
            payload = response.json()
        except ValueError:
            raise TelegramError("Telegram invalid JSON") from None
        if not isinstance(payload, dict) or not payload.get("ok"):
            retry_after = payload.get("parameters", {}).get("retry_after", 3) if isinstance(payload, dict) else 3
            raise TelegramError(f"Telegram HTTP {response.status_code}", response.status_code, retry_after if isinstance(retry_after, int) else 3)
        return payload.get("result")

    async def send(self, chat_id: int, text: str, buttons: list[list[dict]] | None = None) -> None:
        chunks = [text[i:i + 3800] for i in range(0, len(text), 3800)] or ["Готово"]
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

    async def poll(self) -> None:
        try:
            identity = await self.call("getMe", {})
            if not isinstance(identity, dict) or identity.get("username") != BOT_NAME:
                raise TelegramError("Unexpected bot identity")
            webhook = await self.call("getWebhookInfo", {})
            if webhook.get("url"):
                raise TelegramError("Existing webhook prevents polling; it was preserved")
            await self.call("setMyCommands", {"commands": [{"command": key, "description": label} for key, label in COMMANDS]})
            self.ready = True
            offset = await self.app.state.accounts.bot_offset()
            while True:
                try:
                    updates = await self.call("getUpdates", {"offset": offset, "timeout": 25, "limit": 10, "allowed_updates": ["message", "callback_query"]})
                    if not isinstance(updates, list):
                        raise TelegramError("Telegram invalid updates")
                    for update in updates:
                        try:
                            await self.handle(update)
                        except (TelegramError, httpx.HTTPError) as exc:
                            LOGGER.warning("telegram update skipped outcome=%s", type(exc).__name__)
                        offset = int(update["update_id"]) + 1
                        await self.app.state.accounts.bot_offset(offset)
                except httpx.TransportError:
                    LOGGER.warning("telegram outcome=network_error")
                    await asyncio.sleep(3)
                except TelegramError as exc:
                    if exc.status != 429:
                        raise
                    LOGGER.warning("telegram outcome=rate_limited")
                    await asyncio.sleep(min(max(exc.retry_after, 1), 30))
        except (TelegramError, httpx.HTTPError) as exc:
            LOGGER.error("telegram stopped outcome=%s", str(exc) if isinstance(exc, TelegramError) else type(exc).__name__)
        finally:
            self.ready = False

    async def stop(self, task: asyncio.Task) -> None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def handle(self, update: dict) -> None:
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
        if callback:
            try:
                await self.call("answerCallbackQuery", {"callback_query_id": callback["id"]})
            except TelegramError as exc:
                if exc.status != 400:
                    raise
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

    async def show(self, chat_id: int, trip_id: str, state: dict) -> None:
        stage = state.get("stage", "scenarios")
        revision = state.get("revision", 0)
        answer = state.get("answer") or state.get("plan_answer") or "Опишите поездку: откуда, когда, с кем и какой отдых хочется. Планируем Россия."
        buttons = [[self.button(f"{i + 1}. {choice['title']}", f"c:{trip_id}:{revision}:{i}")] for i, choice in enumerate(state.get("choices", []))]
        if stage == "review":
            buttons.append([self.button("💳 Проверить и оплатить (имитация)", "pay")])
        if stage != "scenarios":
            buttons.append([self.button("← Назад", "back"), self.button("Мои поездки", "trips")])
        if state.get("options") or state.get("receipt"):
            buttons.append([self.button("📄 Маршрут PDF", "pdf"), self.button("🧭 В пути", "track")])
        if state.get("bookings"):
            buttons.append([self.button("Сохранённые заказы", "orders")])
        buttons.append([self.button("Помощь в поездке", "help")])
        await self.send(chat_id, f"О! рядом · {STAGES.get(stage, stage)}\n\n{answer}", buttons)

    async def interact(self, api: httpx.AsyncClient, chat_id: int, user: str, text: str, action: str | None) -> None:
        trip_id, pending = await self.app.state.accounts.bot_state(chat_id)
        command = action or (text.split(maxsplit=1)[0].split("@")[0].removeprefix("/") if text.startswith("/") else "")
        if text == "/start web_login":
            command = "site"
        if command == "start":
            await self.app.state.accounts.bot_state(chat_id, trip_id, write=True)
            await self.send(chat_id, "Привет! Я О! рядом — ваш помощник в России.\n\nСоберём поездку по шагам: идея → билеты → отель → программа. Можно менять выбор и задавать вопросы в любой момент. После оформления помогу в пути.\n\nПокупка и оплата — имитация. Начнём?", [
                [self.button("✦ Спланировать поездку", "new")], [self.button("Мои поездки", "trips"), self.button("Личный кабинет", "profile")], [self.button("Помощь и письма", "help")]])
            return
        if command == "new":
            result = await self.request(api, chat_id, "POST", "/trips")
            if result:
                await self.app.state.accounts.bot_state(chat_id, result["trip_id"], write=True)
                await self.send(chat_id, "Куда отправимся в России? Расскажите, какой отдых хочется. Например: «Из Москвы вдвоём в Сочи на 5 ночей в декабре, море и прогулки, до 120 000 ₽ на всех». Даты уточним в диалоге.")
            return
        if command == "site":
            token = await self.app.state.accounts.web_login_link(user)
            url = environment().get("TRAVEL_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")
            await self.send(chat_id, "Продолжим на сайте с этим же аккаунтом и поездками.\n\nОдноразовая ссылка действует 10 минут. Не пересылайте её другим.", [[{"text": "Открыть мои поездки на сайте", "url": url + "/#login/" + token}]])
            return
        if command == "trips":
            trips = await self.request(api, chat_id, "GET", "/trips")
            if trips is not None:
                buttons = [[self.button(f"{t['state'].get('constraints', {}).get('destination', 'Новая поездка')} · {t['state'].get('constraints', {}).get('start') or t['created_at'][:10]} · {STAGES.get(t['state'].get('stage'), 'Начало')}", "t:" + t["trip_id"])] for t in trips[:30]]
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
            result = await self.request(api, chat_id, "POST", f"/trips/{trip_id}/select/{choice}", params={"revision": state["revision"]})
        elif command == "pay":
            if state.get("stage") != "review" or not state.get("selected"):
                await self.send(chat_id, "Сначала согласуйте билеты, отель и программу. /show — текущий этап.")
                return
            option = next(o for o in state["options"] if o["id"] == state["selected"])
            await self.send(chat_id, f"Проверка заказа\n\nБилеты: {option['transport']['name']}\nОтель: {option['stay']['name']}\nИзвестная сумма за всех: {option['budget']['known_subtotal']} ₽\n\nНе включены: питание, местный транспорт, активности и дополнительные сборы.\n\nЭто имитация. Деньги не списываются, места не резервируются. Нажатие кнопки подтверждает только имитацию оплаты выбранным способом.", [[self.button("Подтвердить · карта", f"b:{trip_id}:{state['revision']}:card")], [self.button("Подтвердить · СБП", f"b:{trip_id}:{state['revision']}:sbp")]])
            return
        elif command.startswith("b:"):
            method = command.rsplit(":", 1)[-1]
            if method not in ("card", "sbp") or command != f"b:{trip_id}:{state['revision']}:{method}" or state.get("stage") != "review":
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
        elif command == "track" or command.startswith("done:"):
            progress = await self.request(api, chat_id, "GET", f"/trips/{trip_id}/progress")
            if not progress:
                return
            if command.startswith("done:"):
                parts = command.split(":")
                if len(parts) != 4 or parts[1] != trip_id or not parts[2].isdigit() or int(parts[2]) != state["revision"] or not parts[3].isdigit() or int(parts[3]) >= len(progress["items"]):
                    await self.send(chat_id, "Пункт изменился. Откройте /track.")
                    return
                key = progress["items"][int(parts[3])]["id"]
                progress["completed"][key] = not progress["completed"].get(key, False)
                progress = await self.request(api, chat_id, "PUT", f"/trips/{trip_id}/progress", json={"completed": {k: v for k, v in progress["completed"].items() if k in {c['id'] for c in progress['items']}}})
                if not progress:
                    return
            rows = [[self.button(("✓ " if progress["completed"].get(item["id"]) else "○ ") + item["title"], f"done:{trip_id}:{state['revision']}:{i}")] for i, item in enumerate(progress["items"][:90])]
            await self.send(chat_id, "Ваша поездка под рукой\n\nОтмечайте готовность и посещённые места. Статусы рейсов проверяйте у перевозчика — автоматического мониторинга здесь нет.", rows + [[self.button("Помощь в пути", "help")]])
            return
        elif command:
            await self.send(chat_id, "Команда не найдена. /show — поездка, /help — помощь, /cancel — отмена ввода.")
            return
        elif text.strip():
            await self.send(chat_id, "Думаю над вашим запросом…")
            result = await self.request(api, chat_id, "POST", f"/trips/{trip_id}/messages", json={"message": text, "revision": state["revision"]})
        if result:
            await self.show(chat_id, trip_id, result)
