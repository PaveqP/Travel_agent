import asyncio
import json
from copy import deepcopy
from decimal import Decimal
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from pydantic import ValidationError

from travel_agent.api import create_app
from travel_agent.engine import compose_packages, simulate_purchase
from travel_agent.graph import build_graph
from travel_agent.schemas import AgentTask, BookingRequest, ProposedDay, SpecialistResult, TripDelta, TripScenario, TurnPlan
from test_travel_agent import TRIP, candidates

ROLES = ('transport', 'stays', 'experience')


def task(role, depends_on=()):
    return AgentTask(role=role, goal='Сравни подходящие реальные предложения', depends_on=list(depends_on))


def result(role, trip, revision):
    rows = [c for c in candidates() if c.role == role]
    for c in rows:
        if role in ('transport', 'stays'):
            offset = trip.start - TRIP.start
            c.start += offset
            c.end += offset
            if role == 'transport':
                c.arrival_at += offset
                c.departure_at += offset
                c.return_departure_at += offset
    days = [ProposedDay(date=trip.start + timedelta(days=1), source_ids=[rows[0].id], purpose='Прогулка')] if role == 'experience' else []
    return SpecialistResult(role=role, revision=revision, status='ok', candidates=rows, days=days)


class PlanningTests(unittest.IsolatedAsyncioTestCase):
    async def test_parallel_complete_packages_and_no_forced_choices(self):
        started, gate = set(), asyncio.Event()
        async def run(role, trip, revision, goal, previous):
            started.add(role)
            if len(started) == 3:
                gate.set()
            await asyncio.wait_for(gate.wait(), 1)
            return result(role, trip, revision)
        async def transport(*args): return await run('transport', *args)
        async def stays(*args): return await run('stays', *args)
        async def experience(*args): return await run('experience', *args)
        graph = build_graph(AsyncMock(return_value=TurnPlan(action='plan', tasks=[task(r) for r in ROLES])),
                            dict(zip(ROLES, (transport, stays, experience))), InMemorySaver(), autonomous=True)
        state = await graph.ainvoke({'constraints': TRIP.model_dump(mode='json'), 'messages': [HumanMessage(content='Поехали')]}, {'configurable': {'thread_id': 'parallel'}})
        self.assertEqual(started, set(ROLES))
        self.assertEqual(state['status'], 'ready')
        self.assertEqual(len(state['options']), 5)
        self.assertEqual(len({o['id'] for o in state['options']}), 5)
        self.assertEqual(state['feedback'], [])
        self.assertTrue(all(o['transport'] and o['stay'] for o in state['options']))
        self.assertTrue(state['options'][0]['days'][1]['candidates'])
        self.assertIsNone(state['options'][0]['budget']['confirmed_total'])

    def graph(self, decisions, runners=None, saver=None, present=None, research=None):
        if runners is None:
            runners = {}
            for role in ROLES:
                async def run(trip, revision, goal, previous, role=role):
                    return result(role, trip, revision)
                runners[role] = AsyncMock(side_effect=run)
        return build_graph(AsyncMock(side_effect=decisions), runners, saver or InMemorySaver(), present=present, research=research, autonomous=True), runners

    async def test_full_trip_does_not_infer_component_scope_from_one_task(self):
        graph, runners = self.graph([TurnPlan(action='plan', tasks=[task('stays')])])
        state = await graph.ainvoke({'constraints': TRIP.model_dump(mode='json')}, {'configurable': {'thread_id': 'whole-trip'}})
        self.assertIsNone(state['focus'])
        self.assertTrue(state['options'])
        self.assertTrue(all(o['transport'] and o['stay'] and any(d['candidates'] for d in o['days']) for o in state['options']))
        self.assertEqual([runners[r].await_count for r in ROLES], [1, 1, 1])

    def test_suggested_program_uses_evidence_dates_and_preserves_costs(self):
        from datetime import datetime, timezone
        from travel_agent.engine import suggested_program
        from travel_agent.schemas import TripOption

        results = {role: result(role, TRIP, 1).model_dump(mode='json') for role in ROLES}
        results['experience']['days'] = []
        options, feedback = compose_packages(TRIP, results, 1)
        option = options[0]
        self.assertIn('no_day_plan', [f.code for f in feedback])
        self.assertTrue(any(day.candidates for day in option.days))
        self.assertEqual(option.days[0].candidates, [])
        self.assertEqual(option.days[-1].candidates, [])
        self.assertIsNone(option.budget.confirmed_total)
        empty = TripOption.model_validate(option.model_dump())
        for day in empty.days:
            day.candidates = []
        place = result('experience', TRIP, 1).candidates[0]
        now = datetime.now(timezone.utc)
        expired = place.model_copy(deep=True)
        expired.id, expired.name = 'expired', 'Expired'
        expired.source.expires_at = now - timedelta(seconds=1)
        duplicate = place.model_copy(update={'id': 'duplicate'})
        event = place.model_copy(update={'id': 'event', 'name': 'Dated event', 'start': TRIP.start + timedelta(days=2), 'end': TRIP.start + timedelta(days=2)})
        outside = place.model_copy(update={'id': 'outside', 'name': 'Other date', 'start': TRIP.end + timedelta(days=1)})
        planned = suggested_program(empty, [expired, outside, place, duplicate, event], now)
        scheduled = [(day.date, c) for day in planned for c in day.candidates]
        self.assertEqual([c.id for _, c in scheduled].count(place.id), 1)
        self.assertEqual({c.id for _, c in scheduled}, {place.id, event.id})
        self.assertEqual(next(day for day, c in scheduled if c.id == 'event'), event.start)
        self.assertTrue(all(len(day.candidates) <= 2 for day in planned))
        self.assertEqual(empty.budget, option.budget)
        with_plan = empty.model_copy(update={'days': planned})
        self.assertEqual(suggested_program(with_plan, [outside], now), planned)

    async def test_clarify_hotel_budget_dates_and_readonly_question(self):
        decisions = [TurnPlan(action='clarify', patch=TripDelta(destination='Сочи', origin='Москва', adults=2, purpose='Море'), reply='Когда поедете?'),
                     TurnPlan(action='plan', patch=TripDelta(start=TRIP.start, end=TRIP.end), tasks=[task(r) for r in ROLES]),
                     TurnPlan(action='plan', patch=TripDelta(hotel='Mirror'), tasks=[task('stays'), task('experience')]),
                     TurnPlan(action='plan', patch=TripDelta(budget=100000)),
                     TurnPlan(action='answer'),
                     TurnPlan(action='plan', patch=TripDelta(start=TRIP.start+timedelta(days=1), end=TRIP.end+timedelta(days=1)), tasks=[task(r) for r in ROLES])]
        graph, runners = self.graph(decisions, present=AsyncMock(return_value='Ответ пользователю'))
        config = {'configurable': {'thread_id': 'dialogue'}}
        state = await graph.ainvoke({'messages': [HumanMessage(content='Хочу отдых')]}, config)
        self.assertEqual(state['status'], 'needs_input')
        self.assertEqual(sum(r.await_count for r in runners.values()), 0)
        state = await graph.ainvoke({'messages': [HumanMessage(content='Даты')]}, config)
        transport = state['results']['transport']
        state = await graph.ainvoke({'messages': [HumanMessage(content='Отель')]}, config)
        self.assertEqual(runners['transport'].await_count, 1)
        self.assertEqual(state['results']['transport'], transport)
        self.assertTrue(all('mirror' in o['stay']['name'].lower() for o in state['options']))
        counts = [r.await_count for r in runners.values()]
        state = await graph.ainvoke({'messages': [HumanMessage(content='Бюджет')]}, config)
        self.assertEqual([r.await_count for r in runners.values()], counts)
        revision, options = state['revision'], state['options']
        state = await graph.ainvoke({'messages': [HumanMessage(content='Сколько на человека?')]}, config)
        self.assertEqual(state['revision'], revision)
        self.assertEqual(state['options'], options)
        state = await graph.ainvoke({'messages': [HumanMessage(content='Другие даты')]}, config)
        self.assertEqual(runners['transport'].await_count, 2)
        self.assertTrue(state['options'])
        self.assertTrue(all(o['transport']['start'] == '2026-11-13' for o in state['options']))

    async def test_addressed_repair_runs_once_and_preserves_other_roles(self):
        graph, runners = self.graph([TurnPlan(action='plan', tasks=[task(r) for r in ROLES]), TurnPlan(action='plan', tasks=[task('experience')])])
        async def empty(trip, revision, goal, previous):
            return result('experience', trip, revision).model_copy(update={'days': []})
        runners['experience'].side_effect = empty
        state = await graph.ainvoke({'constraints': TRIP.model_dump(mode='json')}, {'configurable': {'thread_id': 'repair'}})
        self.assertEqual([runners[r].await_count for r in ROLES], [1, 1, 2])
        self.assertEqual(state['search_round'], 1)
        self.assertIn('program_update_incomplete', [f['code'] for f in state['feedback']])
        self.assertEqual(state['status'], 'partial')
        self.assertFalse(state['repair_decision'])
        self.assertTrue(state['options'])

    async def test_dependencies_stale_results_and_persistence(self):
        config = {'configurable': {'thread_id': 'restart'}}
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'state.sqlite')
            async with AsyncSqliteSaver.from_conn_string(path) as saver:
                graph, _ = self.graph([TurnPlan(action='plan', tasks=[task(r) for r in ROLES])], saver=saver)
                valid = await graph.ainvoke({'constraints': TRIP.model_dump(mode='json')}, config)
            async with AsyncSqliteSaver.from_conn_string(path) as saver:
                graph, runners = self.graph([], saver=saver)
                stored = (await graph.aget_state(config)).values
                self.assertEqual(stored['options'], valid['options'])
                chosen = await graph.ainvoke({'requested_choice': stored['options'][0]['id']}, config)
                self.assertEqual(chosen['selected'], stored['options'][0]['id'])
                booking = simulate_purchase(chosen, BookingRequest(option_id=chosen['selected'], revision=chosen['revision'], confirm=True, idempotency_key='persist-test'))
                self.assertTrue(booking['simulated'])
                self.assertFalse(booking['paid'])
        for tasks in ([task('transport', ['stays']), task('stays', ['transport'])], [task('transport'), task('transport')]):
            with self.assertRaises(ValidationError):
                TurnPlan(action='plan', tasks=tasks)

    async def test_dependency_search_and_stale_rejection(self):
        sequence = []
        async def run(role, trip, revision, goal, previous):
            sequence.append(role)
            self.assertEqual(sequence, list(ROLES)[:len(sequence)])
            return result(role, trip, revision)
        async def transport(*args): return await run('transport', *args)
        async def stays(*args): return await run('stays', *args)
        async def experience(*args): return await run('experience', *args)
        graph, runners = self.graph([TurnPlan(action='plan', tasks=[task('transport'), task('stays', ['transport']), task('experience', ['stays'])])], dict(zip(ROLES, (transport, stays, experience))))
        state = await graph.ainvoke({'constraints': TRIP.model_dump(mode='json')}, {'configurable': {'thread_id': 'dependency'}})
        self.assertEqual(sequence, list(ROLES))
        self.assertTrue(state['options'])
        async def stale(*args): return result('transport', TRIP, 0)
        graph, _ = self.graph([TurnPlan(action='plan', tasks=[task(r) for r in ROLES]), TurnPlan(action='plan')], {'transport': stale, 'stays': AsyncMock(return_value=result('stays', TRIP, 1)), 'experience': AsyncMock(return_value=result('experience', TRIP, 1))})
        sequence.clear()
        state = await graph.ainvoke({'constraints': TRIP.model_dump(mode='json')}, {'configurable': {'thread_id': 'stale'}})
        self.assertFalse(state['results']['transport']['candidates'])
        self.assertFalse(state['options'])

    async def test_status_and_partial_previews_do_not_wait_for_trip_lock(self):
        gate, started = asyncio.Event(), asyncio.Event()
        async def decide(state):
            started.set()
            await gate.wait()
            return TurnPlan(action='chat', reply='Привет!')
        graph = build_graph(decide, {r: AsyncMock() for r in ROLES}, InMemorySaver(), autonomous=True)
        app = create_app(graph, tokens=('alice', 'bob'))
        async with app.router.lifespan_context(app), httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test', headers={'Authorization': 'Bearer alice'}) as client:
            ident = (await client.post('/trips')).json()['trip_id']
            pending = asyncio.create_task(client.post(f'/trips/{ident}/messages', json={'message': 'Привет', 'revision': 0}))
            await started.wait()
            status = await asyncio.wait_for(client.get(f'/trips/{ident}/status'), 1)
            self.assertEqual(status.json()['status'], 'running')
            self.assertTrue(status.json()['label'])
            snapshot = await asyncio.wait_for(client.get(f'/trips/{ident}'), 1)
            self.assertEqual(snapshot.status_code, 200)
            self.assertEqual((await client.get(f'/trips/{ident}/status', headers={'Authorization': 'Bearer bob'})).status_code, 404)
            gate.set()
            self.assertEqual((await pending).json()['answer'], 'Привет!')
            self.assertEqual((await client.get(f'/trips/{ident}/status')).json()['status'], 'finished')


class AutonomousToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_selects_its_first_tool_and_can_stop_without_network(self):
        from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
        from travel_agent.agents.stays.agent import run
        from travel_agent.prompts import read_prompts
        from test_travel_agent import FIXTURES

        class ToolModel(FakeMessagesListChatModel):
            def bind_tools(self, tools, **kwargs):
                return self

        first = ToolModel(responses=[AIMessage(content='', tool_calls=[{'name': 'SpecialistSelection', 'args': {'source_ids': [], 'gaps': ['Нужны условия']}, 'id': 'stop', 'type': 'tool_call'}])])
        async with httpx.AsyncClient() as client:
            with patch('travel_agent.tools.runtime_call', new=AsyncMock()) as network:
                row = await run(TRIP, 1, 'Оцени запрос', [], model=first, client=client, env={}, prompt=read_prompts()['stays'], autonomous=True)
                network.assert_not_called()
                self.assertEqual(row.tool_calls, 0)
                self.assertIn('no_evidence', row.warnings)
            model = ToolModel(responses=[
                AIMessage(content='', tool_calls=[{'name': 'search_hotels', 'args': {}, 'id': 'search', 'type': 'tool_call'}]),
                AIMessage(content='', tool_calls=[{'name': 'SpecialistSelection', 'args': {'source_ids': []}, 'id': 'finish', 'type': 'tool_call'}])])
            with patch('travel_agent.tools.runtime_call', new=AsyncMock(return_value={'status': 'ok', 'data': FIXTURES['search_hotels']})) as network:
                row = await run(TRIP, 1, 'Найди отели', [], model=model, client=client, env={}, prompt=read_prompts()['stays'], autonomous=True)
                self.assertEqual(network.await_count, 1)
                self.assertEqual(len(row.candidates), 3)
                self.assertTrue(all(c.provider_id for c in row.candidates))

    def test_rail_return_cost_party_and_hotel_arrival(self):
        from travel_agent.agents.transport.tools import rail_candidates
        outbound = json.loads((Path(__file__).parent / 'fixtures/rail_outbound.json').read_text())
        outbound['meta']['pricing']['passengers'] = 2
        inbound = deepcopy(outbound)
        inbound['meta']['from'], inbound['meta']['to'] = outbound['meta']['to'], outbound['meta']['from']
        for row in inbound['offers']:
            row['offer_id'] = 'return-' + row['offer_id']
            row['departure_at'] = '2026-11-16T10:00:00+03:00'
            row['arrival_at'] = '2026-11-18T01:00:00+03:00'
        rows = rail_candidates(outbound, inbound, TRIP, TRIP.start, TRIP.end)
        self.assertTrue(rows)
        self.assertEqual(rows[0].price.amount, Decimal(str(outbound['offers'][0]['price']['amount'])) * 4)
        self.assertEqual(len(rows[0].legs), 2)
        results = {r: result(r, TRIP, 1).model_dump(mode='json') for r in ROLES}
        results['transport']['candidates'] = [c.model_dump(mode='json') for c in rows]
        options, feedback = compose_packages(TRIP, results, 1)
        self.assertFalse(options)
        self.assertIn('arrival_stay_mismatch', [f.code for f in feedback])
        for stay in results['stays']['candidates']:
            stay['start'] = '2026-11-14'
        options, _ = compose_packages(TRIP, results, 1)
        self.assertTrue(options)
        self.assertTrue(all(o.transport.transport_mode == 'rail' for o in options))
        inbound['meta']['from'] = outbound['meta']['from']
        with self.assertRaises(ValueError):
            rail_candidates(outbound, inbound, TRIP, TRIP.start, TRIP.end)
        outbound['meta']['pricing']['passengers'] = 1
        with self.assertRaises(ValueError):
            rail_candidates(outbound, inbound, TRIP, TRIP.start, TRIP.end)

    def test_unknown_baggage_and_mountain_program_prevent_false_checkout(self):
        trip = TRIP.model_copy(update={'mountain_days': 2, 'baggage': 'required'})
        rows = {r: result(r, trip, 1).model_dump(mode='json') for r in ROLES}
        options, feedback = compose_packages(trip, rows, 1)
        self.assertNotIn('mountain_days_mismatch', [f.code for f in feedback])
        self.assertTrue(any('багаж' in w for w in options[0].warnings))
        state = {'constraints': trip.model_dump(mode='json'), 'options': [o.model_dump(mode='json') for o in options], 'selected': options[0].id, 'revision': 1, 'stage': 'review'}
        with self.assertRaises(ValueError):
            simulate_purchase(state, BookingRequest(option_id=options[0].id, revision=1, confirm=True, idempotency_key='baggage-test'))

    async def test_tools_remain_available_after_two_steps_and_reuse_evidence(self):
        from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
        from travel_agent.agents.stays.agent import run
        from travel_agent.prompts import read_prompts
        from test_travel_agent import FIXTURES

        bindings = []
        class ToolModel(FakeMessagesListChatModel):
            def bind_tools(self, tools, **kwargs):
                bindings.append([t.name for t in tools])
                return self
        source_ids = [c.id for c in candidates() if c.role == 'stays']
        model = ToolModel(responses=[
            AIMessage(content='', tool_calls=[{'name': 'search_hotels', 'args': {}, 'id': 'first', 'type': 'tool_call'}]),
            AIMessage(content='', tool_calls=[{'name': 'search_hotels', 'args': {}, 'id': 'second', 'type': 'tool_call'}]),
            AIMessage(content='', tool_calls=[{'name': 'SpecialistSelection', 'args': {'source_ids': []}, 'id': 'final', 'type': 'tool_call'}])])
        async with httpx.AsyncClient() as client:
            with patch('travel_agent.tools.runtime_call', new=AsyncMock(return_value={'status': 'ok', 'data': FIXTURES['search_hotels']})) as network:
                row = await run(TRIP, 1, 'Сравни', [], model=model, client=client, env={}, prompt=read_prompts()['stays'], autonomous=True)
                self.assertEqual(network.await_count, 1)
                self.assertIn('hotel_details', bindings[-1])
                self.assertIn('SpecialistSelection', bindings[-1])
                source_ids = [c.id for c in row.candidates]
            cached = ToolModel(responses=[AIMessage(content='', tool_calls=[{'name': 'SpecialistSelection', 'args': {'source_ids': source_ids}, 'id': 'cached', 'type': 'tool_call'}])])
            with patch('travel_agent.tools.runtime_call', new=AsyncMock()) as network:
                row = await run(TRIP, 1, 'Используй известные данные', row.candidates, model=cached, client=client, env={}, prompt=read_prompts()['stays'], autonomous=True)
                network.assert_not_called()
                self.assertEqual(row.selected_ids, source_ids)


    async def test_hotel_quotes_keep_date_identity_and_details_use_supplier_id(self):
        from travel_agent.tools import build_tools
        from test_travel_agent import FIXTURES
        calls = []
        async def source(role, provider, method, args, env, owned):
            calls.append((method, args, owned))
            if method == 'search_hotels':
                data = deepcopy(FIXTURES['search_hotels'])
                data['stay']['check_in'], data['stay']['check_out'] = args['check_in'], args['check_out']
                return {'status': 'ok', 'data': data}
            return {'status': 'ok', 'data': {'hotel': {'hotel_id': args['hotel_id'], 'name': 'Проверенный отель'}}}
        evidence = {}
        async with httpx.AsyncClient() as client:
            tools = {t.name: t for t in build_tools('stays', TRIP, 1, client, {}, evidence, [], {'tools': 0}, autonomous=True)}
            with patch('travel_agent.tools.runtime_call', side_effect=source):
                first = await tools['search_hotels'].ainvoke({})
                second = await tools['search_hotels'].ainvoke({'check_in': '2026-11-14'})
                self.assertTrue(set(c['id'] for c in first['candidates']).isdisjoint(c['id'] for c in second['candidates']))
                self.assertEqual(len(evidence), 6)
                ident = second['candidates'][0]['id']
                await tools['hotel_details'].ainvoke({'source_id': ident})
                args = calls[-1][1]
                self.assertEqual(args['check_in'], '2026-11-14')
                self.assertEqual(args['hotel_id'], evidence[ident].provider_id)
                self.assertIn(('hotels', args['hotel_id']), calls[-1][2])

class RepairTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_repair_decision_still_completes_observed_day_plan(self):
        calls = {r: 0 for r in ROLES}
        runners = {}
        for role in ROLES:
            async def run(trip, revision, goal, previous, role=role):
                calls[role] += 1
                row = result(role, trip, revision)
                if role == 'experience' and calls[role] == 1:
                    row.days = []
                if role == 'experience' and calls[role] == 2:
                    self.assertTrue(previous)
                return row
            runners[role] = run
        graph = build_graph(AsyncMock(side_effect=[TurnPlan(action='plan', tasks=[task(r) for r in ROLES]), TurnPlan(action='plan')]), runners, InMemorySaver(), autonomous=True)
        state = await graph.ainvoke({'constraints': TRIP.model_dump(mode='json')}, {'configurable': {'thread_id': 'repair-empty'}})
        self.assertEqual(calls, {'transport': 1, 'stays': 1, 'experience': 2})
        self.assertEqual(state['feedback'], [])
        self.assertEqual(state['status'], 'ready')


    async def test_question_after_partial_plan_is_not_treated_as_internal_repair(self):
        planner = AsyncMock(side_effect=[TurnPlan(action='plan', tasks=[task(r) for r in ROLES]), TurnPlan(action='plan'), TurnPlan(action='answer')])
        runners = {}
        for role in ROLES:
            async def run(trip, revision, goal, previous, role=role):
                row = result(role, trip, revision)
                if role == 'experience':
                    row.days = []
                return row
            runners[role] = AsyncMock(side_effect=run)
        async def present(state):
            return 'Это ответ на вопрос' if state['decision']['action'] == 'answer' else 'Это варианты'
        graph = build_graph(planner, runners, InMemorySaver(), present=present, autonomous=True)
        config = {'configurable': {'thread_id': 'partial-question'}}
        first = await graph.ainvoke({'constraints': TRIP.model_dump(mode='json')}, config)
        counts = [r.await_count for r in runners.values()]
        self.assertEqual(first['status'], 'partial')
        answered = await graph.ainvoke({'messages': [HumanMessage(content='Сколько на человека?')]}, config)
        self.assertEqual(answered['answer'], 'Это ответ на вопрос')
        self.assertEqual(answered['revision'], first['revision'])
        self.assertEqual(answered['options'], first['options'])
        self.assertEqual([r.await_count for r in runners.values()], counts)

    async def test_hotel_selection_and_cached_dependencies_keep_flight(self):
        planner = AsyncMock(side_effect=[TurnPlan(action='plan', tasks=[task(r) for r in ROLES]),
                                        TurnPlan(action='plan', patch=TripDelta(hotel='Mirror'), tasks=[task('stays', ['transport']), task('experience', ['stays'])])])
        runners = {}
        for role in ROLES:
            async def run(trip, revision, goal, previous, role=role):
                return result(role, trip, revision)
            runners[role] = AsyncMock(side_effect=run)
        graph = build_graph(planner, runners, InMemorySaver(), autonomous=True)
        cfg = {'configurable': {'thread_id': 'cached-dependency'}}
        first = await graph.ainvoke({'constraints': TRIP.model_dump(mode='json')}, cfg)
        changed = await graph.ainvoke({'messages': [HumanMessage(content='Замени отель, сохрани билеты')]}, cfg)
        self.assertEqual(runners['transport'].await_count, 1)
        self.assertEqual(changed['results']['transport'], first['results']['transport'])
        self.assertTrue(changed['options'])
        self.assertTrue(all('Mirror' in o['stay']['name'] for o in changed['options']))

    async def test_change_cannot_be_satisfied_by_selecting_an_unrelated_old_option(self):
        planner = AsyncMock(side_effect=[TurnPlan(action='plan', tasks=[task(r) for r in ROLES]), TurnPlan(action='select', patch=TripDelta(hotel='Mirror'), option_id='nonexistent')])
        runners = {}
        for role in ROLES:
            async def run(trip, revision, goal, previous, role=role):
                return result(role, trip, revision)
            runners[role] = AsyncMock(side_effect=run)
        graph = build_graph(planner, runners, InMemorySaver(), autonomous=True)
        cfg = {'configurable': {'thread_id': 'selection-requirements'}}
        await graph.ainvoke({'constraints': TRIP.model_dump(mode='json')}, cfg)
        changed = await graph.ainvoke({'messages': [HumanMessage(content='Замени отель на Mirror')]}, cfg)
        self.assertEqual(changed['constraints']['hotel'], 'Mirror')
        self.assertTrue(all('Mirror' in o['stay']['name'] for o in changed['options']))
        self.assertEqual(runners['transport'].await_count, 1)

class PlannerContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_planner_extracts_in_one_call_and_history_stays_intact(self):
        from unittest.mock import Mock
        from travel_agent.agents.supervisor.agent import llm_planner
        from travel_agent.schemas import RepairPlan
        answers = {
            TurnPlan: TurnPlan(action='plan', patch=TripDelta(start=TRIP.start, end=TRIP.end, purpose='Отдых у моря'), tasks=[task(r) for r in ROLES]),
            TripDelta: TripDelta(start=TRIP.start, end=TRIP.end, purpose='Отдых у моря'),
            RepairPlan: RepairPlan(tasks=[]),
        }
        clients = {schema: Mock(ainvoke=AsyncMock(return_value=value)) for schema, value in answers.items()}
        model = Mock()
        model.with_structured_output.side_effect = lambda schema, **kwargs: clients[schema]
        previous = AIMessage(content='Старый подробный план ' * 1000)
        state = {'constraints': TRIP.model_dump(mode='json'), 'messages': [previous, HumanMessage(content='12–16 ноября 2026, хороший отель и отдых у моря')]}
        decision = await llm_planner(model, 'Offline prompt')(state)
        self.assertEqual(decision.patch.start, TRIP.start)
        self.assertEqual(decision.patch.end, TRIP.end)
        self.assertIsNone(decision.patch.min_hotel_stars)
        self.assertEqual(len(decision.tasks), 3)
        clients[TripDelta].ainvoke.assert_not_awaited()
        clients[TurnPlan].ainvoke.assert_awaited_once()
        self.assertEqual(state['messages'][0].content, previous.content)
        sent = clients[TurnPlan].ainvoke.await_args.args[0]
        self.assertLessEqual(len(next(m.content for m in sent if isinstance(m, AIMessage))), 500)

    async def test_search_starts_without_a_mandatory_purpose_question(self):
        runners = {}
        for role in ROLES:
            async def run(trip, revision, goal, previous, role=role):
                return result(role, trip, revision)
            runners[role] = AsyncMock(side_effect=run)
        graph = build_graph(AsyncMock(side_effect=[TurnPlan(action='plan', reply='Начинаю поиск'), TurnPlan(action='plan', patch=TripDelta(purpose='Море и прогулки'))]), runners, InMemorySaver(), autonomous=True)
        cfg = {'configurable': {'thread_id': 'purpose-first'}}
        first = await graph.ainvoke({'constraints': TRIP.model_copy(update={'purpose': None, 'interests': []}).model_dump(mode='json')}, cfg)
        self.assertNotIn('Какой отдых', first['answer'])
        self.assertEqual([r.await_count for r in runners.values()], [1, 1, 1])
        self.assertTrue(first['options'])
        self.assertIn(first['selected'], {o['id'] for o in first['options']})


