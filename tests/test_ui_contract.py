import asyncio
import copy
import hashlib
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from travel_agent.api import create_app
from travel_agent.graph import build_graph, present_stage
from travel_agent.schemas import SupervisorDecision
from travel_agent.tools import build_tools, normalize
from test_travel_agent import FIXTURES, TRIP, agreed_state, decide, run


class PresentationTests(unittest.TestCase):
    def test_saved_tour_reopens_with_summary_program_and_unchanged_checkpoint(self):
        from travel_agent.engine import compose_packages
        from travel_agent.schemas import TurnPlan
        from test_autonomous_planning import result

        graph = build_graph(AsyncMock(return_value=TurnPlan(action='chat', reply='Обсудим детали.')),
                            {role: AsyncMock() for role in ('transport', 'stays', 'experience')},
                            InMemorySaver(), autonomous=True)
        results = {role: result(role, TRIP, 1).model_dump(mode='json') for role in ('transport', 'stays', 'experience')}
        results['experience']['days'] = []
        options, feedback = compose_packages(TRIP, results, 1)
        for option in options:
            for day in option.days:
                day.candidates = []
        saved = {'autonomous': True, 'constraints': TRIP.model_dump(mode='json'), 'revision': 1, 'stage': 'review',
                 'results': results, 'options': [o.model_dump(mode='json') for o in options],
                 'feedback': [f.model_dump() for f in feedback], 'selected': options[0].id,
                 'choices': [{'id': o.id} for o in options], 'answer': 'Не удалось: timeout. ' * 300,
                 'plan_answer': 'Не удалось: timeout. ' * 300}
        saved['messages'] = [HumanMessage(content='Поездка целиком'), AIMessage(content=saved['answer'])]
        with TestClient(create_app(graph, tokens=('alice',))) as client:
            client.headers['Authorization'] = 'Bearer alice'
            trip_id = client.post('/trips').json()['trip_id']
            config = {'configurable': {'thread_id': hashlib.sha256(b'alice').hexdigest() + ':' + trip_id}}
            client.portal.call(graph.aupdate_state, config, saved)
            shown = client.get('/trips/' + trip_id).json()
            self.assertLess(len(shown['answer']), 1200)
            self.assertNotIn('timeout', shown['answer'])
            self.assertNotIn('Не удалось', shown['answer'])
            self.assertTrue(any(d['candidates'] for d in shown['options'][0]['days']))
            self.assertEqual(shown['options'][0]['budget'], saved['options'][0]['budget'])
            self.assertEqual(shown['selected'], saved['selected'])
            self.assertEqual(shown['revision'], 1)
            self.assertEqual(shown['messages'][-1]['text'], shown['answer'])
            self.assertEqual(shown['messages'][-1]['presentation']['options'], shown['options'])
            stored = client.portal.call(graph.aget_state, config).values
            self.assertEqual(stored['answer'], saved['answer'])
            self.assertFalse(any(d['candidates'] for d in stored['options'][0]['days']))
            self.assertEqual(client.get('/trips/' + trip_id).json(), shown)

    def test_cards_survive_a_text_reply_and_reload_without_nested_message_history(self):
        async def chat(state):
            return SupervisorDecision(action="chat", reply="Условия: [Туту](https://tutu.ru).")

        graph = build_graph(chat, AsyncMock(side_effect=run), InMemorySaver())
        app = create_app(graph, tokens=("alice",))
        with TestClient(app) as client:
            client.headers["Authorization"] = "Bearer alice"
            trip_id = client.post("/trips").json()["trip_id"]
            config = {"configurable": {"thread_id": hashlib.sha256(b"alice").hexdigest() + ":" + trip_id}}
            state = agreed_state("transport")
            state.update(present_stage(state))
            state["messages"] = [HumanMessage(content="Билеты"), AIMessage(content=state["answer"])]
            client.portal.call(graph.aupdate_state, config, state)
            path = "/trips/" + trip_id
            before = client.get(path).json()
            self.assertTrue(before["messages"][-1]["presentation"]["cards"])
            response = client.post(path + "/messages", json={"message": "Уточни условия", "revision": 1})
            self.assertEqual(response.status_code, 200, response.text)
            messages = response.json()["messages"]
            self.assertEqual(len(messages), 4)
            self.assertEqual(messages[1]["presentation"], before["messages"][-1]["presentation"])
            self.assertNotIn("messages", messages[1]["presentation"])
            self.assertIsNone(messages[-1]["presentation"])
            self.assertIn("https://tutu.ru", messages[-1]["text"])
            self.assertEqual(client.get(path).json()["messages"], messages)

    def test_deleting_a_trip_erases_checkpoint_and_leaves_other_trips_and_profile(self):
        graph = build_graph(decide, AsyncMock(side_effect=run), InMemorySaver())
        with TestClient(create_app(graph, tokens=("alice", "bob"))) as client:
            client.headers["Authorization"] = "Bearer alice"
            trip_id, other = [client.post("/trips").json()["trip_id"] for _ in range(2)]
            path = "/trips/" + trip_id
            client.put("/profile", json=["море"])
            self.assertEqual(client.post(path + "/messages", json={"message": "Сочи", "revision": 0}).status_code, 200)
            self.assertEqual(client.delete(path, headers={"Authorization": "Bearer bob"}).status_code, 404)
            self.assertEqual(client.delete(path).status_code, 204)
            for suffix in ("", "/status", "/events"):
                self.assertEqual(client.get(path + suffix).status_code, 404)
            self.assertEqual(client.post(path + "/messages", json={"message": "Верни поездку", "revision": 0}).status_code, 404)
            self.assertEqual(client.delete(path).status_code, 404)
            self.assertEqual(client.get("/trips/" + other).status_code, 200)
            self.assertEqual(client.get("/profile").json()["interests"], ["море"])
            config = {"configurable": {"thread_id": hashlib.sha256(b"alice").hexdigest() + ":" + trip_id}}
            self.assertFalse(client.portal.call(graph.aget_state, config).values)


