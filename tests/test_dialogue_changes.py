import json
import os
import unittest
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from travel_agent.agents.supervisor.agent import llm_planner
from travel_agent.agents.supervisor.response import llm_presenter
from travel_agent.agents.transport.agent import run as run_transport
from travel_agent.api import create_app
from travel_agent.engine import compose_packages, search_dates, simulate_purchase
from travel_agent.graph import build_graph
from travel_agent.prompts import read_prompts
from travel_agent.schemas import BookingRequest, ProposedDay, RepairPlan, SpecialistResult, TripDelta, TurnPlan, UserResponse
from travel_agent.tools import build_tools, normalize
from test_autonomous_planning import ROLES, result, task
from test_travel_agent import FIXTURES, TRIP


class ToolModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def call(name, args):
    return AIMessage(content='', tool_calls=[{'name': name, 'args': args, 'id': name, 'type': 'tool_call'}])


def fares():
    data = deepcopy(FIXTURES['search_avia'])
    data['offers'] = data['offers'][:1]
    data['offers'][0]['variants'] = [
        {'variant_id': 'basic', 'price': {'amount': 10000, 'currency': 'RUB'},
         'conditions': {'fare_family': 'Базовый', 'baggage': {'kg': 0, 'pieces': 0}}},
        {'variant_id': 'with-baggage', 'price': {'amount': 14000, 'currency': 'RUB'},
         'conditions': {'fare_family': 'С багажом', 'baggage': {'kg': 20, 'pieces': 1}, 'refundable': True}},
    ]
    return data


class FareChangesTests(unittest.IsolatedAsyncioTestCase):
    async def test_specific_provider_filters_are_available_to_specialists(self):
        async with httpx.AsyncClient() as client:
            with patch('travel_agent.tools.runtime_call', new=AsyncMock(return_value={'status': 'ok', 'data': {'hotels': []}})) as network:
                tools = {t.name: t for t in build_tools('stays', TRIP, 1, client, {}, {}, [], {'tools': 0}, autonomous=True)}
                await tools['search_hotels'].ainvoke({'hotel_amenities': ['pets', 'pool'], 'breakfast_included': True, 'page': 4})
                self.assertEqual(network.await_args.args[3]['hotel_amenities'], ['pets', 'pool'])
                self.assertTrue(network.await_args.args[3]['breakfast_included'])
                self.assertEqual(network.await_args.args[3]['page'], 4)
            with patch('travel_agent.tools.runtime_call', new=AsyncMock(return_value={'status': 'ok', 'data': {'offers': []}})) as network:
                tools = {t.name: t for t in build_tools('transport', TRIP, 1, client, {}, {}, [], {'tools': 0}, autonomous=True)}
                await tools['search_flights'].ainvoke({'service_class': 'C', 'carriers': ['SU'], 'sort': 'duration_asc'})
                self.assertEqual(network.await_args.args[3]['service_class'], 'C')
                self.assertEqual(network.await_args.args[3]['carriers'], ['SU'])
                self.assertEqual(network.await_args.args[3]['sort'], 'duration_asc')

    def test_explicit_dates_take_priority_over_a_colloquial_day_count(self):
        trip = TRIP.model_copy(update={'start': date(2026, 12, 10), 'end': date(2026, 12, 20), 'duration_days': 10})
        self.assertEqual(search_dates(trip)[0], (date(2026, 12, 10), date(2026, 12, 20)))

    async def test_fare_conditions_prices_and_original_details_survive_followup(self):
        data = fares()
        variants = normalize('tutu', 'search_avia', data, TRIP, datetime.now(timezone.utc))
        chosen = next(c for c in variants if c.baggage_included)
        self.assertEqual(chosen.price.amount, 14000)
        self.assertEqual(chosen.conditions['baggage']['kg'], 20)
        self.assertTrue(chosen.conditions['refundable'])
        self.assertEqual(len({c.id for c in variants}), 2)
        model = ToolModel(responses=[call('search_flights', {}), call('transport_details', {'source_id': chosen.id}),
                                    call('SpecialistSelection', {'source_ids': [chosen.id]})])
        async def source(role, provider, method, args, env, owned):
            if method == 'search_avia':
                return {'status': 'ok', 'data': data}
            self.assertEqual(args['offer_id'], data['offers'][0]['offer_id'])
            self.assertEqual(args['details_ref'], data['offers'][0])
            self.assertIn(('avia', args['offer_id']), owned)
            return {'status': 'ok', 'data': {'offer': data['offers'][0]}}
        async with httpx.AsyncClient() as client:
            with patch('travel_agent.tools.runtime_call', new=AsyncMock(side_effect=source)) as network:
                row = await run_transport(TRIP.model_copy(update={'baggage': 'required'}), 2, 'Багаж не менее 20 кг', [],
                    model=model, client=client, env={}, prompt=read_prompts()['transport'], autonomous=True)
                self.assertEqual(network.await_count, 2)
                self.assertEqual(row.selected_ids, [chosen.id])
                self.assertNotIn('agent_limit', row.warnings)
                self.assertEqual(next(c for c in row.candidates if c.id == chosen.id).price.amount, 14000)
            followup = ToolModel(responses=[call('transport_details', {'source_id': chosen.id}),
                                           call('SpecialistSelection', {'source_ids': [chosen.id]})])
            with patch('travel_agent.tools.runtime_call', new=AsyncMock(side_effect=source)) as network:
                next_row = await run_transport(TRIP, 3, 'Уточни условия этого тарифа', row.candidates,
                    model=followup, client=client, env={}, prompt=read_prompts()['transport'], autonomous=True)
                network.assert_awaited_once()
                self.assertEqual(network.await_args.args[2], 'get_offer_details')
                self.assertEqual(next_row.selected_ids, [chosen.id])

    def test_a_required_baggage_fare_is_recommended_over_a_cheaper_basic_fare(self):
        rows = {r: result(r, TRIP, 1).model_dump(mode='json') for r in ROLES}
        variants = normalize('tutu', 'search_avia', fares(), TRIP, datetime.now(timezone.utc))
        rows['transport'].update(candidates=[c.model_dump(mode='json') for c in variants], selected_ids=[c.id for c in variants])
        options, feedback = compose_packages(TRIP.model_copy(update={'baggage': 'required'}), rows, 1)
        self.assertTrue(options)
        self.assertTrue(all(o.transport.baggage_included for o in options))
        self.assertTrue(all(o.transport.price.amount == Decimal('14000') for o in options))
        self.assertFalse(any(f.code == 'unverified_baggage' for f in feedback))

    def test_an_explicit_activity_on_arrival_day_is_not_silently_removed(self):
        rows = {r: result(r, TRIP, 1).model_dump(mode='json') for r in ROLES}
        place = rows['experience']['candidates'][1]
        rows['experience']['days'].append({'date': str(TRIP.start), 'source_ids': [place['id']], 'purpose': 'Прогулка после прилёта'})
        options, _ = compose_packages(TRIP, rows, 1)
        self.assertIn(place['id'], [c.id for c in options[0].days[0].candidates])


