import hashlib
import os
import unittest
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.store.postgres.aio import AsyncPostgresStore

from travel_agent.api import create_app
from travel_agent.graph import build_graph
from test_travel_agent import agreed_state, decide, run


class TripChatTests(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryStore()
        self.graph = build_graph(decide, AsyncMock(side_effect=run), InMemorySaver())
        self.app = create_app(self.graph, store=self.store, tokens=("alice", "bob"))
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.client.headers["Authorization"] = "Bearer alice"
        self.trip = self.client.post("/trips").json()["trip_id"]
        self.path = "/trips/" + self.trip
        self.app.state.chat_model = AsyncMock()
        self.app.state.chat_model.ainvoke.return_value = AIMessage(content="Ответ с учётом вашей поездки.")

    def create(self, **values):
        response = self.client.post(self.path + "/chats", json=values)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_chats_are_separate_from_plan_and_each_other(self):
        config = {"configurable": {"thread_id": hashlib.sha256(b"alice").hexdigest() + ":" + self.trip}}
        state = agreed_state("review")
        self.client.portal.call(self.graph.aupdate_state, config, state)
        before = self.client.get(self.path).json()
        first = self.create(kind="support")
        second = self.create(kind="places", title="Прогулки")
        response = self.client.post(self.path + "/chats/" + first["chat_id"] + "/messages", json={"message": "Багаж не прилетел, что делать?", "revision": 0})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()["messages"]), 2)
        self.assertIn("Багаж не прилетел", response.json()["messages"][-1]["text"])
        self.app.state.chat_model.ainvoke.assert_not_awaited()
        self.assertEqual(self.client.get(self.path + "/chats/" + second["chat_id"]).json()["messages"], [])
        self.assertEqual(self.client.get(self.path).json(), before)
        self.assertEqual(len(self.client.get(self.path + "/chats").json()), 2)

    def test_questions_receive_selected_context_but_no_other_chat_history(self):
        first, second = self.create(kind="places"), self.create(kind="general")
        path = self.path + "/chats/" + first["chat_id"]
        self.assertEqual(self.client.post(path + "/messages", json={"message": "Что посмотреть рядом?", "revision": 0}).status_code, 200)
        self.assertEqual(self.client.post(path + "/messages", json={"message": "А вечером?", "revision": 1}).status_code, 200)
        calls = self.app.state.chat_model.ainvoke.await_args_list
        self.assertIn("Что посмотреть рядом?", [m.content for m in calls[1].args[0]])
        other = self.path + "/chats/" + second["chat_id"]
        self.assertEqual(self.client.post(other + "/messages", json={"message": "Список вещей", "revision": 0}).status_code, 200)
        self.assertNotIn("Что посмотреть рядом?", [m.content for m in self.app.state.chat_model.ainvoke.await_args.args[0]])
        self.assertEqual(self.client.get(path).json()["revision"], 2)

    def test_ownership_scopes_all_endpoints_and_chat_ids_to_the_trip(self):
        chat = self.create(kind="general")
        path = self.path + "/chats/" + chat["chat_id"]
        other_trip = self.client.post("/trips").json()["trip_id"]
        self.assertEqual(self.client.get("/trips/" + other_trip + "/chats/" + chat["chat_id"]).status_code, 404)
        self.client.headers["Authorization"] = "Bearer bob"
        for method, suffix, payload in [("GET", "/chats", None), ("POST", "/chats", {}), ("GET", "/chats/" + chat["chat_id"], None), ("DELETE", "/chats/" + chat["chat_id"], None), ("POST", "/chats/" + chat["chat_id"] + "/messages", {"message": "Чужой запрос", "revision": 0})]:
            self.assertEqual(self.client.request(method, self.path + suffix, json=payload).status_code, 404)
        self.app.state.chat_model.ainvoke.assert_not_awaited()

    def test_stale_revision_and_failed_reply_do_not_append_messages(self):
        chat = self.create(kind="general")
        path = self.path + "/chats/" + chat["chat_id"]
        self.assertEqual(self.client.post(path + "/messages", json={"message": "Запрос", "revision": 1}).status_code, 409)
        self.app.state.chat_model.ainvoke.assert_not_awaited()
        self.app.state.chat_model.ainvoke.side_effect = TimeoutError
        self.assertEqual(self.client.post(path + "/messages", json={"message": "Запрос", "revision": 0}).status_code, 504)
        self.assertEqual(self.client.get(path).json(), chat)

    def test_deleting_one_chat_keeps_plan_and_other_chats_and_trip_delete_cleans_all(self):
        first, second = self.create(), self.create()
        path = self.path + "/chats/" + first["chat_id"]
        self.assertEqual(self.client.delete(path).status_code, 204)
        self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.client.get(self.path + "/chats/" + second["chat_id"]).status_code, 200)
        self.assertEqual(self.client.get(self.path).status_code, 200)
        self.assertEqual(self.client.delete(self.path).status_code, 204)
        owner = hashlib.sha256(b"alice").hexdigest()
        self.assertEqual(self.client.portal.call(self.store.asearch, ("trip_chats", owner, self.trip)), [])

    def test_contract_rejects_unknown_fields_kinds_and_empty_messages(self):
        self.assertEqual(self.client.post(self.path + "/chats", json={"kind": "planner"}).status_code, 422)
        self.assertEqual(self.client.post(self.path + "/chats", json={"owner": "bob"}).status_code, 422)
        chat = self.create(title="  Вопросы  ")
        self.assertEqual(chat["title"], "Вопросы")
        self.assertEqual(self.client.post(self.path + "/chats/" + chat["chat_id"] + "/messages", json={"message": "", "revision": 0}).status_code, 422)
        self.assertEqual(self.client.post(self.path + "/chats/" + chat["chat_id"] + "/messages", json={"message": "   ", "revision": 0}).status_code, 422)

    def test_chat_titles_are_distinct_and_reopen_with_the_same_store(self):
        first, second = self.create(kind="support"), self.create(kind="support")
        self.assertEqual(first["title"], "Помощь в пути")
        self.assertEqual(second["title"], "Помощь в пути · 2")
        with TestClient(create_app(self.graph, store=self.store, tokens=("alice",))) as reopened:
            reopened.headers["Authorization"] = "Bearer alice"
            self.assertEqual(reopened.get(self.path + "/chats/" + first["chat_id"]).json(), first)


