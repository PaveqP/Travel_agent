import asyncio
import json
import unittest
from contextlib import asynccontextmanager
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from travel_agent.agents.supervisor.agent import llm_planner
from travel_agent.api import create_app
from travel_agent.engine import compose_packages, offer_card
from travel_agent.graph import build_graph
from travel_agent.schemas import ProposedDay, SpecialistResult, TripDelta, TurnPlan
from travel_agent.tools import build_tools
import test_autonomous_planning as planning_tests
from test_autonomous_planning import ROLES, result, task
from test_travel_agent import TRIP


class TourCompletionTests(unittest.IsolatedAsyncioTestCase):
    async def test_complete_request_assembles_without_optional_question_or_budget(self):
        graph, runners = planning_tests.PlanningTests().graph([TurnPlan(action='clarify', reply='Какой отель и бюджет предпочитаете?')])
        state = await graph.ainvoke({'constraints': TRIP.model_dump(mode='json')}, {'configurable': {'thread_id': 'optional-question'}})
        self.assertEqual(state['status'], 'ready')
        self.assertTrue(state['options'])
        for option in state['options']:
            self.assertTrue(option['transport'] and option['stay'])
            self.assertTrue(any(day['candidates'] for day in option['days']))
            self.assertEqual(Decimal(option['budget']['known_subtotal']),
                             Decimal(option['transport']['price']['amount']) + Decimal(option['stay']['price']['amount']))
        self.assertEqual([runners[r].await_count for r in ROLES], [1, 1, 1])

    async def test_missing_origin_is_asked_once_then_trip_is_completed(self):
        graph, runners = planning_tests.PlanningTests().graph([
            TurnPlan(action='clarify', reply='Из какого города отправляетесь?'),
            TurnPlan(action='plan', patch=TripDelta(origin=TRIP.origin)),
        ])
        config = {'configurable': {'thread_id': 'missing-origin'}}
        first = await graph.ainvoke({'constraints': TRIP.model_copy(update={'origin': None}).model_dump(mode='json')}, config)
        self.assertEqual(first['status'], 'needs_input')
        self.assertEqual(first['answer'], 'Из какого города отправляетесь?')
        for run in runners.values():
            run.assert_not_awaited()
        state = await graph.ainvoke({'messages': [HumanMessage(content=TRIP.origin)]}, config)
        self.assertEqual(state['status'], 'ready')
        self.assertTrue(state['options'])
        self.assertEqual(state['constraints']['start'], str(TRIP.start))

    async def test_train_arrival_sets_hotel_dates_even_when_planner_omits_dependency(self):
        observed = []
        async def transport(trip, revision, goal, previous):
            row = result('transport', trip, revision)
            row.candidates = [row.candidates[0].model_copy(update={
                'transport_mode': 'rail', 'arrival_at': row.candidates[0].arrival_at + timedelta(days=2)})]
            return row
        async def stays(trip, revision, goal, previous):
            observed.append(trip.stay_start)
            row = result('stays', trip, revision)
            for candidate in row.candidates:
                candidate.start, candidate.end = trip.stay_start, trip.stay_end
            return row
        runners = {'transport': transport, 'stays': stays, 'experience': AsyncMock(side_effect=lambda trip, revision, *_: result('experience', trip, revision))}
        graph = build_graph(AsyncMock(return_value=TurnPlan(action='plan', tasks=[task(r) for r in ROLES])), runners, InMemorySaver(), autonomous=True)
        state = await graph.ainvoke({'constraints': TRIP.model_dump(mode='json')}, {'configurable': {'thread_id': 'rail-arrival'}})
        self.assertEqual(observed, [TRIP.start + timedelta(days=2)])
        self.assertTrue(state['options'])
        self.assertTrue(all(option['stay']['start'] == str(TRIP.start + timedelta(days=2)) for option in state['options']))
        self.assertEqual(state['constraints']['start'], str(TRIP.start))

    async def test_recovered_transport_refreshes_hotel_in_same_repair_round(self):
        calls = []
        async def transport(trip, revision, goal, previous):
            calls.append('transport')
            if calls.count('transport') == 1:
                return SpecialistResult(role='transport', revision=revision, status='partial', warnings=['tutu:schema_error'])
            row = result('transport', trip, revision)
            for candidate in row.candidates:
                candidate.arrival_at += timedelta(days=1)
            return row
        async def stays(trip, revision, goal, previous):
            calls.append('stays')
            row = result('stays', trip, revision)
            for candidate in row.candidates:
                candidate.start = trip.stay_start
            return row
        experience = AsyncMock(side_effect=lambda trip, revision, *_: result('experience', trip, revision))
        planner = AsyncMock(side_effect=[TurnPlan(action='plan'), TurnPlan(action='plan', tasks=[task('transport'), task('experience')])])
        graph = build_graph(planner, {'transport': transport, 'stays': stays, 'experience': experience}, InMemorySaver(), autonomous=True)
        state = await graph.ainvoke({'constraints': TRIP.model_dump(mode='json')}, {'configurable': {'thread_id': 'recover-transport'}})
        self.assertEqual(calls, ['transport', 'stays', 'transport', 'stays'])
        experience.assert_awaited_once()
        self.assertEqual(state['search_round'], 1)
        self.assertEqual(state['feedback'], [])
        self.assertEqual(state['status'], 'ready')
        self.assertTrue(state['options'])

    async def test_full_trip_hotel_selection_continues_assembly(self):
        rows = {role: result(role, TRIP, 1).model_dump(mode='json') for role in ROLES}
        hotel = rows['stays']['candidates'][0]
        graph, runners = planning_tests.PlanningTests().graph([])
        state = await graph.ainvoke({'constraints': TRIP.model_dump(mode='json'), 'results': rows, 'stage': 'review',
            'requested_choice': hotel['id'], 'focus': None}, {'configurable': {'thread_id': 'select-hotel-in-tour'}})
        self.assertTrue(state['options'])
        self.assertTrue(all(hotel['name'] in option['stay']['name'] for option in state['options']))
        self.assertNotIn('попросите', state['answer'])
        runners['transport'].assert_not_awaited()

    async def test_recovered_transport_also_moves_program_out_of_travel_days(self):
        calls = {role: 0 for role in ROLES}
        async def run(role, trip, revision, goal, previous):
            calls[role] += 1
            row = result(role, trip, revision)
            if role == 'transport':
                if calls[role] == 1:
                    return row.model_copy(update={'candidates': []})
                for candidate in row.candidates:
                    candidate.arrival_at += timedelta(days=2)
            elif role == 'stays':
                for candidate in row.candidates:
                    candidate.start = trip.stay_start
            elif calls[role] == 2:
                row.days = [ProposedDay(date=trip.start + timedelta(days=3), source_ids=[row.candidates[0].id])]
            return row
        runners = {}
        for role in ROLES:
            async def runner(*args, role=role):
                return await run(role, *args)
            runners[role] = runner
        graph = build_graph(AsyncMock(side_effect=[TurnPlan(action='plan'), TurnPlan(action='plan')]), runners, InMemorySaver(), autonomous=True)
        state = await graph.ainvoke({'constraints': TRIP.model_dump(mode='json')}, {'configurable': {'thread_id': 'repair-calendar'}})
        self.assertEqual(calls, dict.fromkeys(ROLES, 2))
        self.assertEqual(state['search_round'], 1)
        self.assertEqual(state['status'], 'ready')
        for option in state['options']:
            self.assertTrue(any(day['candidates'] for day in option['days']))
            self.assertTrue(all(not day['candidates'] for day in option['days'][:2]))

    async def test_full_trip_answer_action_cannot_replace_assembly(self):
        rows = {role: result(role, TRIP, 1).model_dump(mode='json') for role in ROLES}
        graph, runners = planning_tests.PlanningTests().graph([TurnPlan(action='answer', focus='trip', reply='Вот отели.')])
        state = await graph.ainvoke({'constraints': TRIP.model_dump(mode='json'), 'results': rows}, {'configurable': {'thread_id': 'assemble-from-evidence'}})
        self.assertTrue(state['options'])
        self.assertNotEqual(state['answer'], 'Вот отели.')
        for run in runners.values():
            run.assert_not_awaited()

    async def test_planner_rechecks_answer_when_trip_remains_unassembled(self):
        structured = Mock(ainvoke=AsyncMock(side_effect=[TurnPlan(action='answer', reply='Вот отели.'), TurnPlan(action='plan', focus='trip')]))
        model = Mock(with_structured_output=Mock(return_value=structured))
        rows = {role: result(role, TRIP, 1).model_dump(mode='json') for role in ROLES}
        decision = await llm_planner(model, 'Offline planner')({'constraints': TRIP.model_dump(mode='json'), 'results': rows,
            'messages': [HumanMessage(content='Собери полный тур')]})
        self.assertEqual(decision.action, 'plan')
        context = json.loads(structured.ainvoke.await_args.args[0][2].content)
        self.assertTrue(context['plan_review']['unassembled_trip'])

    async def test_timeout_assembles_completed_workers_before_returning(self):
        cancelled = asyncio.Event()
        async def experience(*args):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        graph, _ = planning_tests.PlanningTests().graph([TurnPlan(action='plan')], {
            'transport': AsyncMock(side_effect=lambda trip, revision, *_: result('transport', trip, revision)),
            'stays': AsyncMock(side_effect=lambda trip, revision, *_: result('stays', trip, revision)), 'experience': experience})
        app = create_app(graph, tokens=('alice',))
        async with app.router.lifespan_context(app), httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test', headers={'Authorization': 'Bearer alice'}) as client:
            ident = (await client.post('/trips')).json()['trip_id']
            import hashlib
            config = {'configurable': {'thread_id': hashlib.sha256(b'alice').hexdigest() + ':' + ident}}
            await graph.aupdate_state(config, {'constraints': TRIP.model_dump(mode='json'),
                'results': {'transport': result('transport', TRIP, 0).model_dump(mode='json')}})
            with patch('travel_agent.api.AUTONOMOUS_TURN_TIMEOUT_SECONDS', 0.3):
                response = await client.post(f'/trips/{ident}/messages', json={'message': 'Собери поездку', 'revision': 0})
            self.assertEqual(response.status_code, 200)
            state = response.json()
            self.assertTrue(cancelled.is_set())
            self.assertTrue(state['options'])
            self.assertEqual(state['status'], 'partial')
            self.assertEqual((await client.get(f'/trips/{ident}')).json()['options'], state['options'])

    async def test_flight_search_requests_full_evidence_and_exposes_provider_reason(self):
        session = SimpleNamespace(
            list_tools=AsyncMock(return_value=SimpleNamespace(tools=[SimpleNamespace(name='search_avia', inputSchema={'type': 'object'})])),
            call_tool=AsyncMock(return_value=SimpleNamespace(isError=True, content=[SimpleNamespace(type='text', text='No airport in destination; use a transport city')])),
        )
        @asynccontextmanager
        async def connection(*args):
            yield session, None
        async with httpx.AsyncClient() as client:
            tools = {t.name: t for t in build_tools('transport', TRIP, 1, client, {}, {}, [], {'tools': 0}, autonomous=True)}
            with patch('integrations.mcp.client.connection', new=connection):
                response = await tools['search_flights'].ainvoke({})
            self.assertEqual(session.call_tool.await_args.args[1]['view'], 'full')
            self.assertEqual(response['status'], 'schema_error')
            self.assertIn('No airport', response['reason'])
            session.call_tool.assert_awaited_once()

    def test_air_baggage_requirement_does_not_block_rail_alternative(self):
        trip = TRIP.model_copy(update={'baggage': 'required', 'transport_modes': ['rail']})
        rows = {role: result(role, trip, 1) for role in ROLES}
        for candidate in rows['transport'].candidates:
            candidate.transport_mode = 'rail'
            candidate.baggage_included = None
            self.assertTrue(offer_card(candidate, trip).selectable)
        options, feedback = compose_packages(trip, {r: row.model_dump(mode='json') for r, row in rows.items()}, 1)
        self.assertTrue(options)
        self.assertNotIn('unverified_baggage', [item.code for item in feedback])