class DialogueChangesTests(unittest.IsolatedAsyncioTestCase):
    def graph(self, decisions, runners=None, present=None):
        if runners is None:
            runners = {}
            for role in ROLES:
                async def run(trip, revision, goal, previous, role=role):
                    return result(role, trip, revision)
                runners[role] = AsyncMock(side_effect=run)
        graph = build_graph(AsyncMock(side_effect=decisions), runners, InMemorySaver(), present=present, autonomous=True)
        return graph, runners

    async def test_empty_extraction_does_not_erase_complete_request(self):
        delta = TripDelta(origin='Москва', start=TRIP.start, end=TRIP.end, adults=2, budget=200000, purpose='Горнолыжный отдых')
        clients = {
            TurnPlan: Mock(ainvoke=AsyncMock(return_value=TurnPlan(action='plan', patch=delta, tasks=[task(r) for r in ROLES]))),
            TripDelta: Mock(ainvoke=AsyncMock(return_value=TripDelta())),
            RepairPlan: Mock(),
        }
        model = Mock()
        model.with_structured_output.side_effect = lambda schema, **kwargs: clients[schema]
        decision = await llm_planner(model, 'Offline prompt')({'messages': [HumanMessage(content='Готовый тур на двоих из Москвы 12–16 ноября до 200 тысяч')]})
        self.assertEqual(decision.patch, delta)

    async def test_a_short_followup_has_the_original_request_for_recovery(self):
        original = 'Я хочу поехать с другом на горнолыжный курорт с 10 по 20 декабря, до 200000 на двоих, подбери готовый тур'
        async def plan(messages):
            human = [m.content for m in messages if isinstance(m, HumanMessage)]
            self.assertIn(original, human)
            self.assertEqual(human[-1], 'активный')
            return TurnPlan(action='plan', patch=TripDelta(destination='Сочи', start='2026-12-10', end='2026-12-20', adults=2, budget=200000, purpose='Горнолыжная поездка'))
        model = Mock()
        model.with_structured_output.side_effect = lambda schema, **kwargs: {
            TurnPlan: Mock(ainvoke=plan),
            TripDelta: Mock(), RepairPlan: Mock(),
        }[schema]
        decision = await llm_planner(model, 'Offline prompt')({'messages': [HumanMessage(content=original), AIMessage(content='Какой отдых?'), HumanMessage(content='активный')]})
        graph, runners = self.graph([decision])
        state = await graph.ainvoke({'messages': [HumanMessage(content='активный')]}, {'configurable': {'thread_id': 'recover-input'}})
        self.assertEqual(state['constraints']['budget'], '200000')
        self.assertEqual(state['constraints']['adults'], 2)
        self.assertEqual(state['constraints']['start'], '2026-12-10')
        self.assertIn('города', state['answer'])
        self.assertNotIn('Какой отдых', state['answer'])
        self.assertEqual(sum(r.await_count for r in runners.values()), 0)

    async def test_complete_input_produces_a_selected_package_ready_for_simulation(self):
        graph, runners = self.graph([TurnPlan(action='plan', tasks=[task(r) for r in ROLES])])
        state = await graph.ainvoke({'constraints': TRIP.model_copy(update={'purpose': None}).model_dump(mode='json')}, {'configurable': {'thread_id': 'ready-package'}})
        self.assertEqual(state['status'], 'ready')
        selected = next(o for o in state['options'] if o['id'] == state['selected'])
        self.assertEqual(state['selected_transport'], selected['transport']['id'])
        self.assertEqual(state['selected_stay'], selected['stay']['id'])
        receipt = simulate_purchase(state, BookingRequest(option_id=state['selected'], revision=state['revision'], confirm=True, idempotency_key='ready-package'))
        self.assertTrue(receipt['simulated'])
        self.assertEqual([r.await_count for r in runners.values()], [1, 1, 1])

    async def test_replacing_a_hotel_keeps_a_complete_trip_and_the_selected_flight(self):
        graph, runners = self.graph([
            TurnPlan(action='plan', tasks=[task(r) for r in ROLES]),
            TurnPlan(action='plan', focus='trip', patch=TripDelta(hotel='Mirror'), tasks=[task('stays')]),
        ])
        config = {'configurable': {'thread_id': 'hotel-edit'}}
        original = await graph.ainvoke({'constraints': TRIP.model_dump(mode='json')}, config)
        changed = await graph.ainvoke({'messages': [HumanMessage(content='Замени отель на Mirror, билеты и программу оставь')]}, config)
        self.assertIsNone(changed['focus'])
        selected = next(o for o in changed['options'] if o['id'] == changed['selected'])
        self.assertEqual(selected['transport']['id'], original['selected_transport'])
        self.assertIn('Mirror', selected['stay']['name'])
        self.assertEqual(changed['results']['experience'], original['results']['experience'])
        self.assertEqual([r.await_count for r in runners.values()], [1, 2, 1])

    async def test_a_baggage_edit_keeps_hotel_and_program(self):
        graph, runners = self.graph([
            TurnPlan(action='plan', tasks=[task(r) for r in ROLES]),
            TurnPlan(action='plan', patch=TripDelta(baggage='required'), tasks=[task('transport')]),
        ])
        config = {'configurable': {'thread_id': 'baggage-edit'}}
        original = await graph.ainvoke({'constraints': TRIP.model_dump(mode='json')}, config)
        variants = normalize('tutu', 'search_avia', fares(), TRIP, datetime.now(timezone.utc))
        runners['transport'].side_effect = lambda trip, revision, goal, previous: SpecialistResult(role='transport', revision=revision, status='ok', candidates=variants,
            selected_ids=[next(c.id for c in variants if c.baggage_included)])
        changed = await graph.ainvoke({'messages': [HumanMessage(content='Хочу билеты с багажом')]}, config)
        selected = next(o for o in changed['options'] if o['id'] == changed['selected'])
        self.assertTrue(selected['transport']['baggage_included'])
        self.assertEqual(selected['transport']['conditions']['baggage']['kg'], 20)
        self.assertEqual(selected['stay']['id'], original['selected_stay'])
        self.assertEqual(changed['results']['experience'], original['results']['experience'])
        self.assertEqual([r.await_count for r in runners.values()], [2, 1, 1])
        self.assertIn('20 кг', changed['answer'])

    async def test_program_edit_keeps_unchanged_days_and_allows_repeated_resort_visits(self):
        graph, runners = self.graph([
            TurnPlan(action='plan', tasks=[task(r) for r in ROLES]),
            TurnPlan(action='plan', patch=TripDelta(interests=['прогулки', 'баня']), tasks=[task('experience')]),
        ])
        config = {'configurable': {'thread_id': 'day-edit'}}
        trip = TRIP.model_copy(update={'end': TRIP.start + timedelta(days=9)})
        for role in ('transport', 'stays'):
            async def run(trip, revision, goal, previous, role=role):
                row = result(role, TRIP, revision)
                for c in row.candidates:
                    c.end = trip.end
                    if role == 'transport':
                        c.return_departure_at += trip.end - TRIP.end
                return row
            runners[role].side_effect = run
        original = await graph.ainvoke({'constraints': trip.model_dump(mode='json')}, config)
        async def program(trip, revision, goal, previous):
            context = json.loads(goal.split('\n', 1)[1])
            self.assertIn('восьмой', context['user_request'])
            self.assertTrue(context['current_days'])
            self.assertTrue(previous)
            row = result('experience', trip, revision)
            row.candidates = [c for c in previous if c.role == 'experience']
            bath = row.candidates[0].model_copy(update={'id': 'bath', 'name': 'Баня'})
            row.candidates.append(bath)
            row.days += [ProposedDay(date=trip.start + timedelta(days=2), source_ids=[row.candidates[0].id]),
                         ProposedDay(date=trip.start + timedelta(days=7), source_ids=[bath.id])]
            return row
        runners['experience'].side_effect = program
        changed = await graph.ainvoke({'messages': [HumanMessage(content='Добавь баню на восьмой день поездки')]}, config)
        selected = next(o for o in changed['options'] if o['id'] == changed['selected'])
        day = next(d for d in selected['days'] if d['date'] == str(trip.start + timedelta(days=7)))
        self.assertEqual([c['name'] for c in day['candidates']], ['Баня'])
        self.assertEqual(selected['days'][1], original['options'][0]['days'][1])
        self.assertEqual([r.await_count for r in runners.values()], [1, 1, 2])
        self.assertNotIn('invalid_day_evidence', [f['code'] for f in changed['feedback']])

    async def test_comparison_and_complaint_are_answers_without_new_search_or_replanning(self):
        text = 'В администрацию отеля. Во время моего посещения сауна была холодной. Прошу проверить качество услуги. Письмо не отправлено.'
        presenter = AsyncMock(return_value=text)
        graph, runners = self.graph([
            TurnPlan(action='plan', tasks=[task(r) for r in ROLES]), TurnPlan(action='answer', reply='В первом варианте ниже известная сумма.'),
            TurnPlan(action='answer', reply=text),
        ], present=presenter)
        config = {'configurable': {'thread_id': 'helpful-answer'}}
        original = await graph.ainvoke({'constraints': TRIP.model_dump(mode='json')}, config)
        for question, expected in [('Какие плюсы у каждого варианта?', 'В первом варианте ниже известная сумма.'), ('Сауна была холодной, напиши жалобу администрации отеля', text)]:
            state = await graph.ainvoke({'messages': [HumanMessage(content=question)]}, config)
            self.assertEqual(state['answer'], expected)
            self.assertEqual(state['options'], original['options'])
            self.assertEqual(state['revision'], original['revision'])
            self.assertEqual(state['selected'], original['selected'])
        self.assertEqual([r.await_count for r in runners.values()], [1, 1, 1])
        presenter.assert_awaited_once()

    async def test_editing_a_saved_legacy_trip_reuses_its_approved_calendar(self):
        graph, runners = self.graph([TurnPlan(action='plan', tasks=[task('experience')])])
        config = {'configurable': {'thread_id': 'legacy-calendar'}}
        rows = {r: result(r, TRIP, 1).model_dump(mode='json') for r in ROLES}
        options, _ = compose_packages(TRIP, rows, 1)
        chosen = options[0]
        rows['experience'].pop('days')
        await graph.aupdate_state(config, {'constraints': TRIP.model_dump(mode='json'), 'results': rows,
            'options': [chosen.model_dump(mode='json')], 'selected': chosen.id, 'revision': 1, 'stage': 'review',
            'selected_transport': chosen.transport.id, 'selected_stay': chosen.stay.id})
        async def program(trip, revision, goal, previous):
            context = json.loads(goal.split('\n', 1)[1])
            self.assertEqual(context['current_days'][1]['source_ids'], [c.id for c in chosen.days[1].candidates])
            self.assertEqual(context['current_transport']['id'], chosen.transport.id)
            return result('experience', trip, revision)
        runners['experience'].side_effect = program
        state = await graph.ainvoke({'messages': [HumanMessage(content='Дополни мою программу')]}, config)
        self.assertTrue(state['options'])
        self.assertEqual([r.await_count for r in runners.values()], [0, 0, 1])


