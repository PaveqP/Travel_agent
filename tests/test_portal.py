import asyncio
import json
import os
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from pydantic import ValidationError

from travel_agent.accounts import AccountInput, AccountProfile, LoginInput, password_hash
from travel_agent.api import create_app
from travel_agent.itinerary_pdf import itinerary_pdf
from travel_agent.support import support_letter, support_reply
from travel_agent.telegram import TelegramBot
from travel_agent.web import ProgressRequest, checklist, create_web_app
from test_travel_agent import TRIP, agreed_state, decide, run


class PortalUnitTests(unittest.TestCase):
    def test_container_uses_service_hostname_and_encodes_postgres_password(self):
        env = {"TRAVEL_POSTGRES_HOST": "postgres", "TRAVEL_POSTGRES_PASSWORD": "a@:/#?%$=", "TRAVEL_DATABASE_URL": "postgresql://old@localhost/travel"}
        with patch("travel_agent.web.environment", return_value=env), patch("travel_agent.api.create_app") as factory:
            create_web_app()
        factory.assert_called_once_with(portal_database_url="postgresql://travel:a%40%3A%2F%23%3F%25%24%3D@postgres:5432/travel")

    def test_direct_startup_preserves_explicit_database_url(self):
        dsn = "postgresql://travel:example@localhost:55432/travel"
        with patch("travel_agent.web.environment", return_value={"TRAVEL_DATABASE_URL": dsn}), patch("travel_agent.api.create_app") as factory:
            create_web_app()
        factory.assert_called_once_with(portal_database_url=dsn)

    def test_container_rejects_missing_password_before_database_access(self):
        with patch("travel_agent.web.environment", return_value={"TRAVEL_POSTGRES_HOST": "postgres"}), patch("travel_agent.api.create_app") as factory:
            with self.assertRaisesRegex(RuntimeError, "TRAVEL_POSTGRES_PASSWORD"):
                create_web_app()
        factory.assert_not_called()

    def test_account_contract_and_password_hash(self):
        self.assertEqual(AccountInput(name="Аня", email="Anna@Example.org", password="password1234").email, "anna@example.org")
        for values in ({"name": "Аня", "email": "broken", "password": "password1234"}, {"name": "", "email": "a@b.ru", "password": "password1234"}, {"name": "Аня", "email": "a@b.ru", "password": "short"}):
            with self.assertRaises(ValidationError):
                AccountInput(**values)
        with self.assertRaises(ValidationError):
            AccountProfile(name="Аня", interests=[""])
        self.assertNotEqual(password_hash("password", "a" * 32), password_hash("password", "b" * 32))

    def test_support_uses_trip_facts_and_never_invents_booking(self):
        state = {"constraints": TRIP.model_dump(mode="json")}
        letter = support_letter("flight", state, "Аня")
        self.assertIn("Москва", letter["letter"])
        self.assertIn("2026-11-12", letter["letter"])
        self.assertIn("[номер реального бронирования]", letter["letter"])
        self.assertIn("Аня", letter["letter"])
        self.assertIsNone(support_reply("Хочу отель у моря", state))
        self.assertIn("Письмо не отправлено", support_reply("Помоги составить письмо в отель", state))
        self.assertIn("Багаж не прилетел", support_reply("Багаж не прилетел, что делать?", state))

    def test_progress_is_strict_and_based_on_actual_itinerary(self):
        with self.assertRaises(ValidationError):
            ProgressRequest(completed={"tickets": "false"})
        self.assertEqual(len(checklist({})), 4)
        self.assertEqual(checklist({"stage": "booked", "receipt": {"itinerary": [{"date": "2026-11-12", "candidates": [{"name": "Море"}]}]}})[-1]["id"], "2026-11-12:0")

    def test_pdf_embeds_cyrillic_font_and_handles_untrusted_text(self):
        state = agreed_state("review")
        state["constraints"]["purpose"] = "Море <script>не инструкция</script> & горы"
        document = itinerary_pdf(state, "test-trip")
        self.assertTrue(document.startswith(b"%PDF-"))
        self.assertIn(b"/FontFile2", document)
        self.assertGreater(len(document), 20000)