@unittest.skipUnless(os.environ.get("TRAVEL_TEST_DATABASE_URL"), "Separate PostgreSQL chat integration mode")
class PostgresChatTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_history_survives_store_restart_and_is_removed_with_trip(self):
        import httpx

        graph = build_graph(decide, AsyncMock(side_effect=run), InMemorySaver())
        dsn = os.environ["TRAVEL_TEST_DATABASE_URL"]
        async with AsyncPostgresStore.from_conn_string(dsn) as store:
            await store.setup()
            app = create_app(graph, store=store, tokens=("alice",))
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test", headers={"Authorization": "Bearer alice"}) as client:
                    trip = (await client.post("/trips")).json()["trip_id"]
                    path = "/trips/" + trip
                    chat = (await client.post(path + "/chats", json={"kind": "support"})).json()
                    chat_path = path + "/chats/" + chat["chat_id"]
                    response = await client.post(chat_path + "/messages", json={"message": "Багаж не прилетел", "revision": 0})
                    self.assertEqual(response.status_code, 200, response.text)
                    saved = response.json()
        async with AsyncPostgresStore.from_conn_string(dsn) as store:
            app = create_app(graph, store=store, tokens=("alice",))
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test", headers={"Authorization": "Bearer alice"}) as client:
                    self.assertEqual((await client.get(chat_path)).json(), saved)
                    self.assertEqual((await client.delete(path)).status_code, 204)
                    self.assertEqual((await client.get(chat_path)).status_code, 404)
            self.assertEqual(await store.asearch(("trip_chats", hashlib.sha256(b"alice").hexdigest(), trip)), [])
