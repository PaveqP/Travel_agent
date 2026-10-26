import json
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from langchain_core.exceptions import OutputParserException
from pydantic import ValidationError

from travel_agent.engine import apply_delta, compose, diagnose, simulate_purchase
from travel_agent.graph import supervise
from travel_agent.graph import build_graph
from travel_agent.schemas import BookingRequest, SpecialistResult, SupervisorDecision, TripDelta, TripScenario
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from test_travel_agent import TRIP, candidates


class ReliabilityTests(unittest.IsolatedAsyncioTestCase):
    def test_overnight_arrival_preserves_stays_and_explains_conflict(self):
        rows = candidates()
        for row in rows:
            if row.role == "transport":
                row.arrival_at += timedelta(days=1)
        options = compose(TRIP, rows, 1)
        self.assertTrue(options)
        self.assertTrue(all(o.stay and o.transport is None for o in options))
        diagnostics = diagnose(TRIP, rows)
        self.assertIn("arrival_stay_mismatch", diagnostics.reasons)
        self.assertEqual(diagnostics.suggested_check_in, TRIP.start + timedelta(days=1))
        revised = TRIP.model_copy(update={"check_in": diagnostics.suggested_check_in})
        for row in rows:
            if row.role == "stays":
                row.start = revised.check_in
        self.assertTrue(all(o.transport and o.stay for o in compose(revised, rows, 2)))

    def test_budget_basis_and_explicit_clearing(self):
        trip, affected = apply_delta(TRIP, TripDelta(adults=4, budget=100000, budget_basis="person"))
        self.assertEqual(trip.party_budget, 400000)
        self.assertIn("transport", affected)
        trip, _ = apply_delta(trip, TripDelta(hotel="Mirror"))
        trip, affected = apply_delta(trip, TripDelta(clear=["hotel"]))
        self.assertIsNone(trip.hotel)
        self.assertEqual(affected, {"stays", "experience"})
        with self.assertRaises(ValidationError):
            TripDelta(hotel="Mirror", clear=["hotel"])

    def test_hotel_dates_invalidate_only_dependent_roles(self):
        revised, affected = apply_delta(TRIP, TripDelta(check_in=TRIP.start + timedelta(days=1)))
        self.assertEqual(affected, {"stays", "experience"})
        self.assertEqual(revised.start, TRIP.start)
        revised, affected = apply_delta(revised, TripDelta(start=TRIP.start + timedelta(days=1), end=TRIP.end + timedelta(days=1)))
        self.assertIsNone(revised.check_in)
        self.assertEqual(affected, {"transport", "stays", "experience"})

    async def test_supervisor_error_preserves_plan_and_selection(self):
        options = [o.model_dump(mode="json") for o in compose(TRIP, candidates(), 1)]
        state = {"constraints": TRIP.model_dump(mode="json"), "revision": 1,
                 "options": options, "selected": options[0]["id"], "calls": 0}
        update = await supervise(state, AsyncMock(side_effect=OutputParserException("offline failure")))
        restored = {**state, **update}
        self.assertEqual(restored["options"], options)
        self.assertEqual(restored["selected"], state["selected"])
        self.assertEqual(restored["revision"], 1)
        self.assertNotIn("offline failure", json.dumps(update))