class TelegramUnitTests(unittest.IsolatedAsyncioTestCase):
    async def test_group_updates_never_create_accounts(self):
        accounts = SimpleNamespace(telegram_owner=AsyncMock())
        bot = TelegramBot(SimpleNamespace(state=SimpleNamespace(accounts=accounts)), AsyncMock(), "test-token")
        await bot.handle({"update_id": 1, "message": {"chat": {"id": -10, "type": "group"}, "from": {"id": 7}, "text": "/start"}})
        accounts.telegram_owner.assert_not_awaited()

    async def test_long_messages_keep_choice_buttons_on_last_part(self):
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True, "result": {}})))
        async with client:
            bot = TelegramBot(None, client, "test-token")
            bot.call = AsyncMock()
            await bot.send(7, "д" * 8000, [[bot.button("Выбрать", "c:1:2:0")]])
            self.assertEqual(bot.call.await_count, 3)
            self.assertNotIn("reply_markup", bot.call.await_args_list[0].args[1])
            self.assertIn("reply_markup", bot.call.await_args_list[-1].args[1])

    async def test_callback_size_and_outbound_allowlist(self):
        with self.assertRaises(ValueError):
            TelegramBot.button("X", "x" * 65)
        bot = TelegramBot(None, AsyncMock(), "test-token")
        with self.assertRaises(ValueError):
            await bot.call("deleteWebhook", {})
        bot.client.post.assert_not_awaited()

    async def test_stale_telegram_choice_does_not_select_or_invoke_agent(self):
        accounts = SimpleNamespace(bot_state=AsyncMock(return_value=("trip", None)))
        bot = TelegramBot(SimpleNamespace(state=SimpleNamespace(accounts=accounts)), AsyncMock(), "test-token")
        bot.request = AsyncMock(return_value={"revision": 2, "choices": [{"id": "flight"}]})
        bot.send = AsyncMock()
        await bot.interact(AsyncMock(), 7, "owner", "", "c:trip:1:0")
        self.assertEqual(bot.request.await_count, 1)
        self.assertIn("устарела", bot.send.await_args.args[1])

    async def test_old_delete_button_cannot_delete_a_newly_linked_account(self):
        accounts = SimpleNamespace(bot_state=AsyncMock(return_value=("trip", "delete:old-owner")))
        bot = TelegramBot(SimpleNamespace(state=SimpleNamespace(accounts=accounts)), AsyncMock(), "test-token")
        bot.request = AsyncMock()
        bot.send = AsyncMock()
        await bot.interact(AsyncMock(), 7, "new-owner", "", "delete-confirm")
        bot.request.assert_not_awaited()
        self.assertIn("устарело", bot.send.await_args.args[1])