class SessionReliabilityTests(unittest.IsolatedAsyncioTestCase):
    def graph(self, planner, runners=None):
        runners = runners or {role: AsyncMock(side_effect=lambda trip, revision, goal, previous, role=role: result(role, trip, revision)) for role in ROLES}
        return build_graph(planner, runners, InMemorySaver(), autonomous=True), runners

    async def test_destination_selection_clarifies_and_resumes_search_over_http(self):
        question = 'Из какого города поедете и на какие будущие даты перенести поездку?'
        scenario = TripScenario(id='krasnodar', title='Город и гастрономия', destination='Краснодар',
            purpose='Парки и рестораны', tradeoff='Без моря')
        async def decide(state):
            if not state.get('stage'):
                return TurnPlan(action='destinations', scenarios=[scenario], patch=TripDelta(
                    start='2026-03-10', end='2026-03-20', adults=4, budget=300000))
            if state.get('plan_review'):
                self.assertEqual(state['selected_scenario'], 'krasnodar')
                self.assertEqual(state['constraints']['destination'], 'Краснодар')
                self.assertEqual(set(state['plan_review']['unresolved_fields']), {'origin', 'future_dates'})
                self.assertIsNone(state['requested_choice'])
                return TurnPlan(action='clarify', reply=question)
            return TurnPlan(action='plan', patch=TripDelta(origin='Москва', start=TRIP.start, end=TRIP.end),
                tasks=[task(r) for r in ROLES])
        def run(role, trip, revision, goal, previous):
            row = result(role, trip, revision)
            for candidate in row.candidates:
                candidate.destination = trip.destination
                if role in ('transport', 'stays'):
                    candidate.adults = trip.adults
            return row
        runners = {role: AsyncMock(side_effect=lambda *args, role=role: run(role, *args)) for role in ROLES}
        planner = AsyncMock(side_effect=decide)
        graph, _ = self.graph(planner, runners)
        app = create_app(graph, tokens=('alice',))
        async with app.router.lifespan_context(app), httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test', headers={'Authorization': 'Bearer alice'}) as client:
            ident = (await client.post('/trips')).json()['trip_id']
            first = (await client.post(f'/trips/{ident}/messages', json={'message': 'Предложи направления', 'revision': 0})).json()
            chosen = await client.post(f'/trips/{ident}/select/krasnodar', params={'revision': first['revision']})
            self.assertEqual(chosen.status_code, 200)
            selected = chosen.json()
            self.assertEqual(selected['status'], 'needs_input')
            self.assertEqual(selected['answer'], question)
            self.assertEqual(selected['selected_scenario'], 'krasnodar')
            self.assertEqual(selected['constraints']['adults'], 4)
            self.assertEqual(selected['constraints']['budget'], '300000')
            self.assertEqual(selected['choices'], [])
            for runner in runners.values():
                runner.assert_not_awaited()
            restored = (await client.get(f'/trips/{ident}')).json()
            self.assertEqual(restored['constraints'], selected['constraints'])
            response = await client.post(f'/trips/{ident}/messages', json={'message': 'Из Москвы, 12–16 ноября 2026', 'revision': selected['revision']})
            self.assertEqual(response.status_code, 200)
            ready = response.json()
            self.assertEqual(ready['status'], 'ready')
            self.assertTrue(ready['options'])
            self.assertEqual(ready['constraints']['destination'], 'Краснодар')
            for runner in runners.values():
                runner.assert_awaited_once()
                self.assertEqual(runner.await_args.args[0].adults, 4)
                self.assertEqual(runner.await_args.args[0].budget, Decimal(300000))

    async def test_complete_destination_choice_starts_search_without_another_planner_call(self):
        scenario = TripScenario(id='sochi', title='Море', destination='Сочи', purpose='Прогулки', tradeoff='Проверим тарифы')
        planner = AsyncMock(return_value=TurnPlan(action='destinations', scenarios=[scenario]))
        graph, runners = self.graph(planner)
        config = {'configurable': {'thread_id': 'complete-destination'}}
        await graph.ainvoke({'constraints': TRIP.model_dump(mode='json')}, config)
        selected = await graph.ainvoke({'requested_choice': 'sochi'}, config)
        self.assertEqual(selected['selected_scenario'], 'sochi')
        self.assertEqual(selected['status'], 'ready')
        self.assertTrue(selected['options'])
        planner.assert_awaited_once()
        for runner in runners.values():
            runner.assert_awaited_once()

    async def test_selection_review_can_restore_known_fields_and_search_immediately(self):
        from unittest.mock import Mock
        from travel_agent.agents.supervisor.agent import llm_planner
        async def decide(messages):
            context = json.loads(messages[1].content)
            self.assertEqual(context['plan_review']['unresolved_fields'], ['origin'])
            self.assertEqual(context['selected_scenario'], 'sochi')
            self.assertEqual(context['constraints']['destination'], 'Сочи')
            self.assertIn('Из Москвы', [m.content for m in messages])
            return TurnPlan(action='plan', patch=TripDelta(origin='Москва'))
        structured = Mock(ainvoke=AsyncMock(side_effect=decide))
        model = Mock(with_structured_output=Mock(return_value=structured))
        graph, runners = self.graph(llm_planner(model, 'Offline planner'))
        scenario = TripScenario(id='sochi', title='Море', destination='Сочи', purpose='Прогулки', tradeoff='Проверим тарифы')
        trip = TRIP.model_copy(update={'origin': None})
        state = await graph.ainvoke({'constraints': trip.model_dump(mode='json'), 'stage': 'scenarios',
            'scenarios': [scenario.model_dump(mode='json')], 'requested_choice': 'sochi',
            'messages': [HumanMessage(content='Из Москвы'), HumanMessage(content='/select sochi')]},
            {'configurable': {'thread_id': 'restore-origin'}})
        self.assertEqual(state['status'], 'ready')
        self.assertTrue(state['options'])
        structured.ainvoke.assert_awaited_once()
        for runner in runners.values():
            runner.assert_awaited_once()

    async def test_failed_clarification_preserves_choice_and_requests_missing_data(self):
        for failure in (TimeoutError(), TurnPlan(action='plan'), TurnPlan(action='select', option_id='sochi'), TurnPlan(action='unsupported')):
            with self.subTest(failure=repr(failure)):
                planner = AsyncMock(side_effect=[failure] if isinstance(failure, Exception) else None, return_value=failure)
                graph, runners = self.graph(planner)
                scenario = TripScenario(id='sochi', title='Море', destination='Сочи', purpose='Прогулки', tradeoff='Проверим тарифы')
                trip = TRIP.model_copy(update={'origin': None})
                state = await graph.ainvoke({'constraints': trip.model_dump(mode='json'), 'stage': 'scenarios',
                    'scenarios': [scenario.model_dump(mode='json')], 'requested_choice': 'sochi'},
                    {'configurable': {'thread_id': 'clarification-failure'}})
                self.assertEqual(state['status'], 'needs_input')
                self.assertIn('город отправления', state['answer'])
                self.assertEqual(state['selected_scenario'], 'sochi')
                self.assertEqual(state['constraints']['destination'], 'Сочи')
                self.assertIsNone(state['requested_choice'])
                planner.assert_awaited_once()
                for runner in runners.values():
                    runner.assert_not_awaited()

    async def test_month_without_duration_clarifies_before_any_search(self):
        planner = AsyncMock(side_effect=[
            TurnPlan(action='clarify', patch=TripDelta(destination='Сочи', travel_month='2026-12', adults=2, purpose='Отдых'), reply='Из какого города удобно выехать и на сколько ночей?'),
            TurnPlan(action='clarify', patch=TripDelta(origin='Санкт-Петербург'), reply='Какую длительность отдыха рассматриваете?'),
        ])
        graph, runners = self.graph(planner)
        config = {'configurable': {'thread_id': 'unknown-duration'}}
        first = await graph.ainvoke({'messages': [HumanMessage(content='Хочу отдохнуть в декабре вдвоём')]}, config)
        self.assertEqual(first['answer'], 'Из какого города удобно выехать и на сколько ночей?')
        second = await graph.ainvoke({'messages': [HumanMessage(content='Санкт-Петербург')]}, config)
        self.assertEqual(second['status'], 'needs_input')
        self.assertIn('длительность', second['answer'])
        self.assertIsNone(second['constraints']['start'])
        self.assertIsNone(second['constraints']['end'])
        self.assertEqual(second['constraints']['purpose'], 'Отдых')
        for runner in runners.values():
            runner.assert_not_awaited()

    async def test_month_with_duration_keeps_flexible_constraints_after_composition(self):
        planner = AsyncMock(return_value=TurnPlan(action='plan', tasks=[task(r) for r in ROLES]))
        runners = {role: AsyncMock(return_value=result(role, TRIP, 1)) for role in ROLES}
        graph, _ = self.graph(planner, runners)
        trip = TRIP.model_copy(update={'start': None, 'end': None, 'travel_month': '2026-11', 'nights': 4})
        state = await graph.ainvoke({'constraints': trip.model_dump(mode='json')}, {'configurable': {'thread_id': 'flexible-month'}})
        self.assertTrue(state['options'])
        self.assertIsNone(state['constraints']['start'])
        self.assertIsNone(state['constraints']['end'])
        self.assertEqual(state['constraints']['travel_month'], '2026-11')
        booking = simulate_purchase(state, BookingRequest(option_id=state['selected'], revision=state['revision'],
            confirm=True, idempotency_key='month-simulation'))
        self.assertTrue(booking['simulated'])
        self.assertIsNone(state['constraints']['start'])

    async def test_program_repair_keeps_all_package_alternatives(self):
        attempts = 0
        async def program(trip, revision, goal, previous):
            nonlocal attempts
            attempts += 1
            row = result('experience', trip, revision)
            if attempts == 1:
                row.days = []
            return row
        runners = {r: AsyncMock(side_effect=lambda trip, revision, goal, previous, role=r: result(role, trip, revision)) for r in ROLES}
        runners['experience'].side_effect = program
        graph, _ = self.graph(AsyncMock(side_effect=[TurnPlan(action='plan'), TurnPlan(action='plan', tasks=[task('experience')])]), runners)
        state = await graph.ainvoke({'constraints': TRIP.model_dump(mode='json')}, {'configurable': {'thread_id': 'keep-alternatives'}})
        self.assertEqual(len(state['options']), 5)
        self.assertGreater(len({o['stay']['id'] for o in state['options']}), 1)
        self.assertTrue(all(any(d['candidates'] for d in o['days']) for o in state['options']))
        self.assertEqual([runners[r].await_count for r in ROLES], [1, 1, 2])

    async def test_hotel_repair_covers_both_transport_arrival_windows(self):
        transport = result('transport', TRIP, 1)
        rail = transport.candidates[0].model_copy(update={'id': 'rail:fixture', 'transport_mode': 'rail', 'destination': 'Сочи',
            'arrival_at': transport.candidates[0].arrival_at + timedelta(days=1)})
        transport.candidates.append(rail)
        stays = result('stays', TRIP, 1)
        rail_hotel = stays.candidates[0].model_copy(update={'id': 'hotel:rail-date', 'start': TRIP.start + timedelta(days=1)})
        rounds = 0
        async def lodging(trip, revision, goal, previous):
            nonlocal rounds
            rounds += 1
            if rounds == 1:
                return SpecialistResult(role='stays', revision=revision, status='ok', candidates=[rail_hotel])
            context = json.loads(goal.split('\n', 1)[1])
            self.assertEqual({p['check_in'] for p in context['transport_stays']}, {str(TRIP.start), str(TRIP.start + timedelta(days=1))})
            self.assertEqual(trip.stay_start, TRIP.start)
            return stays.model_copy(update={'candidates': [*stays.candidates, rail_hotel]})
        runners = {'transport': AsyncMock(return_value=transport), 'stays': AsyncMock(side_effect=lodging),
                   'experience': AsyncMock(return_value=result('experience', TRIP, 1))}
        graph, _ = self.graph(AsyncMock(side_effect=[TurnPlan(action='plan'), TurnPlan(action='plan')]), runners)
        state = await graph.ainvoke({'constraints': TRIP.model_dump(mode='json')}, {'configurable': {'thread_id': 'arrival-windows'}})
        self.assertEqual({o['transport']['transport_mode'] for o in state['options']}, {'avia', 'rail'})
        self.assertEqual(rounds, 2)
        self.assertEqual(state['feedback'], [])

    async def test_transport_cards_are_selectable_without_a_complete_package(self):
        planner = AsyncMock(return_value=TurnPlan(action='plan', focus='transport', tasks=[task('transport')]))
        graph, runners = self.graph(planner)
        config = {'configurable': {'thread_id': 'transport-cards'}}
        state = await graph.ainvoke({'constraints': TRIP.model_dump(mode='json')}, config)
        self.assertTrue(state['cards'])
        self.assertTrue(all(c['selectable'] for c in state['cards']))
        ident = state['cards'][0]['id']
        selected = await graph.ainvoke({'requested_choice': ident}, config)
        self.assertEqual(selected['selected_transport'], ident)
        self.assertEqual(selected['constraints']['check_in'], str(TRIP.start))
        runners['stays'].assert_not_awaited()
        runners['experience'].assert_not_awaited()

    def test_same_hotel_still_offers_distinct_flights(self):
        rows = {role: result(role, TRIP, 1).model_dump(mode='json') for role in ROLES}
        rows['stays']['candidates'] = rows['stays']['candidates'][:1]
        options, _ = compose_packages(TRIP, rows, 1)
        self.assertGreater(len({o.transport.id for o in options}), 1)
        self.assertEqual(len({o.stay.id for o in options}), 1)


class ScopeAndLatencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_tour_replaces_cached_transport_without_researching_compatible_parts(self):
        graph, runners = PlanningTests().graph([TurnPlan(action='plan', focus='trip')])
        saved = {role: result(role, TRIP, 1).model_dump(mode='json') for role in ROLES}
        cached = saved['transport']['candidates'][0]
        cached.update(origin='MOW', adults=1, arrival_at=None)
        cached['source']['evidence'] = 'cached'
        saved['transport']['candidates'] = [cached]
        state = await graph.ainvoke({'constraints': TRIP.model_dump(mode='json'), 'results': saved,
            'focus': 'stays', 'messages': [HumanMessage(content='Собери мне полный тур по наилучшим условиям и объясни почему стоит выбрать его')]},
            {'configurable': {'thread_id': 'full-tour-from-cached'}})
        self.assertIsNone(state['focus'])
        self.assertEqual(state['status'], 'ready')
        self.assertGreater(len(state['options']), 1)
        self.assertTrue(all(o['transport']['source']['evidence'] == 'live' and o['stay'] and any(d['candidates'] for d in o['days']) for o in state['options']))
        self.assertEqual([runners[r].await_count for r in ROLES], [1, 0, 0])
        self.assertEqual(state['search_round'], 0)
        self.assertEqual(state['results']['stays'], saved['stays'])
        self.assertEqual(state['results']['experience'], saved['experience'])

    async def test_unavailable_transport_does_not_present_hotels_as_finished_tours(self):
        runners = {role: AsyncMock(side_effect=lambda trip, revision, goal, previous, role=role: result(role, trip, revision)) for role in ROLES}
        async def cached_only(trip, revision, goal, previous):
            row = result('transport', trip, revision)
            for candidate in row.candidates:
                candidate.source.evidence = 'cached'
                candidate.origin, candidate.adults, candidate.arrival_at = 'MOW', 1, None
            return row
        runners['transport'].side_effect = cached_only
        graph, _ = PlanningTests().graph([TurnPlan(action='plan'), TurnPlan(action='plan')], runners)
        state = await graph.ainvoke({'constraints': TRIP.model_dump(mode='json')}, {'configurable': {'thread_id': 'no-fake-tour'}})
        self.assertEqual(state['options'], [])
        self.assertEqual(state['status'], 'partial')
        self.assertIn('Тур пока не собран', state['answer'])
        self.assertIn('проезд туда-обратно', state['answer'])
        self.assertIn('отели и места сохранены', state['answer'])
        self.assertNotIn('Выберите вариант', state['answer'])
        self.assertEqual([runners[r].await_count for r in ROLES], [2, 1, 1])

    def test_every_tour_explains_price_travel_and_hotel_tradeoffs(self):
        from travel_agent.agents.supervisor.response import render_options
        rows = {role: result(role, TRIP, 1).model_dump(mode='json') for role in ROLES}
        options, _ = compose_packages(TRIP, rows, 1)
        first, second = [o.model_dump(mode='json') for o in options[:2]]
        first['budget']['known_subtotal'], second['budget']['known_subtotal'] = '70000', '90000'
        first['transport']['duration_minutes'], second['transport']['duration_minutes'] = 180, 120
        first['stay']['rating'], second['stay']['rating'] = '8', '9'
        state = {'constraints': TRIP.model_dump(mode='json'), 'options': [second, first], 'selected': second['id']}
        answer = render_options(state)
        self.assertEqual(answer.count('**Плюсы:**'), 2)
        self.assertEqual(answer.count('**Минусы:**'), 2)
        self.assertIn('на 20 000 ₽ дороже', answer)
        self.assertIn('на 60 мин дольше', answer)
        self.assertIn('оценка жилья 9/10', answer)
        self.assertIn('По цене рекомендую вариант 2', answer)
        self.assertIn('платные активности в указанную сумму не входят', answer)
        self.assertEqual(state['options'][0]['budget']['known_subtotal'], '90000')
        state['constraints']['baggage'] = 'required'
        first['transport']['baggage_included'], second['transport']['baggage_included'] = None, True
        self.assertIn('С требуемым багажом рекомендую вариант 1', render_options(state))

    async def test_single_task_does_not_change_planner_validation_to_hotel_only(self):
        from unittest.mock import Mock
        from travel_agent.agents.supervisor.agent import llm_planner
        structured = Mock(ainvoke=AsyncMock(side_effect=[
            TurnPlan(action='plan', tasks=[task('stays')]),
            TurnPlan(action='clarify', reply='Из какого города поедете?')]))
        model = Mock(with_structured_output=Mock(return_value=structured))
        decision = await llm_planner(model, 'Offline planner')({'constraints': TRIP.model_copy(update={'origin': None}).model_dump(mode='json')})
        self.assertEqual(decision.action, 'clarify')
        self.assertEqual(structured.ainvoke.await_count, 2)
        review = json.loads(structured.ainvoke.await_args.args[0][2].content)
        self.assertIn('origin', review['plan_review']['unresolved_fields'])

    async def test_hotel_only_http_never_requests_departure_or_runs_other_roles(self):
        from unittest.mock import Mock
        from travel_agent.agents.supervisor.agent import llm_planner
        structured = Mock(ainvoke=AsyncMock(return_value=TurnPlan(action='plan', focus='stays',
            patch=TripDelta(destination='Сочи', start=TRIP.start, end=TRIP.end, adults=2, option_limit=3),
            tasks=[task('stays')])))
        model = Mock(with_structured_output=Mock(return_value=structured))
        runners = {role: AsyncMock(side_effect=lambda trip, revision, goal, previous, role=role: result(role, trip, revision)) for role in ROLES}
        graph = build_graph(llm_planner(model, 'Offline planner'), runners, InMemorySaver(), autonomous=True)
        app = create_app(graph, tokens=('alice',))
        async with app.router.lifespan_context(app), httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test', headers={'Authorization': 'Bearer alice'}) as client:
            ident = (await client.post('/trips')).json()['trip_id']
            response = await client.post(f'/trips/{ident}/messages', json={'message': 'Найди три отеля, сравни отмену и расположение', 'revision': 0})
            self.assertEqual(response.status_code, 200)
            state = response.json()
            self.assertEqual(state['focus'], 'stays')
            self.assertEqual(state['stage'], 'stays')
            self.assertTrue(state['cards'])
            self.assertEqual(state['options'], [])
            self.assertNotIn('Из какого города', state['answer'])
        structured.ainvoke.assert_awaited_once()
        runners['stays'].assert_awaited_once()
        runners['transport'].assert_not_awaited()
        runners['experience'].assert_not_awaited()

    async def test_component_scope_survives_clarification_and_can_expand_explicitly(self):
        decisions = [TurnPlan(action='clarify', focus='stays', patch=TripDelta(destination='Сочи', adults=2), reply='На какие даты искать проживание?'),
            TurnPlan(action='plan', patch=TripDelta(start=TRIP.start, end=TRIP.end), tasks=[task('stays')]),
            TurnPlan(action='plan', focus='trip', patch=TripDelta(origin='Москва'), tasks=[task(r) for r in ROLES])]
        graph, runners = PlanningTests().graph(decisions)
        config = {'configurable': {'thread_id': 'component-clarification'}}
        first = await graph.ainvoke({'messages': [HumanMessage(content='Нужны отели')]}, config)
        self.assertNotIn('города поедете', first['answer'])
        self.assertEqual(first['focus'], 'stays')
        for run in runners.values():
            run.assert_not_awaited()
        hotels = await graph.ainvoke({'messages': [HumanMessage(content='12–16 ноября')]}, config)
        self.assertTrue(hotels['cards'])
        runners['transport'].assert_not_awaited()
        runners['experience'].assert_not_awaited()
        full = await graph.ainvoke({'messages': [HumanMessage(content='Добавь билеты из Москвы и программу')]}, config)
        self.assertIsNone(full['focus'])
        self.assertTrue(full['options'])

    async def test_explicit_component_scope_does_not_expand_missing_components(self):
        graph, runners = PlanningTests().graph([TurnPlan(action='plan', focus='stays', tasks=[task('stays')])])
        state = await graph.ainvoke({'constraints': TRIP.model_copy(update={'origin': None}).model_dump(mode='json')}, {'configurable': {'thread_id': 'inferred-scope'}})
        self.assertEqual(state['focus'], 'stays')
        self.assertTrue(state['cards'])
        runners['stays'].assert_awaited_once()
        runners['transport'].assert_not_awaited()
        runners['experience'].assert_not_awaited()

    async def test_explicit_component_scope_overrides_existing_package(self):
        graph, runners = PlanningTests().graph([TurnPlan(action='plan', tasks=[task(r) for r in ROLES]),
            TurnPlan(action='plan', focus='stays', tasks=[task('stays', ['transport'])])])
        config = {'configurable': {'thread_id': 'narrow-existing'}}
        await graph.ainvoke({'constraints': TRIP.model_dump(mode='json')}, config)
        narrowed = await graph.ainvoke({'messages': [HumanMessage(content='Теперь покажи только отели')]}, config)
        self.assertEqual(narrowed['focus'], 'stays')
        self.assertEqual(narrowed['options'], [])
        self.assertTrue(narrowed['cards'])
        self.assertEqual([runners[r].await_count for r in ROLES], [1, 2, 1])

    async def test_concise_explanation_is_one_llm_call_and_preserves_trip(self):
        from unittest.mock import Mock
        from travel_agent.agents.supervisor.agent import llm_planner
        reply = 'Сравнение по сохранённым ценам. ' * 20
        with self.assertRaises(ValidationError):
            TurnPlan(action='answer', reply=reply * 4)
        structured = Mock(ainvoke=AsyncMock(return_value=TurnPlan(action='answer', reply=reply)))
        model = Mock(with_structured_output=Mock(return_value=structured))
        presenter = AsyncMock()
        graph, runners = PlanningTests().graph([TurnPlan(action='plan', tasks=[task(r) for r in ROLES])])
        config = {'configurable': {'thread_id': 'explain-existing'}}
        first = await graph.ainvoke({'constraints': TRIP.model_dump(mode='json')}, config)
        graph = build_graph(llm_planner(model, 'Explain verified options'), runners, graph.checkpointer, present=presenter, autonomous=True)
        answered = await graph.ainvoke({'messages': [HumanMessage(content='Почему первый, а не второй?')]}, config)
        self.assertEqual(answered['answer'], reply)
        for field in ('revision', 'options', 'selected', 'constraints', 'results'):
            self.assertEqual(answered[field], first[field])
        self.assertEqual([runners[r].await_count for r in ROLES], [1, 1, 1])
        structured.ainvoke.assert_awaited_once()
        presenter.assert_not_awaited()
        context = json.loads(structured.ainvoke.await_args.args[0][1].content)
        self.assertIn('coordinates', context['options'][0]['stay'])
        self.assertIn('departure_at', context['options'][0]['transport'])

    async def test_concurrent_duplicate_mcp_queries_make_one_network_call(self):
        from travel_agent.tools import build_tools
        from test_travel_agent import FIXTURES
        async def source(*args):
            await asyncio.sleep(0.01)
            return {'status': 'ok', 'data': FIXTURES['search_hotels']}
        async with httpx.AsyncClient() as client:
            tools = {tool.name: tool for tool in build_tools('stays', TRIP, 1, client, {}, {}, [], {'tools': 0}, autonomous=True)}
            with patch('travel_agent.tools.runtime_call', side_effect=source) as network:
                first, second = await asyncio.gather(tools['search_hotels'].ainvoke({}), tools['search_hotels'].ainvoke({}))
                self.assertEqual(first, second)
                self.assertTrue(first['candidates'])
                network.assert_awaited_once()

    async def test_concurrent_geocoding_shares_one_request(self):
        from travel_agent.agents.experience.tools import build_tools
        async def source(*args):
            await asyncio.sleep(0.01)
            return {'locations': [{'latitude': 55.79, 'longitude': 49.12}]}
        rest = AsyncMock(side_effect=source)
        async with httpx.AsyncClient() as client:
            tools = {tool.name: tool for tool in build_tools(TRIP.model_copy(update={'destination': 'Казань'}), client, {}, {}, AsyncMock(), rest, autonomous=True)}
            await asyncio.gather(*(tools['geocode_destination'].ainvoke({}) for _ in range(3)))
        rest.assert_awaited_once()

    async def test_mcp_timeout_is_not_automatically_retried(self):
        from integrations.mcp.client import runtime_call
        with patch('integrations.mcp.client._runtime_attempt', new=AsyncMock(return_value={'status': 'timeout'})) as source:
            response = await runtime_call('stays', 'tutu', 'search_hotels', {}, {})
        source.assert_awaited_once()
        self.assertEqual(response, {'status': 'timeout', 'attempts': 1})


    async def test_hotel_checkin_dates_work_without_departure_dates_or_origin(self):
        graph, runners = PlanningTests().graph([TurnPlan(action='plan', focus='stays',
            patch=TripDelta(destination='Сочи', adults=2, check_in=TRIP.start, check_out=TRIP.end), tasks=[task('stays')])])
        state = await graph.ainvoke({'messages': [HumanMessage(content='Заселение 12 ноября, выезд 16 ноября, двое')]}, {'configurable': {'thread_id': 'hotel-local-dates'}})
        self.assertTrue(state['cards'])
        self.assertEqual(state['constraints']['start'], str(TRIP.start))
        self.assertEqual(state['constraints']['end'], str(TRIP.end))
        runners['transport'].assert_not_awaited()
        runners['experience'].assert_not_awaited()

    async def test_explanation_does_not_upgrade_partial_search_or_mutate_constraints(self):
        graph, runners = PlanningTests().graph([TurnPlan(action='answer', reply='Ни у одного варианта не проверено время местных переездов.', patch=TripDelta(budget=1))])
        config = {'configurable': {'thread_id': 'partial-explanation'}}
        state = await graph.ainvoke({'constraints': TRIP.model_dump(mode='json'), 'revision': 4, 'status': 'partial', 'messages': [HumanMessage(content='Что известно?')]}, config)
        self.assertEqual(state['status'], 'partial')
        self.assertEqual(state['revision'], 4)
        self.assertEqual(state['constraints'], TRIP.model_dump(mode='json'))
        for run in runners.values():
            run.assert_not_awaited()


    async def test_standalone_hotel_dates_do_not_follow_an_old_overnight_flight(self):
        graph, runners = PlanningTests().graph([TurnPlan(action='plan', focus='stays', tasks=[task('stays')])])
        config = {'configurable': {'thread_id': 'old-overnight-flight'}}
        journey = result('transport', TRIP, 1)
        journey.candidates[0].arrival_at += timedelta(days=1)
        observed = []
        async def hotels(trip, revision, goal, previous):
            observed.append(trip.stay_start)
            context = json.loads(goal.split('\n', 1)[1])
            self.assertEqual(context['transport_stays'], [])
            self.assertIsNone(context['current_transport'])
            return result('stays', trip, revision)
        runners['stays'].side_effect = hotels
        state = await graph.ainvoke({'constraints': TRIP.model_dump(mode='json'),
            'results': {'transport': journey.model_dump(mode='json')},
            'selected_transport': journey.candidates[0].id}, config)
        self.assertEqual(observed, [TRIP.start])
        self.assertTrue(state['cards'])
        runners['transport'].assert_not_awaited()