class CardDataTests(unittest.IsolatedAsyncioTestCase):
    def test_roundtrip_normalization_keeps_distinct_return_flight_details(self):
        candidate = normalize("tutu", "search_avia", FIXTURES["search_avia"], TRIP, datetime.now(timezone.utc))[0]
        self.assertEqual(len(candidate.legs), 2)
        self.assertIn("Шереметьево", candidate.legs[0].origin)
        self.assertIn("Внуково", candidate.legs[1].destination)
        self.assertEqual(candidate.legs[1].arrival_at.isoformat(), "2026-11-16T19:00:00+03:00")
        self.assertEqual(candidate.legs[1].carriers, ["Utair"])
        self.assertEqual(candidate.legs[1].flight_numbers, ["UT-268"])

    async def test_hotel_details_enrich_only_matching_hotel_and_dates(self):
        data = copy.deepcopy(FIXTURES["search_hotels"])
        data["hotels"][0]["photos"] = ["https://cdn2.tu-tu.ru/hotel.jpg", "javascript:bad", "https://127.0.0.1/private"]
        evidence = {}
        now = datetime.now(timezone.utc)
        candidates = normalize("tutu", "search_hotels", data, TRIP, now)
        hotel = candidates[0]
        self.assertEqual(hotel.photos, ["https://cdn2.tu-tu.ru/hotel.jpg"])
        self.assertFalse(hotel.amenities)
        evidence.update({c.id: c for c in candidates})
        shifted = hotel.model_copy(update={"id": hotel.id + "@other", "start": TRIP.start.replace(day=13)})
        evidence[shifted.id] = shifted
        details = {"hotel": {"amenities": ["Бассейн", {"name": "Сауна"}, {"name": "Баня", "available": False}],
                              "amenity_groups": [{"name": "Услуги", "amenities": ["Сауна", {"label": "SPA"}]}],
                              "photos": ["https://cdn2.tu-tu.ru/details.jpg"]}}
        async with httpx.AsyncClient() as client:
            tools = {t.name: t for t in build_tools("stays", TRIP, 1, client, {}, evidence, [], {"tools": 0})}
            with patch("travel_agent.tools.runtime_call", new=AsyncMock(return_value={"status": "ok", "data": details})) as network:
                result = await tools["hotel_details"].ainvoke({"source_id": hotel.id})
            self.assertEqual(result["status"], "ok")
            self.assertEqual(network.await_args.args[3]["hotel_id"], hotel.provider_id)
        self.assertEqual(evidence[hotel.id].amenities, ["Бассейн", "Сауна", "SPA"])
        self.assertEqual(evidence[hotel.id].photos, ["https://cdn2.tu-tu.ru/details.jpg"])
        self.assertFalse(evidence[candidates[1].id].amenities)
        self.assertFalse(evidence[shifted.id].amenities)

    async def test_mismatched_hotel_details_do_not_attach_amenities(self):
        hotels = normalize("tutu", "search_hotels", FIXTURES["search_hotels"], TRIP, datetime.now(timezone.utc))
        evidence = {hotel.id: hotel for hotel in hotels}
        async with httpx.AsyncClient() as client:
            tools = {t.name: t for t in build_tools("stays", TRIP, 1, client, {}, evidence, [], {"tools": 0})}
            with patch("travel_agent.tools.runtime_call", new=AsyncMock(return_value={"status": "ok", "data": {"hotel": {"hotel_id": "foreign", "amenities": ["Сауна"]}}})):
                result = await tools["hotel_details"].ainvoke({"source_id": hotels[0].id})
            self.assertEqual(result["status"], "schema_error")
            self.assertFalse(evidence[hotels[0].id].amenities)

    async def test_queued_message_cannot_recreate_a_deleted_trip(self):
        started, release = asyncio.Event(), asyncio.Event()

        async def waiting(state):
            started.set()
            await release.wait()
            return SupervisorDecision(action="chat", reply="Ответ")

        decider = AsyncMock(side_effect=waiting)
        graph = build_graph(decider, AsyncMock(side_effect=run), InMemorySaver())
        app = create_app(graph, tokens=("alice",))
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test", headers={"Authorization": "Bearer alice"}) as client:
                trip_id = (await client.post("/trips")).json()["trip_id"]
                path = "/trips/" + trip_id
                first = asyncio.create_task(client.post(path + "/messages", json={"message": "Привет", "revision": 0}))
                await asyncio.wait_for(started.wait(), 5)
                deletion = asyncio.create_task(client.delete(path))
                await asyncio.sleep(0)
                late = asyncio.create_task(client.post(path + "/messages", json={"message": "Поздний запрос", "revision": 0}))
                await asyncio.sleep(0)
                release.set()
                responses = await asyncio.wait_for(asyncio.gather(first, deletion, late), 5)
                self.assertEqual([response.status_code for response in responses], [200, 204, 404])
                self.assertEqual(decider.await_count, 1)
                self.assertEqual((await client.get(path)).status_code, 404)