@unittest.skipUnless(os.environ.get("TRAVEL_TEST_DATABASE_URL"), "Separate PostgreSQL portal integration mode")
class PortalPostgresTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch("travel_agent.api.create_model", return_value=object()))
        self.stack.enter_context(patch("travel_agent.api.llm_decider", return_value=decide))
        self.stack.enter_context(patch("travel_agent.api.llm_presenter", return_value=None))
        self.runners = {}
        for role, symbol in (("transport", "run_transport"), ("stays", "run_stays"), ("experience", "run_experience")):
            async def runner(trip, revision, task, previous, _role=role, **kwargs):
                return await run(_role, trip, revision, task, previous)
            mocked = AsyncMock(side_effect=runner)
            self.runners[role] = mocked
            self.stack.enter_context(patch("travel_agent.api." + symbol, mocked))
        self.dsn = os.environ["TRAVEL_TEST_DATABASE_URL"]
        self.credentials = {"name": "Аня", "email": f"{uuid4()}@example.org", "password": "test-password-1234"}
        self.client = self.stack.enter_context(TestClient(create_app(portal_database_url=self.dsn)))
        response = self.client.post("/api/auth/register", json=self.credentials)
        self.assertEqual(response.status_code, 200, response.text)
        self.user = response.json()["id"]

    def plan(self):
        trip_id = self.client.post("/trips").json()["trip_id"]
        path = "/trips/" + trip_id
        state = self.client.post(path + "/messages", json={"message": "Сочи", "revision": 0}).json()
        state = self.client.post(path + "/messages", json={"message": "даты", "revision": state["revision"]}).json()
        for _ in range(4):
            response = self.client.post(path + "/select/" + state["choices"][0]["id"], params={"revision": state["revision"]})
            self.assertEqual(response.status_code, 200, response.text)
            state = response.json()
        self.assertEqual(state["stage"], "review")
        return trip_id, path, state

    def test_profile_crud_auth_and_csrf(self):
        cookie = self.client.cookies.get("travel_session")
        self.assertTrue(cookie)
        response = self.client.put("/api/account", json={"name": "Анна", "phone": "+7 900 123-45-67", "city": "Москва", "interests": ["море"]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["name"], "Анна")
        self.assertEqual(self.client.get("/profile").json()["interests"], ["море"])
        self.assertEqual(self.client.put("/api/account", headers={"Origin": "https://attacker.example"}, json={"name": "Чужой"}).status_code, 403)
        self.assertEqual(self.client.post("/api/auth/register", json=self.credentials).status_code, 409)
        self.client.post("/api/auth/logout")
        self.assertEqual(self.client.get("/api/account").status_code, 401)
        bad = {"email": self.credentials["email"], "password": "wrong"}
        self.assertEqual(self.client.post("/api/auth/login", json=bad).status_code, 401)
        bad["password"] = self.credentials["password"]
        self.assertEqual(self.client.post("/api/auth/login", json=bad).status_code, 200)
        self.assertEqual(self.client.request("DELETE", "/api/account", json={"confirmation": "УДАЛИТЬ"}).status_code, 204)
        self.assertEqual(self.client.get("/api/account").status_code, 401)
        self.assertEqual(self.client.post("/api/auth/login", json=bad).status_code, 401)

    def test_full_trip_back_booking_pdf_progress_and_support(self):
        trip_id, path, state = self.plan()
        before_transport = state["selected_transport"]
        back = self.client.post(path + "/back", json={"stage": "stays", "revision": state["revision"]}).json()
        self.assertEqual(back["selected_transport"], before_transport)
        self.assertIsNone(back["selected_stay"])
        self.assertFalse(back["options"])
        self.assertEqual(self.client.post(path + "/back", json={"stage": "transport", "revision": state["revision"]}).status_code, 409)
        for _ in range(2):
            back = self.client.post(path + "/select/" + back["choices"][0]["id"], params={"revision": back["revision"]}).json()
        booking = {"option_id": back["selected"], "revision": back["revision"], "confirm": True, "idempotency_key": "portal-test-key", "payment_method": "sbp"}
        first = self.client.post(path + "/bookings", json=booking)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json(), self.client.post(path + "/bookings", json=booking).json())
        self.assertTrue(first.json()["simulated"])
        self.assertFalse(first.json()["paid"])
        self.assertEqual(first.json()["payment"]["method"], "sbp")
        self.assertEqual(self.client.post(path + "/bookings", json={**booking, "payment_method": "card"}).status_code, 409)
        pdf = self.client.get(path + "/itinerary.pdf")
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        self.assertEqual(self.client.put(path + "/progress", json={"completed": {"tickets": True}}).status_code, 200)
        self.assertTrue(self.client.get(path + "/progress").json()["completed"]["tickets"])
        self.assertEqual(self.client.put(path + "/progress", json={"completed": {"invented": True}}).status_code, 422)
        count = sum(r.await_count for r in self.runners.values())
        support = self.client.post(path + "/messages", json={"message": "Помоги составить письмо в отель", "revision": back["revision"]})
        self.assertEqual(support.status_code, 200, support.text)
        self.assertEqual(sum(r.await_count for r in self.runners.values()), count)
        self.assertIn("Письмо не отправлено", support.json()["answer"])
        self.assertEqual(support.json()["stage"], "booked")
        self.assertEqual(self.client.get("/trips").json()[0]["state"]["stage"], "booked")
        self.assertEqual(self.client.request("DELETE", "/api/account", json={"confirmation": "УДАЛИТЬ"}).status_code, 204)

    def test_web_and_telegram_share_owner_and_reject_stale_buttons(self):
        trip_id, path, state = self.plan()
        url = self.client.post("/api/telegram/link").json()["url"]
        token = url.split("link_")[1]
        accounts = self.client.app.state.accounts
        telegram_id = uuid4().int % 10**12 + 1
        linked = self.client.portal.call(accounts.telegram_owner, telegram_id, "Аня", token)
        self.assertEqual(linked, self.user)
        login_token = self.client.portal.call(accounts.web_login_link, self.user)
        self.assertEqual(self.client.post("/api/auth/telegram", json={"token": login_token}).json()["id"], self.user)
        self.assertEqual(self.client.post("/api/auth/telegram", json={"token": login_token}).status_code, 401)
        with self.assertRaises(ValueError):
            self.client.portal.call(accounts.telegram_owner, telegram_id + 1, "Другой", token)
        before = sum(r.await_count for r in self.runners.values())
        calls = []
        async def transport(request):
            calls.append(json.loads(request.content))
            return httpx.Response(200, json={"ok": True, "result": {}})
        async def interact():
            await accounts.bot_state(telegram_id, trip_id, write=True)
            async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
                bot = TelegramBot(self.client.app, client, "test-token")
                await bot.handle({"update_id": 1, "callback_query": {"id": "callback", "from": {"id": telegram_id}, "message": {"chat": {"id": telegram_id, "type": "private"}}, "data": f"c:{trip_id}:0:0"}})
                await bot.handle({"update_id": 2, "message": {"chat": {"id": telegram_id, "type": "private"}, "from": {"id": telegram_id}, "text": "/trips"}})
        self.client.portal.call(interact)
        self.assertEqual(sum(r.await_count for r in self.runners.values()), before)
        self.assertTrue(any("устарела" in c.get("text", "") for c in calls))
        self.assertTrue(any(trip_id in json.dumps(c) for c in calls))
        self.client.request("DELETE", "/api/account", json={"confirmation": "УДАЛИТЬ"})

    def test_all_records_and_messages_survive_application_restart_and_are_isolated(self):
        trip_id, path, state = self.plan()
        cookies = dict(self.client.cookies)
        with TestClient(create_app(portal_database_url=self.dsn)) as other:
            other.cookies.update(cookies)
            restored = other.get(path)
            self.assertEqual(restored.status_code, 200, restored.text)
            self.assertEqual(restored.json()["revision"], state["revision"])
            self.assertEqual(restored.json()["messages"], state["messages"])
            self.assertEqual(other.get("/trips").json()[0]["trip_id"], trip_id)
            stranger = {**self.credentials, "email": f"{uuid4()}@example.org"}
            self.assertEqual(other.post("/api/auth/register", json=stranger).status_code, 200)
            self.assertEqual(other.get(path).status_code, 404)
            self.assertEqual(other.get(path + "/itinerary.pdf").status_code, 404)
            self.assertEqual(other.get(path + "/progress").status_code, 404)
            other.request("DELETE", "/api/account", json={"confirmation": "УДАЛИТЬ"})
        self.client.request("DELETE", "/api/account", json={"confirmation": "УДАЛИТЬ"})
