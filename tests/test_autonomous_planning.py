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
from travel_agent.schemas import AgentTask, BookingRequest, ProposedDay, SpecialistResult, TripDelta, TurnPlan
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
        self.assertEqual(len(state['options']), 3)
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

    async def test_clarify_hotel_budget_dates_and_readonly_question(self):
        decisions = [TurnPlan(action='clarify', patch=TripDelta(origin='Москва', adults=2, purpose='Море'), reply='Когда поедете?'),
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
        self.assertIn('no_day_plan', [f['code'] for f in state['feedback']])
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
        self.assertIn('mountain_days_mismatch', [f.code for f in feedback])
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
    async def test_focused_extraction_is_authoritative_and_history_stays_intact(self):
        from unittest.mock import Mock
        from travel_agent.agents.supervisor.agent import llm_planner
        from travel_agent.schemas import RepairPlan
        answers = {
            TurnPlan: TurnPlan(action='plan', patch=TripDelta(start='2026-11-10', min_hotel_stars=4), tasks=[task(r) for r in ROLES]),
            TripDelta: TripDelta(start=TRIP.start, end=TRIP.end, purpose='Отдых у моря'),
            RepairPlan: RepairPlan(tasks=[]),
        }
        clients = {schema: Mock(ainvoke=AsyncMock(return_value=value)) for schema, value in answers.items()}
        model = Mock()
        model.with_structured_output.side_effect = lambda schema, **kwargs: clients[schema]
        previous = AIMessage(content='Старый подробный план ' * 1000)
        state = {'constraints': {}, 'messages': [previous, HumanMessage(content='12–16 ноября 2026, хороший отель и отдых у моря')]}
        decision = await llm_planner(model, 'Offline prompt')(state)
        self.assertEqual(decision.patch.start, TRIP.start)
        self.assertEqual(decision.patch.end, TRIP.end)
        self.assertIsNone(decision.patch.min_hotel_stars)
        self.assertEqual(len(decision.tasks), 3)
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
