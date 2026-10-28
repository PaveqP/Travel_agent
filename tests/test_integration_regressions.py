import asyncio
import copy
import json
import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import httpx
from langchain_core.messages import HumanMessage

from travel_agent.agents.research import research
from travel_agent.agents.supervisor.agent import llm_decider
from travel_agent.agents.supervisor.response import render_stage
from travel_agent.graph import planning
from travel_agent.prompts import load_prompt
from travel_agent.schemas import SupervisorDecision, TripDelta
from travel_agent.tools import build_tools
from test_agent_isolation import ToolModel, selection
from test_travel_agent import FIXTURES, TRIP, agreed_state


class IntegrationRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_latest_user_request_follows_runtime_context(self):
        query = "Из Москвы в Сочи, 12–17 ноября, двое, бюджет 100000"

        async def decide(messages):
            self.assertEqual(messages[-1].content, query)
            self.assertIn("constraints", json.loads(messages[1].content))
            return SupervisorDecision(
                action="clarify",
                patch=TripDelta(
                    origin="Москва", adults=2, start="2026-11-12", end="2026-11-17"
                ),
            )

        model = Mock()
        model.with_structured_output.side_effect = lambda schema, **kwargs: (
            Mock(ainvoke=AsyncMock(return_value=TripDelta()))
            if schema is TripDelta
            else Mock(ainvoke=decide)
        )
        result = await llm_decider(model, load_prompt("supervisor"))(
            {"messages": [HumanMessage(content=query)]}
        )
        self.assertEqual(result.patch.origin, "Москва")

    async def test_transport_details_pass_observed_offer_not_only_id(self):
        async with httpx.AsyncClient() as client:
            evidence = {}
            tools = {
                t.name: t
                for t in build_tools(
                    "transport", TRIP, 1, client, {}, evidence, [], {"tools": 0}
                )
            }

            async def source(role, provider, method, args, env, owned):
                if method == "search_avia":
                    return {"status": "ok", "data": FIXTURES["search_avia"]}
                self.assertIn(("avia", args["offer_id"]), owned)
                self.assertEqual(args["details_ref"]["offer_id"], args["offer_id"])
                self.assertIn(args["details_ref"], FIXTURES["search_avia"]["offers"])
                return {"status": "ok", "data": {"offer": args["details_ref"]}}

            with patch(
                "travel_agent.tools.runtime_call", new=AsyncMock(side_effect=source)
            ):
                await tools["search_flights"].ainvoke({})
                result = await tools["transport_details"].ainvoke(
                    {"source_id": next(iter(evidence))}
                )
            self.assertEqual(result["status"], "ok")

    async def test_hotel_metadata_reaches_specialist_without_changing_price(self):
        data = copy.deepcopy(FIXTURES["search_hotels"])
        data["hotels"][0].update(
            stars=4, rating=9.2, review_count=123, address="Улица Приморская, 1"
        )
        async with httpx.AsyncClient() as client:
            evidence = {}
            tool = next(
                t
                for t in build_tools(
                    "stays", TRIP, 1, client, {}, evidence, [], {"tools": 0}
                )
                if t.name == "search_hotels"
            )
            with patch(
                "travel_agent.tools.runtime_call",
                new=AsyncMock(return_value={"status": "ok", "data": data}),
            ):
                result = await tool.ainvoke({})
        hotel = result["candidates"][0]
        self.assertEqual(
            (hotel["stars"], hotel["rating"], hotel["review_count"]), (4, "9.2", 123)
        )
        self.assertIn("9.2/10", hotel["description"])
        self.assertEqual(
            Decimal(hotel["price"]["amount"]),
            Decimal(str(data["hotels"][0]["best_offer"]["price"]["amount"])),
        )

    async def test_selected_hotel_can_be_researched_without_tavily(self):
        state = agreed_state("review")
        state["decision"] = {
            "action": "research",
            "research_role": "stays",
            "task": "Есть ли бассейн у выбранного отеля?",
        }
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: self.fail("Unexpected web request")
            )
        ) as client:
            source = AsyncMock(
                return_value={
                    "status": "ok",
                    "data": {
                        "hotel": {"name": "Отель", "amenities": ["Бассейн"]},
                        "rooms": [],
                    },
                }
            )
            with patch("travel_agent.tools.runtime_call", new=source):
                result = await research(
                    state,
                    models={"stays": ToolModel(responses=[selection()])},
                    client=client,
                    env={},
                    prompt=load_prompt("research"),
                )
        self.assertEqual(source.await_count, 1)
        self.assertEqual(source.await_args.args[2], "get_offer_details")
        self.assertEqual(source.await_args.args[3]["product_type"], "hotels")
        self.assertEqual(len(result.sources), 1)
        self.assertTrue(result.sources[0].title.startswith("Туту:"))
        self.assertIn("Бассейн", result.sources[0].text)

    async def test_foreign_hotel_dates_cannot_seed_tool_ownership(self):
        state = agreed_state("review")
        from travel_agent.schemas import Candidate

        hotel = next(
            Candidate.model_validate(c) for c in state["results"]["stays"]["candidates"]
        )
        hotel.adults = 6
        async with httpx.AsyncClient() as client:
            tool = next(
                t
                for t in build_tools(
                    "stays", TRIP, 1, client, {}, {hotel.id: hotel}, [], {"tools": 0}
                )
                if t.name == "hotel_details"
            )
            with patch("integrations.mcp.client.connection") as network:
                result = await tool.ainvoke({"source_id": hotel.id})
                network.assert_not_called()
        self.assertEqual(result["status"], "forbidden")

    async def test_empty_train_schedule_is_empty_not_successful_quote(self):
        async with httpx.AsyncClient() as client:
            evidence = {}
            tool = next(
                t
                for t in build_tools(
                    "transport", TRIP, 1, client, {}, evidence, [], {"tools": 0}
                )
                if t.name == "search_trains"
            )
            with patch(
                "travel_agent.tools.runtime_call",
                new=AsyncMock(return_value={"status": "ok", "data": {"offers": []}}),
            ):
                result = await tool.ainvoke({"mode": "etrain"})
        self.assertEqual(result["status"], "empty")
        self.assertEqual(evidence, {})

    async def test_route_timeout_preserves_places_and_stops_slow_call(self):
        state = agreed_state("review")
        from travel_agent.schemas import Candidate

        place = next(
            Candidate.model_validate(c)
            for c in state["results"]["experience"]["candidates"]
        )
        evidence, warnings = {place.id: place}, []
        timeout = asyncio.timeout

        async def slow(*args):
            await asyncio.sleep(1)

        def deadline(seconds):
            self.assertLessEqual(seconds, 15)
            return timeout(0.01)

        async with httpx.AsyncClient() as client:
            tool = next(
                t
                for t in build_tools(
                    "experience", TRIP, 1, client, {}, evidence, warnings, {"tools": 0}
                )
                if t.name == "route"
            )
            with (
                patch("travel_agent.tools.runtime_call", side_effect=slow),
                patch("travel_agent.tools.asyncio.timeout", side_effect=deadline),
            ):
                result = await tool.ainvoke({"source_id": place.id})
        self.assertEqual(result["status"], "timeout")
        self.assertIn("2gis:timeout", warnings)
        self.assertIn(place.id, evidence)

    def test_unfinished_selection_does_not_fill_days_with_arbitrary_catalog(self):
        state = agreed_state("itinerary")
        state["results"]["experience"].update(
            status="partial", warnings=["agent_limit"], selected_ids=[]
        )
        result = planning(state)
        self.assertTrue(result["options"])
        self.assertTrue(
            all(not day["candidates"] for day in result["options"][0]["days"])
        )
        self.assertIn("Места пока не отобраны", render_stage({**state, **result}))

    async def test_separate_extraction_recovers_dates_omitted_by_planner(self):
        query = "С 12 по 16 ноября 2026 года"
        model = Mock()
        structured = AsyncMock(return_value=SupervisorDecision(action="compose"))
        extraction = AsyncMock(
            return_value=TripDelta(start="2026-11-12", end="2026-11-16")
        )
        model.with_structured_output.side_effect = lambda schema, **kwargs: Mock(
            ainvoke=extraction if schema is TripDelta else structured
        )
        result = await llm_decider(model, load_prompt("supervisor"))(
            {"messages": [HumanMessage(content=query)]}
        )
        self.assertEqual(str(result.patch.start), "2026-11-12")
        self.assertEqual(structured.await_count, 1)
        self.assertEqual(extraction.await_count, 1)
        self.assertEqual(extraction.await_args.args[0][-1].content, query)

    async def test_invalid_extraction_is_rejected_without_guessing(self):
        from pydantic import ValidationError

        model = Mock()
        structured = AsyncMock(return_value=SupervisorDecision(action="compose"))
        extraction = AsyncMock(return_value={"start": "not-a-date"})
        model.with_structured_output.side_effect = lambda schema, **kwargs: Mock(
            ainvoke=extraction if schema is TripDelta else structured
        )
        with self.assertRaises(ValidationError):
            await llm_decider(model, load_prompt("supervisor"))(
                {"messages": [HumanMessage(content="С 12 по 16 ноября 2026 года")]}
            )
        self.assertEqual(extraction.await_count, 2)

    async def test_date_question_does_not_force_constraint_changes(self):
        model = Mock()
        structured = AsyncMock(return_value=SupervisorDecision(action="research"))
        model.with_structured_output.return_value.ainvoke = structured
        result = await llm_decider(model, load_prompt("supervisor"))(
            {"messages": [HumanMessage(content="Какая погода 12 ноября?")]}
        )
        self.assertEqual(structured.await_count, 1)
        self.assertIsNone(result.patch.start)

    def test_catalog_does_not_implicitly_create_a_program(self):
        from integrations.schemas.models import Coordinates
        from travel_agent.engine import area_of, compose
        from test_travel_agent import candidates

        rows = candidates()
        place = next(c for c in rows if c.role == "experience")
        rows += [
            place.model_copy(
                update={
                    "id": f"mountain:{i}",
                    "name": f"Горное место {i}",
                    "coordinates": Coordinates(lat=43.68, lon=40.2),
                }
            )
            for i in range(4)
        ]
        option = compose(TRIP, rows, 1)[0]
        areas = {area_of(c.coordinates) for day in option.days for c in day.candidates}
        self.assertEqual(areas, set())
        for day in option.days:
            self.assertLessEqual(
                len({area_of(c.coordinates) for c in day.candidates}), 1
            )

    def test_catalog_does_not_implicitly_schedule_mountain_days(self):
        from datetime import timedelta
        from integrations.schemas.models import Coordinates
        from travel_agent.engine import compose
        from test_travel_agent import candidates

        trip = TRIP.model_copy(update={"end": TRIP.end + timedelta(days=1)})
        rows = candidates()
        for row in rows:
            if row.role in ("transport", "stays"):
                row.end = trip.end
            if row.role == "transport":
                row.return_departure_at += timedelta(days=1)
        place = next(c for c in rows if c.role == "experience")
        rows += [
            place.model_copy(
                update={
                    "id": f"sirius:{i}",
                    "coordinates": Coordinates(lat=43.405, lon=39.96),
                }
            )
            for i in range(4)
        ]
        rows += [
            place.model_copy(
                update={
                    "id": f"mountain:{i}",
                    "coordinates": Coordinates(lat=43.68, lon=40.2),
                    "area": "Красная Поляна",
                }
            )
            for i in range(4)
        ]
        option = compose(trip, rows, 1)[0]
        self.assertEqual(
            sum(
                any(c.area == "Красная Поляна" for c in day.candidates)
                for day in option.days
            ),
            0,
        )
