import json
import unittest
from datetime import timedelta
from unittest.mock import AsyncMock

from langchain_core.exceptions import OutputParserException
from pydantic import ValidationError

from travel_agent.engine import apply_delta, compose, diagnose
from travel_agent.graph import supervise
from travel_agent.schemas import TripDelta
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