class HelpfulAnswerTests(unittest.IsolatedAsyncioTestCase):
    async def test_letter_uses_current_hotel_and_request_without_requiring_old_web_citations(self):
        rows = {r: result(r, TRIP, 1).model_dump(mode='json') for r in ROLES}
        options, _ = compose_packages(TRIP, rows, 1)
        chosen = options[0]
        chosen.transport.conditions = {'baggage': {'kg': 20, 'pieces': 1}}
        model = Mock()
        async def answer(messages):
            context = json.loads(messages[1].content)
            self.assertEqual(context['selected'], chosen.id)
            self.assertEqual(context['options'][0]['stay']['name'], chosen.stay.name)
            self.assertEqual(context['options'][0]['transport']['conditions']['baggage']['kg'], 20)
            self.assertEqual(context['research'], {})
            self.assertIn('сауна была холодной', messages[-1].content)
            return UserResponse(text='Здравствуйте, администрация ' + chosen.stay.name + '! Сауна была холодной. Прошу проверить качество услуги. Письмо не отправлено.')
        model.with_structured_output.return_value.ainvoke = answer
        state = {'autonomous': True, 'constraints': TRIP.model_dump(mode='json'), 'options': [chosen.model_dump(mode='json')],
                 'selected': chosen.id, 'decision': {'action': 'answer'},
                 'research': {'sources': [{'url': 'https://example.org/old', 'text': 'старый поиск', 'title': 'старый поиск'}]},
                 'messages': [HumanMessage(content='В отеле сауна была холодной. Напиши жалобу администрации')]}
        text = await llm_presenter(model, read_prompts()['response'])(state)
        self.assertIn(chosen.stay.name, text)
        self.assertIn('Сауна была холодной', text)
        self.assertNotIn('Не удалось', text)


