import json
import unittest
from datetime import timedelta
from functools import partial
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from travel_agent.agents.transport.agent import run as run_transport
from travel_agent.agents.stays.agent import run as run_stays
from travel_agent.agents.experience.agent import run as run_experience
from travel_agent.api import create_app
from travel_agent.graph import build_graph
from travel_agent.prompts import load_prompt
from travel_agent.schemas import SupervisorDecision, TripDelta
from test_agent_isolation import ToolModel, selection
from test_travel_agent import FIXTURES, TRIP


class PipelineE2ETests(unittest.TestCase):
    def test_api_runs_real_agents_and_selectively_refreshes_sources(self):
        calls = []

        async def source(role, provider, method, args, env, owned):
            calls.append((role, method, dict(args)))
            data = json.loads(json.dumps(FIXTURES[method]))
            if method == "search_hotels":
                data["stay"].update(
                    check_in=args["check_in"], check_out=args["check_out"]
                )
                for row in data["hotels"]:
                    row["checkout_ref"]["adults"] = args["adults"]
            elif method == "search_avia":
                data["meta"]["pricing"]["passengers"]["full"] = args["adults"]
                for row in data["offers"]:
                    for key in ("departure_at", "arrival_at"):
                        row[key] = args["departure_date"] + row[key][10:]
                    row["return_departure_at"] = (
                        args["return_date"] + row["return_departure_at"][10:]
                    )
            return {"status": "ok", "data": data}

        async def planner(state):
            if state.get("calls", 0):
                return SupervisorDecision(action="compose")
            message = state["messages"][-1].content
            patch = {
                "начать": TripDelta(origin="Москва", adults=2, purpose="Прогулки"),
                "даты": TripDelta(start=TRIP.start, end=TRIP.end),
                "отель": TripDelta(hotel="Mirror"),
                "бюджет": TripDelta(budget=80000),
                "сдвиг": TripDelta(
                    start=TRIP.start + timedelta(days=1),
                    end=TRIP.end + timedelta(days=1),
                ),
                "гости": TripDelta(adults=3),
            }.get(message, TripDelta())
            if message == "вопрос":
                return SupervisorDecision(action="answer", source_ids=["hotel:9573823"])
            return SupervisorDecision(action="compose", patch=patch)

        client = httpx.AsyncClient()
        runners = {
            role: partial(
                run,
                model=ToolModel(responses=[selection()]),
                client=client,
                env={},
                prompt=load_prompt(role),
            )
            for role, run in [
                ("transport", run_transport),
                ("stays", run_stays),
                ("experience", run_experience),
            ]
        }
        graph = build_graph(planner, runners, InMemorySaver())
        app = create_app(graph, tokens=("test-user",))
        with (
            patch("travel_agent.tools.runtime_call", side_effect=source),
            TestClient(app) as api,
        ):
            headers = {"Authorization": "Bearer test-user"}
            trip_id = api.post("/trips", headers=headers).json()["trip_id"]
            url = "/trips/" + trip_id
            revision = 0

            def send(message):
                nonlocal revision
                response = api.post(
                    url + "/messages",
                    headers=headers,
                    json={"message": message, "revision": revision},
                )
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                revision = result["revision"]
                return result

            result = send("начать")
            self.assertEqual(result["status"], "needs_input")
            self.assertEqual(calls, [])
            result = send("даты")
            self.assertEqual(result["status"], "ready")
            self.assertEqual(len(result["options"]), 3)
            self.assertEqual(
                [c[1] for c in calls], ["search_avia", "search_hotels", "search_places"]
            )
            transport = result["results"]["transport"]
            calls.clear()
            result = send("отель")
            self.assertEqual([c[1] for c in calls], ["search_places"])
            self.assertEqual(result["results"]["transport"], transport)
            self.assertTrue(
                all("Mirror" in o["stay"]["name"] for o in result["options"])
            )
            calls.clear()
            result = send("бюджет")
            self.assertEqual(calls, [])
            self.assertEqual(result["constraints"]["budget"], "80000")
            result = send("вопрос")
            self.assertEqual(calls, [])
            self.assertIn("Mirror", result["answer"])
            result = send("сдвиг")
            self.assertEqual(
                [c[1] for c in calls], ["search_avia", "search_hotels", "search_places"]
            )
            self.assertEqual(result["status"], "ready")
            self.assertTrue(
                all(o["transport"]["start"] == "2026-11-13" for o in result["options"])
            )
            calls.clear()
            result = send("гости")
            self.assertEqual(len(calls), 3)
            self.assertEqual(result["options"][0]["stay"]["adults"], 3)
            option = result["options"][0]
            self.assertIsNone(option["budget"]["confirmed_total"])
            self.assertEqual(
                api.post(
                    url + "/select/" + option["id"],
                    headers=headers,
                    params={"revision": revision},
                ).status_code,
                200,
            )
            request = {
                "option_id": option["id"],
                "revision": revision,
                "confirm": True,
                "idempotency_key": "stable-pipeline-key",
            }
            first = api.post(url + "/bookings", headers=headers, json=request)
            second = api.post(url + "/bookings", headers=headers, json=request)
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(first.json(), second.json())
            self.assertFalse(first.json()["reserved"])
            self.assertEqual(len(calls), 3)
            api.portal.call(client.aclose)

    def test_turn_deadline_has_explicit_http_status(self):
        from test_travel_agent import decide, run

        graph = build_graph(decide, run, InMemorySaver())
        with TestClient(create_app(graph, tokens=("timeout-user",))) as api:
            headers = {"Authorization": "Bearer timeout-user"}
            trip = api.post("/trips", headers=headers).json()["trip_id"]
            with patch.object(
                graph, "ainvoke", new=AsyncMock(side_effect=TimeoutError)
            ):
                result = api.post(
                    f"/trips/{trip}/messages",
                    headers=headers,
                    json={"message": "Plan", "revision": 0},
                )
            self.assertEqual(result.status_code, 504)
            self.assertEqual(
                api.get(f"/trips/{trip}", headers=headers).status_code, 200
            )
