import json
import unittest
from datetime import timedelta
from unittest.mock import AsyncMock

from langchain_core.exceptions import OutputParserException
from pydantic import ValidationError

from travel_agent.engine import apply_delta, compose, diagnose
from travel_agent.graph import supervise
from travel_agent.graph import build_graph
from travel_agent.schemas import SpecialistResult, SupervisorDecision, TripDelta, TripScenario
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
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
        planner = AsyncMock(return_value=SupervisorDecision(action="scenarios", scenarios=[self.scenario(str(i)) for i in range(4)]))
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

    async def test_night_flight_waits_for_agreement_before_hotel_search(self):
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
        self.assertTrue(state["pending_check_in"])
        self.assertEqual([c.args[0] for c in runner.await_args_list], ["transport"])
        self.assertIsNone(state["constraints"]["check_in"])
        state = await graph.ainvoke({"messages": [HumanMessage(content="Да, заселение с прилёта")], "calls": 0}, config)
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