class SupervisorQuestionTests(unittest.IsolatedAsyncioTestCase):
    async def test_supervisor_chooses_question_without_field_order_or_overwriting(self):
        question = 'Что важнее для романтичного отдыха: тишина у моря или рестораны в центре?'
        graph, runners = PlanningTests().graph([TurnPlan(action='clarify', reply=question,
            patch=TripDelta(origin='Санкт-Петербург', destination='Владивосток', adults=2, budget=350000))])
        state = await graph.ainvoke({'messages': [HumanMessage(content='Из Питера во Владивосток вдвоём, бюджет 350 тысяч')]}, {'configurable': {'thread_id': 'natural-question'}})
        self.assertEqual(state['answer'], question)
        self.assertEqual(state['constraints']['origin'], 'Санкт-Петербург')
        self.assertEqual(state['constraints']['destination'], 'Владивосток')
        self.assertEqual(state['constraints']['budget'], '350000')
        self.assertEqual(state['status'], 'needs_input')
        for runner in runners.values():
            runner.assert_not_awaited()

    async def test_lost_request_fields_are_reviewed_by_supervisor_before_search(self):
        from unittest.mock import Mock
        from travel_agent.agents.supervisor.agent import llm_planner
        request = 'Мы с девушкой из Питера во Владивосток 12–17 ноября 2026, 350 тысяч на двоих, отель, море и горы, программа по дням'
        complete = TripDelta(origin='Санкт-Петербург', destination='Владивосток', start='2026-11-12', end='2026-11-17', adults=2, budget=350000, interests=['море', 'горы'])
        outputs = [TurnPlan(action='plan', tasks=[task(r) for r in ROLES]), TurnPlan(action='plan', focus='trip', patch=complete, tasks=[task(r) for r in ROLES])]
        async def decide(messages):
            self.assertEqual(messages[-1].content, request)
            if len(outputs) == 1:
                review = json.loads(messages[2].content)['plan_review']
                self.assertIn('origin', review['unresolved_fields'])
                self.assertIn('destination', review['unresolved_fields'])
            return outputs.pop(0)
        structured = Mock(ainvoke=AsyncMock(side_effect=decide))
        model = Mock(with_structured_output=Mock(return_value=structured))
        decision = await llm_planner(model, 'Offline planner')({'messages': [HumanMessage(content=request)]})
        self.assertEqual(decision.action, 'plan')
        self.assertEqual(decision.patch, complete)
        self.assertEqual(structured.ainvoke.await_count, 2)

    async def test_complete_request_does_not_need_review_or_city_question(self):
        from unittest.mock import Mock
        from travel_agent.agents.supervisor.agent import llm_planner
        complete = TurnPlan(action='plan', focus='trip', patch=TripDelta(origin='Санкт-Петербург', destination='Владивосток', start='2026-11-12', end='2026-11-17', adults=2, budget=350000), tasks=[task(r) for r in ROLES])
        structured = Mock(ainvoke=AsyncMock(return_value=complete))
        model = Mock(with_structured_output=Mock(return_value=structured))
        decision = await llm_planner(model, 'Offline planner')({'messages': [HumanMessage(content='Полный маршрут из Питера во Владивосток')]})
        self.assertEqual(decision, complete)
        structured.ainvoke.assert_awaited_once()
        self.assertEqual(decision.patch.origin, 'Санкт-Петербург')

    async def test_incomplete_plan_returns_to_supervisor_without_calling_sources(self):
        question = 'Куда хотите поехать и из какого города?'
        graph, runners = PlanningTests().graph([TurnPlan(action='plan'), TurnPlan(action='clarify', reply=question)])
        state = await graph.ainvoke({'messages': [HumanMessage(content='Полный запрос, потерянный в решении')]}, {'configurable': {'thread_id': 'bad-plan'}})
        self.assertEqual(state['status'], 'needs_input')
        self.assertEqual(state['answer'], question)
        for runner in runners.values():
            runner.assert_not_awaited()

    def test_clarification_requires_supervisor_text_and_wire_schema_requires_patch(self):
        with self.assertRaises(ValidationError):
            TurnPlan(action='clarify')
        required = TurnPlan.model_json_schema()['required']
        self.assertIn('patch', required)
        self.assertIn('reply', required)


class ParallelSearchRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_experience_starts_with_transport_while_stays_wait_for_arrival(self):
        experience_started, transport_done = asyncio.Event(), asyncio.Event()
        async def transport(trip, revision, goal, previous):
            await asyncio.wait_for(experience_started.wait(), 1)
            transport_done.set()
            return result('transport', trip, revision)
        async def experience(trip, revision, goal, previous):
            self.assertFalse(transport_done.is_set())
            experience_started.set()
            return result('experience', trip, revision)
        async def stays(trip, revision, goal, previous):
            self.assertTrue(transport_done.is_set())
            return result('stays', trip, revision)
        graph = build_graph(AsyncMock(return_value=TurnPlan(action='plan', tasks=[task('transport'), task('stays', ['transport']), task('experience')])),
            {'transport': transport, 'stays': stays, 'experience': experience}, InMemorySaver(), autonomous=True)
        state = await graph.ainvoke({'constraints': TRIP.model_dump(mode='json')}, {'configurable': {'thread_id': 'parallel-discovery'}})
        self.assertTrue(state['options'])
        self.assertTrue(any(day['candidates'] for day in state['options'][0]['days']))

    async def test_nine_tools_in_two_batches_can_finish_without_losing_second_batch(self):
        from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
        from travel_agent.agents.stays.agent import run
        from travel_agent.prompts import load_prompt
        from test_travel_agent import FIXTURES
        class ToolModel(FakeMessagesListChatModel):
            def bind_tools(self, tools, **kwargs):
                return self
        def searches(pages):
            return AIMessage(content='', tool_calls=[{'name': 'search_hotels', 'args': {'page': page}, 'id': f'page-{page}', 'type': 'tool_call'} for page in pages])
        model = ToolModel(responses=[searches(range(1, 7)), searches(range(7, 10)),
            AIMessage(content='', tool_calls=[{'name': 'SpecialistSelection', 'args': {'source_ids': []}, 'id': 'finish', 'type': 'tool_call'}])])
        async with httpx.AsyncClient() as client:
            with patch('travel_agent.tools.runtime_call', new=AsyncMock(return_value={'status': 'ok', 'data': FIXTURES['search_hotels']})) as source:
                row = await run(TRIP, 1, 'Offline batch regression', [], model=model, client=client, env={}, prompt=load_prompt('stays'), autonomous=True)
        self.assertEqual(source.await_count, 9)
        self.assertEqual(row.tool_calls, 9)
        self.assertTrue(row.candidates)
        self.assertNotIn('agent_limit', row.warnings)
        self.assertNotIn('finalization_failed', row.warnings)

    async def test_search_radius_matches_provider_contract_before_network(self):
        from travel_agent.tools import build_tools
        async with httpx.AsyncClient() as client:
            tools = {t.name: t for t in build_tools('experience', TRIP, 1, client, {'TWOGIS_API_KEY': 'offline-test'}, {}, [], {'tools': 0}, autonomous=True)}
            schema = tools['search_places'].args_schema.model_json_schema()
            self.assertEqual(schema['properties']['radius']['maximum'], 40000)
            with patch('travel_agent.tools.runtime_call', new=AsyncMock(return_value={'status': 'ok', 'data': {}})) as source:
                with self.assertRaises(ValidationError):
                    await tools['search_places'].ainvoke({'radius': 50000})
                source.assert_not_awaited()
                await tools['search_places'].ainvoke({'radius': 40000})
                self.assertEqual(source.await_args.args[3]['radius'], 40000)


class TurnDeadlineTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_returns_saved_options_and_stops_pending_work(self):
        cancelled = asyncio.Event()
        async def present(state):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        graph, runners = PlanningTests().graph([TurnPlan(action='plan', tasks=[task(r) for r in ROLES])], present=present)
        app = create_app(graph, tokens=('alice',))
        async with app.router.lifespan_context(app), httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test', headers={'Authorization': 'Bearer alice'}) as client:
            ident = (await client.post('/trips')).json()['trip_id']
            import hashlib
            config = {'configurable': {'thread_id': hashlib.sha256(b'alice').hexdigest() + ':' + ident}}
            await graph.aupdate_state(config, {'constraints': TRIP.model_dump(mode='json')})
            with patch('travel_agent.api.AUTONOMOUS_TURN_TIMEOUT_SECONDS', 0.5):
                response = await asyncio.wait_for(client.post(f'/trips/{ident}/messages', json={'message': 'Полная поездка', 'revision': 0}), 2)
            self.assertEqual(response.status_code, 200)
            partial = response.json()
            self.assertEqual(partial['status'], 'partial')
            self.assertTrue(partial['options'])
            self.assertIn('Туры под ключ', partial['answer'])
            self.assertNotIn('лимит', partial['answer'].lower())
            self.assertLess(len(partial['answer']), 3000)
            self.assertTrue(cancelled.is_set())
            restored = (await client.get(f'/trips/{ident}')).json()
            self.assertEqual(restored['options'], partial['options'])
            self.assertEqual(restored['answer'], partial['answer'])
            snapshot = await graph.aget_state(config)
            self.assertEqual(snapshot.next, ())
            self.assertEqual(len(snapshot.values['messages']), 2)
            self.assertEqual([runners[r].await_count for r in ROLES], [1, 1, 1])

    async def test_fourth_model_step_only_offers_structured_completion(self):
        from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
        from travel_agent.agents.stays.agent import run
        from travel_agent.prompts import load_prompt
        from test_travel_agent import FIXTURES
        bindings = []
        class ToolModel(FakeMessagesListChatModel):
            def bind_tools(self, tools, **kwargs):
                bindings.append([t.name for t in tools])
                return self
        model = ToolModel(responses=[*[AIMessage(content='', tool_calls=[{'name': 'search_hotels', 'args': {'page': page}, 'id': f'search-{page}', 'type': 'tool_call'}]) for page in range(1,4)],
            AIMessage(content='', tool_calls=[{'name': 'SpecialistSelection', 'args': {'source_ids': []}, 'id': 'done', 'type': 'tool_call'}])])
        async with httpx.AsyncClient() as client:
            with patch('travel_agent.tools.runtime_call', new=AsyncMock(return_value={'status': 'ok', 'data': FIXTURES['search_hotels']})) as source:
                row = await run(TRIP, 1, 'Offline completion test', [], model=model, client=client, env={}, prompt=load_prompt('stays'), autonomous=True)
        self.assertEqual(source.await_count, 3)
        self.assertIn('hotel_details', bindings[2])
        self.assertEqual(bindings[-1], ['SpecialistSelection'])
        self.assertNotIn('agent_limit', row.warnings)
        self.assertNotIn('finalization_failed', row.warnings)

    async def test_cancelled_network_call_is_not_logged_as_success(self):
        from travel_agent.tools import build_tools
        started = asyncio.Event()
        async def source(*args):
            started.set()
            await asyncio.Event().wait()
        async with httpx.AsyncClient() as client:
            tools = {t.name: t for t in build_tools('stays', TRIP, 1, client, {}, {}, [], {'tools':0}, autonomous=True)}
            with patch('travel_agent.tools.runtime_call', side_effect=source), patch('travel_agent.tools.logger.info') as logs:
                pending = asyncio.create_task(tools['search_hotels'].ainvoke({}))
                await asyncio.wait_for(started.wait(), 1)
                pending.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await pending
            self.assertEqual([call.args[5] for call in logs.call_args_list], ['cancelled'])