class StagedPlanningTests(unittest.IsolatedAsyncioTestCase):
    def scenario(self, ident="coast"):
        return TripScenario(id=ident, title="Прогулки у моря", destination="Сочи", purpose="Море и прогулки", tradeoff="Тарифы и детали проверим после выбора")

    async def test_scenarios_and_each_component_require_a_separate_choice(self):
        from test_travel_agent import run

        runner = AsyncMock(side_effect=run)
        planner = AsyncMock(return_value=SupervisorDecision(action="scenarios", scenarios=[self.scenario(str(i)).model_copy(update={"priority": priority}) for i, priority in enumerate(("cost", "balance", "comfort", "activities"))]))
        graph = build_graph(planner, runner, InMemorySaver())
        config = {"configurable": {"thread_id": "staged"}}
        state = await graph.ainvoke({"constraints": TRIP.model_dump(mode="json"), "messages": [HumanMessage(content="Предложи отдых")], "calls": 0}, config)
        self.assertEqual(len(state["choices"]), 4)
        runner.assert_not_called()
        for expected_stage, roles in (("transport", ["transport"]), ("stays", ["transport", "stays"]), ("itinerary", ["transport", "stays", "experience"]), ("review", ["transport", "stays", "experience"])):
            state = await graph.ainvoke({"requested_choice": state["choices"][0]["id"], "calls": 0}, config)
            self.assertEqual(state["stage"], expected_stage)
            self.assertEqual([c.args[0] for c in runner.await_args_list], roles)
        self.assertEqual(len(state["options"]), 1)
        self.assertEqual(runner.await_args_list[-1].args[4][0].id, state["selected_stay"])
        self.assertIsNone(state["options"][0]["budget"]["confirmed_total"])

    async def test_vague_request_can_choose_a_scenario_before_dates(self):
        runner = AsyncMock()
        graph = build_graph(AsyncMock(return_value=SupervisorDecision(action="scenarios", scenarios=[self.scenario()])), runner, InMemorySaver())
        config = {"configurable": {"thread_id": "vague"}}
        state = await graph.ainvoke({"messages": [HumanMessage(content="Хочу отдохнуть")], "calls": 0}, config)
        self.assertEqual(state["stage"], "scenarios")
        state = await graph.ainvoke({"requested_choice": "coast", "calls": 0}, config)
        self.assertEqual(state["status"], "needs_input")
        self.assertIn("города", state["answer"])
        runner.assert_not_called()

    async def test_night_flight_choice_accepts_actual_hotel_dates(self):
        async def run(role, trip, revision, task, previous):
            rows = [c for c in candidates() if c.role == role]
            for row in rows:
                if role == "transport":
                    row.arrival_at += timedelta(days=1)
                elif role == "stays":
                    row.start = trip.stay_start
            return SpecialistResult(role=role, revision=revision, status="ok", candidates=rows)

        runner = AsyncMock(side_effect=run)
        planner = AsyncMock(side_effect=[SupervisorDecision(action="scenarios", scenarios=[self.scenario()]), SupervisorDecision(action="approve", confirmed=True)])
        graph = build_graph(planner, runner, InMemorySaver())
        config = {"configurable": {"thread_id": "overnight"}}
        state = await graph.ainvoke({"constraints": TRIP.model_dump(mode="json"), "messages": [HumanMessage(content="Поездка")], "calls": 0}, config)
        state = await graph.ainvoke({"requested_choice": "coast", "calls": 0}, config)
        state = await graph.ainvoke({"requested_choice": state["choices"][0]["id"], "calls": 0}, config)
        self.assertIsNone(state["pending_check_in"])
        self.assertEqual([c.args[0] for c in runner.await_args_list], ["transport", "stays"])
        self.assertEqual(state["constraints"]["check_in"], (TRIP.start + timedelta(days=1)).isoformat())
        self.assertEqual(state["constraints"]["start"], TRIP.start.isoformat())

    async def test_foreign_id_cannot_advance_or_call_a_specialist(self):
        runner = AsyncMock()
        graph = build_graph(AsyncMock(return_value=SupervisorDecision(action="scenarios", scenarios=[self.scenario()])), runner, InMemorySaver())
        config = {"configurable": {"thread_id": "unknown"}}
        await graph.ainvoke({"constraints": TRIP.model_dump(mode="json"), "calls": 0}, config)
        state = await graph.ainvoke({"requested_choice": "forged", "calls": 0}, config)
        self.assertEqual(state["stage"], "scenarios")
        self.assertEqual(state["status"], "needs_input")
        runner.assert_not_called()
        with self.assertRaises(ValidationError):
            SupervisorDecision(action="scenarios", scenarios=[self.scenario(str(i)) for i in range(5)])
        with self.assertRaises(ValidationError):
            TripScenario(id="abroad", title="Пляж", destination="Бали", purpose="Море", tradeoff="Перелёт")
        with self.assertRaises(ValidationError):
            SupervisorDecision(action="scenarios", scenarios=[self.scenario("one"), self.scenario("two")])

    async def test_duration_conflict_stops_before_any_search(self):
        from test_travel_agent import agreed_state

        state = agreed_state()
        state["results"] = {}
        state["constraints"]["duration_days"] = 4
        runner = AsyncMock()
        graph = build_graph(AsyncMock(return_value=SupervisorDecision(action="compose")), runner, InMemorySaver())
        result = await graph.ainvoke({**state, "messages": [HumanMessage(content="Ищем")], "calls": 0}, {"configurable": {"thread_id": "duration"}})
        self.assertIn("4 ночей и 5", result["answer"])
        runner.assert_not_called()

    async def test_every_stage_and_order_survive_sqlite_reopening(self):
        from test_travel_agent import run

        runner = AsyncMock(side_effect=run)
        planner = AsyncMock(side_effect=[SupervisorDecision(action="scenarios", scenarios=[self.scenario()]), SupervisorDecision(action="checkout", confirmed=True)])
        config = {"configurable": {"thread_id": "persistent-stages"}}
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "stages.sqlite")
            async with AsyncSqliteSaver.from_conn_string(path) as saver:
                graph = build_graph(planner, runner, saver)
                await graph.ainvoke({"constraints": TRIP.model_dump(mode="json"), "messages": [HumanMessage(content="Предложи поездку")], "calls": 0}, config)
            for stage in ("transport", "stays", "itinerary", "review"):
                async with AsyncSqliteSaver.from_conn_string(path) as saver:
                    graph = build_graph(planner, runner, saver)
                    saved = (await graph.aget_state(config)).values
                    result = await graph.ainvoke({"requested_choice": saved["choices"][0]["id"], "calls": 0}, config)
                    self.assertEqual(result["stage"], stage)
            async with AsyncSqliteSaver.from_conn_string(path) as saver:
                graph = build_graph(planner, runner, saver)
                result = await graph.ainvoke({"messages": [HumanMessage(content="Подтверждаю имитацию покупки")], "calls": 0}, config)
                self.assertEqual(result["stage"], "booked")
                order_id = result["receipt"]["id"]
            async with AsyncSqliteSaver.from_conn_string(path) as saver:
                saved = (await build_graph(planner, runner, saver).aget_state(config)).values
                self.assertEqual(saved["receipt"]["id"], order_id)
                self.assertEqual(saved["receipt"]["payment"]["status"], "succeeded")
                self.assertEqual(len(saved["bookings"]), 1)
                self.assertFalse(saved["receipt"]["paid"])
                self.assertEqual([c.args[0] for c in runner.await_args_list], ["transport", "stays", "experience"])