@unittest.skipUnless(os.environ.get('TRAVEL_TEST_DATABASE_URL'), 'Separate PostgreSQL portal integration mode')
class PortalAnswerTests(unittest.TestCase):
    def test_a_real_portal_message_reaches_the_agent_instead_of_the_support_template(self):
        rows = {r: result(r, TRIP, 1).model_dump(mode='json') for r in ROLES}
        options, _ = compose_packages(TRIP, rows, 1)
        chosen = options[0]
        text = 'Здравствуйте, администрация ' + chosen.stay.name + '! Сауна была холодной. Прошу проверить качество услуги. Письмо не отправлено.'
        response_model = Mock()
        response_model.with_structured_output.return_value.ainvoke = AsyncMock(return_value=UserResponse(text=text))
        presenter = llm_presenter(response_model, read_prompts()['response'])
        planner = AsyncMock(return_value=TurnPlan(action='answer', reply='Подготовь письмо по жалобе пользователя'))
        runners = {role: AsyncMock() for role in ROLES}
        graph = build_graph(planner, runners, InMemorySaver(), present=presenter, autonomous=True)
        with patch('travel_agent.api.environment', return_value={}), TestClient(create_app(graph, portal_database_url=os.environ['TRAVEL_TEST_DATABASE_URL'])) as client:
            account = client.post('/api/auth/register', json={'name': 'Тест', 'email': str(uuid4()) + '@example.org', 'password': 'fixture-password-123'}).json()
            ident = client.post('/trips').json()['trip_id']
            config = {'configurable': {'thread_id': account['id'] + ':' + ident}}
            client.portal.call(graph.aupdate_state, config, {
                'autonomous': True, 'constraints': TRIP.model_dump(mode='json'), 'revision': 1,
                'options': [chosen.model_dump(mode='json')], 'selected': chosen.id, 'stage': 'review',
            })
            reply = client.post('/trips/' + ident + '/messages', json={'message': 'В отеле сауна была холодной. Напиши жалобу администрации', 'revision': 1})
            self.assertEqual(reply.status_code, 200, reply.text)
            self.assertEqual(reply.json()['answer'], text)
            self.assertEqual(reply.json()['selected'], chosen.id)
            planner.assert_awaited_once()
            response_model.with_structured_output.return_value.ainvoke.assert_awaited_once()
            self.assertEqual(sum(r.await_count for r in runners.values()), 0)
            client.request('DELETE', '/api/account', json={'confirmation': 'УДАЛИТЬ'})


class ContextBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_saved_fares_are_compact_and_bounded_without_losing_evidence(self):
        from travel_agent.schemas import Candidate
        from langchain_core.callbacks import AsyncCallbackHandler
        base = result('transport', TRIP, 1).candidates[0]
        previous = [base.model_copy(update={'id': f'avia:saved-{i}', 'provider_details': {'large': 'x' * 10000},
                    'url': 'https://example.org/' + 'a' * 6000}) for i in range(120)]
        seen = []
        class Capture(AsyncCallbackHandler):
            async def on_chat_model_start(self, serialized, messages, **kwargs):
                seen.extend(m for batch in messages for m in batch if isinstance(m, HumanMessage))
        model = ToolModel(responses=[call('SpecialistSelection', {'source_ids': [previous[0].id]})], callbacks=[Capture()])
        async with httpx.AsyncClient() as client:
            with patch('travel_agent.tools.runtime_call', new=AsyncMock()) as network:
                row = await run_transport(TRIP, 2, 'Сравни найденное', previous, model=model, client=client, env={},
                                          prompt=read_prompts()['transport'], autonomous=True)
        network.assert_not_awaited()
        self.assertEqual(len(row.candidates), 120)
        context = json.loads(seen[0].content)
        self.assertEqual(len(context['observations'][0]['result']['candidates']), 24)
        self.assertLess(len(seen[0].content), 40000)
        self.assertNotIn('provider_details', seen[0].content)
        self.assertNotIn('https://example.org', seen[0].content)
        self.assertTrue(all(isinstance(c, Candidate) for c in row.candidates))

    async def test_flight_search_returns_only_current_query_not_accumulated_fares(self):
        base = result('transport', TRIP, 1).candidates[0]
        evidence = {f'avia:old-{i}': base.model_copy(update={'id': f'avia:old-{i}'}) for i in range(120)}
        async with httpx.AsyncClient() as client:
            with patch('travel_agent.tools.runtime_call', new=AsyncMock(return_value={'status': 'ok', 'data': FIXTURES['search_avia']})):
                tools = {t.name: t for t in build_tools('transport', TRIP, 2, client, {}, evidence, [], {'tools': 0}, autonomous=True)}
                response = await tools['search_flights'].ainvoke({})
        self.assertTrue(response['candidates'])
        self.assertTrue(all(not c['id'].startswith('avia:old-') for c in response['candidates']))
        self.assertGreater(len(evidence), 120)
        self.assertLess(len(json.dumps(response, ensure_ascii=False)), 30000)

    async def test_tool_limit_still_finalizes_days_from_observed_places(self):
        from travel_agent.agents.experience.agent import run
        from travel_agent.schemas import SpecialistSelection
        place = result('experience', TRIP, 1).candidates[0]
        async def limited(state, config):
            raise TimeoutError()
        model = Mock()
        finalizer = AsyncMock(return_value=SpecialistSelection(source_ids=[place.id],
            days=[ProposedDay(date=TRIP.start + timedelta(days=1), source_ids=[place.id])]))
        model.with_structured_output.return_value.ainvoke = finalizer
        with patch('travel_agent.agents.react.create_agent', return_value=Mock(ainvoke=limited)):
            async with httpx.AsyncClient() as client:
                row = await run(TRIP, 2, 'Собери программу', [place], model=model, client=client, env={},
                                prompt=read_prompts()['experience'], autonomous=True)
        finalizer.assert_awaited_once()
        context = json.loads(finalizer.await_args.args[0][-1].content)
        self.assertEqual(context['phase'], 'finalize')
        self.assertEqual(row.days[0].source_ids, [place.id])
        self.assertIn('agent_limit', row.warnings)
        self.assertEqual(row.tool_calls, 0)