class CheckoutTests(unittest.IsolatedAsyncioTestCase):
    def review(self):
        from test_travel_agent import agreed_state

        state = agreed_state("review")
        state["selected"] = state["options"][0]["id"]
        return state

    def test_checkout_validates_confirmation_budget_expiry_and_dates(self):
        state = self.review()
        request = BookingRequest(option_id=state["selected"], revision=1, confirm=True, idempotency_key="complete-order")
        booking = simulate_purchase(state, request)
        self.assertEqual(len(booking["items"]), 2)
        self.assertEqual(booking["payment"]["amount"], state["options"][0]["budget"]["known_subtotal"])
        self.assertIn("local_transport", booking["missing_costs"])
        self.assertFalse(booking["reserved"])
        self.assertTrue(booking["itinerary"])
        variants = []
        premature = deepcopy(state)
        premature["stage"] = "itinerary"
        variants.append(premature)
        expensive = deepcopy(state)
        expensive["constraints"].update(budget="1", budget_basis="party")
        variants.append(expensive)
        expired = deepcopy(state)
        expired["options"][0]["stay"]["source"]["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        variants.append(expired)
        mismatch = deepcopy(state)
        flight = mismatch["options"][0]["transport"]
        flight["arrival_at"] = (datetime.fromisoformat(flight["arrival_at"]) + timedelta(days=1)).isoformat()
        variants.append(mismatch)
        for invalid in variants:
            with self.subTest(stage=invalid["stage"]), self.assertRaises(ValueError):
                simulate_purchase(invalid, request)
        with self.assertRaises(ValueError):
            simulate_purchase(state, request.model_copy(update={"confirm": False}))
        state.update(stage="booked", bookings={request.idempotency_key: booking}, revision=2)
        self.assertEqual(simulate_purchase(state, request), booking)
        with self.assertRaises(ValueError):
            simulate_purchase(state, request.model_copy(update={"option_id": "different"}))

    async def test_natural_checkout_and_repeated_confirmation_do_not_research(self):
        state = self.review()
        runner = AsyncMock()
        graph = build_graph(AsyncMock(return_value=SupervisorDecision(action="checkout", confirmed=True)), runner, InMemorySaver())
        config = {"configurable": {"thread_id": "natural-checkout"}}
        result = await graph.ainvoke({**state, "messages": [HumanMessage(content="Оформляй")], "calls": 0}, config)
        self.assertEqual(result["stage"], "booked")
        result = await graph.ainvoke({"messages": [HumanMessage(content="Оформляй")], "calls": 0}, config)
        self.assertEqual(len(result["bookings"]), 1)
        runner.assert_not_called()

    async def test_program_change_preserves_hotel_transport_and_old_order(self):
        from test_travel_agent import run

        state = self.review()
        request = BookingRequest(option_id=state["selected"], revision=1, confirm=True, idempotency_key="old-order")
        receipt = simulate_purchase(state, request)
        state.update(stage="booked", bookings={"old-order": receipt}, receipt=receipt)
        runner = AsyncMock(side_effect=run)
        graph = build_graph(AsyncMock(return_value=SupervisorDecision(action="experience", patch=TripDelta(interests=["музеи"]))), runner, InMemorySaver())
        result = await graph.ainvoke({**state, "messages": [HumanMessage(content="Добавь музеи, отель и билеты оставь")], "calls": 0}, {"configurable": {"thread_id": "amendment"}})
        self.assertEqual([c.args[0] for c in runner.await_args_list], ["experience"])
        self.assertEqual(result["selected_transport"], state["selected_transport"])
        self.assertEqual(result["selected_stay"], state["selected_stay"])
        self.assertEqual(result["bookings"]["old-order"], receipt)
        self.assertEqual(result["stage"], "itinerary")


class ProfileTests(unittest.TestCase):
    def test_local_profile_survives_restart_and_is_isolated(self):
        from fastapi.testclient import TestClient
        from travel_agent.api import create_app

        env = {"MODEL": "offline", "TOKEN": "offline-token", "BASE_URL": "https://example.invalid/v1", "TRAVEL_API_TOKEN": "alice,bob"}
        alice = {"Authorization": "Bearer alice"}
        bob = {"Authorization": "Bearer bob"}
        async def decide(state):
            if state["messages"][-1].content == "Запомни прогулки":
                return SupervisorDecision(action="remember", profile_interests=["прогулки"])
            return SupervisorDecision(action="chat", reply="Привет!")
        with tempfile.TemporaryDirectory() as directory, patch("travel_agent.api.environment", return_value=env), patch("travel_agent.api.llm_decider", return_value=decide):
            path = str(Path(directory) / "profiles.sqlite")
            with TestClient(create_app(local_database=path)) as api:
                trip = api.post("/trips", headers=alice).json()["trip_id"]
                response = api.post(f"/trips/{trip}/messages", headers=alice, json={"message": "Запомни прогулки", "revision": 0})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(api.get("/profile", headers=alice).json()["interests"], ["прогулки"])
            with TestClient(create_app(local_database=path)) as api:
                self.assertEqual(api.get("/profile", headers=alice).json()["interests"], ["прогулки"])
                self.assertEqual(api.get("/profile", headers=bob).json()["interests"], [])
                trip = api.post("/trips", headers=alice).json()["trip_id"]
                result = api.post(f"/trips/{trip}/messages", headers=alice, json={"message": "Привет", "revision": 0}).json()
                self.assertEqual(result["constraints"]["interests"], ["прогулки"])
                self.assertEqual(api.get(f"/trips/{trip}", headers=bob).status_code, 404)
