import json
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from langchain_core.messages import AIMessage, ToolMessage
from pydantic import Field

from integrations.mcp.client import runtime_call
from integrations.schemas.models import Provenance
from travel_agent.agents.react import validate_candidate
from travel_agent.agents.transport.agent import run as run_transport
from travel_agent.engine import compose, offer_card
from travel_agent.prompts import load_prompt
from travel_agent.schemas import Candidate, SourceObservation, TripConstraints, TripDelta
from travel_agent.tools import build_tools
from test_agent_isolation import ToolModel
from test_travel_agent import TRIP

NOW = datetime.now(timezone.utc)
SOURCE = Provenance(provider='tutu', source_url='https://mcp.tutu.ru/mcp', retrieved_at=NOW,
    expires_at=NOW + timedelta(minutes=10), evidence='live')


def call(name, args=None):
    return AIMessage(content='', tool_calls=[{'name': name, 'args': args or {}, 'id': name, 'type': 'tool_call'}])


def finish(cards, explanation='Условия проверены по сохранённому ответу.'):
    return [call('present_offers', {'candidates': [c.model_dump(mode='json') for c in cards], 'explanation': explanation}),
        AIMessage(content='', tool_calls=[{'name': 'SpecialistSelection', 'args': {
            'source_ids': [c.id for c in cards], 'explanation': explanation}, 'id': 'finish', 'type': 'tool_call'}])]


def ref(response, *path):
    return {'observation_id': 'response:' + response, 'path': list(path)}


def flight_data():
    return {'offers': [{'offer_id': 'flight-1', 'transport': 'avia', 'price': {'amount': 9000, 'currency': 'RUB'},
        'departure_at': '2026-11-12T08:00:00+03:00', 'arrival_at': '2026-11-12T12:00:00+03:00',
        'return_departure_at': '2026-11-16T18:00:00+03:00',
        'search_results_url': 'https://avia.tutu.ru/search/example',
        'variants': [
            {'variant_id': 'basic', 'price': {'amount': 9000, 'currency': 'RUB'}, 'service_class': 'ECONOMIC',
                'conditions': {'baggage': {'kg': 0, 'pieces': 0}, 'pets': None}},
            {'variant_id': 'bag', 'price': {'amount': 17000, 'currency': 'RUB'}, 'service_class': 'ECONOMIC',
                'conditions': {'baggage': {'kg': 23, 'pieces': 1}, 'pets': {'accepted': None, 'requires_confirmation': True}}},
            {'variant_id': 'business', 'price': {'amount': 600000, 'currency': 'RUB'}, 'service_class': 'BUSINESS',
                'conditions': {'baggage': {'kg': 32, 'pieces': 2}, 'pets': {'accepted': True, 'max_weight_kg': 8, 'fee': None}}}
        ], 'future_field': {'long': 'X' * 15000, 'unclassified': [None, {'new': True}]}}],
        'meta': {'pricing': {'basis': 'party_total', 'passengers': {'full': 2}}, 'has_more': True}}


def flight_card(index=1, trip=TRIP):
    row = flight_data()['offers'][0]
    variant = row['variants'][index]
    root = ['data', 'offers', 0]
    refs = {key: ref('flight', *root, key) for key in ('departure_at', 'arrival_at', 'return_departure_at')}
    refs.update(start=refs['departure_at'], end=refs['return_departure_at'], adults=ref('flight', 'constraints', 'adults'),
        url=ref('flight', *root, 'search_results_url'), price=ref('flight', *root, 'variants', index, 'price'),
        service_class=ref('flight', *root, 'variants', index, 'service_class'))
    if trip.children_ages:
        refs['children_ages'] = ref('flight', 'constraints', 'children_ages')
    for field in ('baggage', 'pets'):
        refs['facts.' + field] = ref('flight', *root, 'variants', index, 'conditions', field)
    return Candidate(id=variant['variant_id'], role='transport', name='Найденный тариф', source=SOURCE,
        start=TRIP.start, end=TRIP.end, departure_at=row['departure_at'], arrival_at=row['arrival_at'],
        return_departure_at=row['return_departure_at'], adults=trip.adults, children_ages=trip.children_ages,
        origin=trip.origin, destination='AER', transport_mode='avia', service_class=variant['service_class'],
        price={**variant['price'], 'basis': 'party'}, facts=variant['conditions'], url=row['search_results_url'], field_refs=refs)


class RecordingModel(ToolModel):
    seen: list = Field(default_factory=list)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(list(messages))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


class AdaptiveUseCaseTests(unittest.IsolatedAsyncioTestCase):
    async def invoke_flight(self, trip, card, args=None, explanation='Условия проверены.'):
        model = RecordingModel(responses=[call('search_flights', args), *finish([card], explanation)])
        with patch('travel_agent.tools.runtime_call', new=AsyncMock(return_value={'status': 'ok', 'data': flight_data()})) as network, \
             patch('travel_agent.tools.uuid4', return_value=SimpleNamespace(hex='flight')), \
             patch('travel_agent.tools.datetime') as clock:
            clock.now.return_value = NOW
            async with httpx.AsyncClient() as client:
                result = await run_transport(trip, 1, 'Выполни текущие требования пользователя', [], model=model,
                    client=client, env={}, prompt=load_prompt('transport'))
        self.assertEqual(result.warnings, [])
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.observations[0].data, flight_data())
        observed = [json.loads(m.content) for messages in model.seen for m in messages if isinstance(m, ToolMessage) and m.name == 'search_flights']
        self.assertEqual(observed[-1]['data'], flight_data())
        return result, network.await_args.args[3]

    async def test_baggage_selects_exact_variant_price_and_preserves_other_tariffs(self):
        trip = TRIP.model_copy(update={'requirements': ['Зарегистрированный багаж минимум 20 кг']})
        result, args = await self.invoke_flight(trip, flight_card(trip=trip))
        self.assertEqual(result.candidates[0].price.amount, Decimal('17000'))
        self.assertEqual(result.candidates[0].facts['baggage']['kg'], 23)
        self.assertEqual(len(result.observations[0].data['offers'][0]['variants']), 3)
        self.assertIsNone(args['price_max'])

    async def test_children_and_infant_are_forwarded_and_kept_in_card(self):
        trip = TRIP.model_copy(update={'children_ages': [6, 1]})
        result, args = await self.invoke_flight(trip, flight_card(trip=trip))
        self.assertEqual((args['adults'], args['children'], args['infants']), (2, 1, 1))
        self.assertEqual(result.candidates[0].children_ages, [6, 1])
        self.assertEqual(result.candidates[0].price.amount, 17000)

    async def test_pet_condition_is_preserved_without_inventing_service_confirmation(self):
        trip = TRIP.model_copy(update={'requirements': ['Кошка 5 кг в салоне']})
        result, _ = await self.invoke_flight(trip, flight_card(trip=trip), explanation='Перевозка животного на этом рейсе требует подтверждения: источник не подтвердил наличие услуги.')
        self.assertIsNone(result.candidates[0].facts['pets']['accepted'])
        self.assertIn('требует подтверждения', result.explanation)
        self.assertEqual(result.observations[0].constraints['requirements'], trip.requirements)

    async def test_business_and_expensive_fare_are_not_replaced_by_cheapest(self):
        trip = TRIP.model_copy(update={'service_class': 'C', 'budget': Decimal('1000')})
        result, args = await self.invoke_flight(trip, flight_card(2, trip), {'sort': 'price_desc'})
        card = result.candidates[0]
        self.assertEqual(args['service_class'], 'C')
        self.assertEqual(args['sort'], 'price_desc')
        self.assertEqual(card.service_class, 'BUSINESS')
        self.assertEqual(card.price.amount, 600000)
        self.assertEqual(offer_card(card, trip).action, 'select')
        self.assertTrue(compose(trip, [card], 1))
        self.assertIn('over_budget', offer_card(card, trip).warnings)

    async def test_rail_roundtrip_uses_both_directions_and_never_calls_flights(self):
        trip = TRIP.model_copy(update={'transport_mode': 'rail', 'requirements': ['Купе']})
        out = {'offers': [{'offer_id': 'rail-out', 'price_party': {'amount': 12000, 'currency': 'RUB'},
            'departure_at': '2026-11-12T19:50:00+03:00', 'arrival_at': '2026-11-14T04:35:00+03:00',
            'details_ref': {'train_number': '304М', 'opaque': {'retain': True}}}], 'meta': {'pricing': {'basis': 'per_seat'}}}
        back = {'offers': [{'offer_id': 'rail-back', 'price_party': {'amount': 14000, 'currency': 'RUB'},
            'departure_at': '2026-11-16T16:04:00+03:00', 'arrival_at': '2026-11-18T02:06:00+03:00'}], 'meta': {'pricing': {'basis': 'per_seat'}}}
        card = Candidate(id='rail-roundtrip', role='transport', name='Поезд туда и обратно', source=SOURCE,
            transport_mode='rail', start=TRIP.start, end=TRIP.end, arrival_at=out['offers'][0]['arrival_at'],
            departure_at=out['offers'][0]['departure_at'], return_departure_at=back['offers'][0]['departure_at'],
            price={'amount': 26000, 'currency': 'RUB', 'basis': 'party'}, adults=2,
            field_refs={'start': ref('out', 'data', 'offers', 0, 'departure_at'), 'end': ref('back', 'data', 'offers', 0, 'departure_at'),
                'departure_at': ref('out', 'data', 'offers', 0, 'departure_at'), 'arrival_at': ref('out', 'data', 'offers', 0, 'arrival_at'),
                'return_departure_at': ref('back', 'data', 'offers', 0, 'departure_at'), 'adults': ref('out', 'constraints', 'adults')},
            price_parts=[{'reference': ref(response, 'data', 'offers', 0, 'price_party'), **row['offers'][0]['price_party']} for response, row in [('out', out), ('back', back)]])
        model = ToolModel(responses=[call('search_trains', {'seat_categories': ['COMPARTMENT']}),
            call('search_trains', {'origin': 'Сочи', 'destination': 'Москва', 'departure_date': '2026-11-16'}), *finish([card])])
        with patch('travel_agent.tools.runtime_call', new=AsyncMock(side_effect=[{'status': 'ok', 'data': out}, {'status': 'ok', 'data': back}])) as network, \
             patch('travel_agent.tools.uuid4', side_effect=[SimpleNamespace(hex='out'), SimpleNamespace(hex='back')]), \
             patch('travel_agent.tools.datetime') as clock:
            clock.now.return_value = NOW
            async with httpx.AsyncClient() as client:
                result = await run_transport(trip, 1, 'Поезд туда и обратно', [], model=model, client=client, env={}, prompt=load_prompt('transport'))
        self.assertEqual(result.warnings, [])
        self.assertEqual([c.args[2] for c in network.await_args_list], ['search_rail', 'search_rail'])
        self.assertEqual(network.await_args_list[0].args[3]['passengers'], 2)
        self.assertEqual(network.await_args_list[0].args[3]['seat_categories'], ['COMPARTMENT'])
        self.assertEqual(network.await_args_list[1].args[3]['origin'], 'Сочи')
        self.assertEqual(result.candidates[0].price.amount, 26000)
        self.assertEqual(result.candidates[0].arrival_at.day, 14)
        self.assertEqual(offer_card(result.candidates[0], trip).action, 'select')

    async def test_partial_or_invalid_model_output_never_erases_raw_response(self):
        card = flight_card()
        card.price.amount = Decimal('1')
        observation = SourceObservation(id='response:flight', role='transport', revision=1, provider='tutu', tool='search_avia',
            arguments={}, constraints=TRIP.model_dump(mode='json'), status='ok', source=SOURCE, data=flight_data())
        with self.assertRaises(ValueError):
            validate_candidate(card, 'transport', {observation.id: observation})
        self.assertEqual(observation.data, flight_data())

    async def test_model_can_repair_missing_reference_without_another_search(self):
        invalid = flight_card()
        invalid.transfers = 0
        valid = flight_card()
        model = RecordingModel(responses=[call('present_offers', {'candidates': [invalid.model_dump(mode='json')]}),
            *finish([valid])])
        observation = SourceObservation(id='response:flight', role='transport', revision=1, provider='tutu', tool='search_avia',
            arguments={}, constraints=TRIP.model_dump(mode='json'), status='ok', source=SOURCE, data=flight_data())
        with patch('travel_agent.tools.runtime_call', new=AsyncMock()) as network:
            async with httpx.AsyncClient() as client:
                result = await run_transport(TRIP, 1, 'Уточни багаж', [], model=model, client=client, env={},
                    prompt=load_prompt('transport'), observations=[observation])
        network.assert_not_called()
        self.assertEqual(result.warnings, [])
        self.assertEqual(result.candidates, [valid])
        feedback = [json.loads(m.content) for messages in model.seen for m in messages if isinstance(m, ToolMessage)]
        self.assertTrue(any(row.get('reason') == 'Missing field references: transfers' for row in feedback))
        self.assertEqual(result.observations[0].data, flight_data())

    async def test_children_and_room_filters_reach_hotel_provider_without_losing_response(self):
        trip = TRIP.model_copy(update={'children_ages': [6, 1], 'requirements': ['С питомцем']})
        data = {'hotels': [], 'filters_available': {'unknown_future': ['a', 'b']}}
        with patch('travel_agent.tools.runtime_call', new=AsyncMock(return_value={'status': 'ok', 'data': data})) as network:
            async with httpx.AsyncClient() as client:
                tools = {t.name: t for t in build_tools('stays', trip, 1, client, {}, {}, [], {'tools': 0})}
                result = await tools['search_hotels'].ainvoke({'hotel_amenities': ['pets'], 'room_amenities': ['balcony'], 'page': 2})
        args = network.await_args.args[3]
        self.assertEqual(args['children_ages'], [6, 1])
        self.assertEqual(args['hotel_amenities'], ['pets'])
        self.assertEqual(args['room_amenities'], ['balcony'])
        self.assertEqual(args['page'], 2)
        self.assertEqual(result['data'], data)

    async def test_details_reuse_owned_original_ref_across_turns(self):
        original = {'offers': [{'offer_id': 'rail-1', 'details_ref': {'train_number': '304М', 'nested': {'opaque': 'preserved'}}}]}
        observation = SourceObservation(id='response:previous', role='transport', revision=1, provider='tutu', tool='search_rail',
            arguments={}, status='ok', source=SOURCE, data=original)
        with patch('travel_agent.tools.runtime_call', new=AsyncMock(return_value={'status': 'ok', 'data': {'cars': []}})) as network:
            async with httpx.AsyncClient() as client:
                tools = {t.name: t for t in build_tools('transport', TRIP, 2, client, {}, {observation.id: observation}, [], {'tools': 0})}
                await tools['transport_details'].ainvoke({'source_id': 'rail:rail-1', 'product_type': 'rail'})
                denied = await tools['transport_details'].ainvoke({'source_id': 'rail:foreign', 'product_type': 'rail'})
        network.assert_awaited_once()
        self.assertEqual(network.await_args.args[3]['details_ref'], original['offers'][0]['details_ref'])
        self.assertEqual(denied['status'], 'forbidden')
        with patch('integrations.mcp.client.connection') as connection:
            denied = await runtime_call('transport', 'tutu', 'get_rail_seatmap', {'details_ref': {'train_number': 'foreign'}}, {})
            self.assertEqual(denied['status'], 'forbidden')
            connection.assert_not_called()

    def test_requirements_survive_incremental_changes(self):
        from travel_agent.engine import apply_delta
        trip = TRIP.model_copy(update={'requirements': ['С питомцем', 'Багаж 20 кг'], 'children_ages': [6]})
        changed, affected = apply_delta(trip, TripDelta(service_class='C'))
        self.assertEqual(changed.requirements, trip.requirements)
        self.assertEqual(changed.children_ages, [6])
        self.assertIn('transport', affected)

class EvidenceBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_strict_live_client_contract_preserves_arbitrary_card_fields(self):
        import jsonschema
        from travel_agent.agents.model import create_model
        from travel_agent.config import Settings
        card = flight_card()
        encoded = card.model_dump(mode='json')
        encoded['facts'] = json.dumps(encoded['facts'])
        encoded['field_refs'] = json.dumps(encoded['field_refs'])
        publication = {'candidates': [encoded], 'explanation': 'Выбран тариф с багажом.'}
        observation = SourceObservation(id='response:flight', role='transport', revision=1, provider='tutu', tool='search_avia',
            arguments={}, constraints=TRIP.model_dump(mode='json'), status='ok', source=SOURCE, data=flight_data())

        def respond(request):
            body = json.loads(request.content)
            self.assertEqual(body['reasoning'], {'effort': 'none'})
            self.assertTrue(all(row['function']['strict'] for row in body['tools']))
            published = any(row.get('role') == 'tool' for row in body['messages'])
            name = 'SpecialistSelection' if published else 'present_offers'
            arguments = {'source_ids': [card.id], 'explanation': 'Выбран тариф с багажом.'} if published else publication
            schema = next(row['function']['parameters'] for row in body['tools'] if row['function']['name'] == name)
            jsonschema.validate(arguments, schema)
            return httpx.Response(200, json={'id': 'completion', 'choices': [{'index': 0, 'finish_reason': 'tool_calls', 'message': {
                'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'finish', 'type': 'function', 'function': {
                    'name': name, 'arguments': json.dumps(arguments)}}]}}]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            model = create_model(Settings(model='test', token='test', base_url='https://polza.ai/api/v1', deadline=120), client)
            self.assertEqual(model.request_timeout, 120)
            result = await run_transport(TRIP, 1, 'С багажом', [], model=model, client=client, env={},
                prompt=load_prompt('transport'), observations=[observation])
        self.assertEqual(result.warnings, [])
        self.assertEqual(result.candidates[0].facts, card.facts)
        self.assertEqual(result.candidates[0].field_refs, card.field_refs)
        self.assertEqual(result.observations[0].data, flight_data())

    async def test_mcp_keeps_business_error_payload_and_entire_envelope(self):
        from contextlib import asynccontextmanager
        from integrations.mcp.client import _runtime_attempt
        raw = {'isError': False, 'structuredContent': {'error': {'code': 2001, 'unknown': {'explanation': 'retained'}}},
            'content': [{'type': 'text', 'text': 'Additional provider context'}], '_meta': {'future': [1, 2]}}
        session = SimpleNamespace(list_tools=AsyncMock(return_value=SimpleNamespace(tools=[SimpleNamespace(name='search_hotels', inputSchema={'type': 'object'})])),
            call_tool=AsyncMock(return_value=SimpleNamespace(isError=False, model_dump=lambda **kwargs: raw)))

        @asynccontextmanager
        async def connection(*args):
            yield session, None

        with patch('integrations.mcp.client.connection', side_effect=connection):
            result = await _runtime_attempt('stays', 'tutu', 'search_hotels', {}, {})
        self.assertEqual(result['status'], 'no_availability')
        self.assertEqual(result['response'], raw)
        self.assertEqual(result['data'], raw['structuredContent'])

    async def test_invalid_tool_arguments_return_actionable_error_before_call(self):
        from contextlib import asynccontextmanager
        from integrations.mcp.client import _runtime_attempt
        session = SimpleNamespace(list_tools=AsyncMock(return_value=SimpleNamespace(tools=[SimpleNamespace(name='search_avia',
            inputSchema={'type': 'object', 'properties': {'page': {'type': 'integer', 'minimum': 1}}, 'additionalProperties': False})])), call_tool=AsyncMock())

        @asynccontextmanager
        async def connection(*args):
            yield session, None

        with patch('integrations.mcp.client.connection', side_effect=connection):
            result = await _runtime_attempt('transport', 'tutu', 'search_avia', {'page': 0}, {})
        self.assertEqual(result['status'], 'schema_error')
        self.assertIn('minimum', result['data']['error']['message'])
        session.call_tool.assert_not_called()

    async def test_refinement_preserves_full_history_after_provider_failure(self):
        from langchain_core.messages import HumanMessage
        from langgraph.checkpoint.memory import InMemorySaver
        from travel_agent.graph import build_graph
        from travel_agent.schemas import SpecialistResult, SupervisorDecision
        observation = SourceObservation(id='response:flight', role='transport', revision=1, provider='tutu', tool='search_avia',
            arguments={}, status='ok', source=SOURCE, data=flight_data())
        initial = {'constraints': TRIP.model_dump(mode='json'), 'revision': 1, 'stage': 'transport', 'selected_scenario': 'direct',
            'results': {'transport': SpecialistResult(role='transport', revision=1, status='ok', observations=[observation],
                candidates=[flight_card().model_copy(update={'id': 'card:' + str(i)}) for i in range(120)]).model_dump(mode='json')}}

        async def run(role, trip, revision, task, previous, *, observations):
            self.assertEqual(observations[0].data, flight_data())
            self.assertEqual(len(previous), 120)
            return SpecialistResult(role=role, revision=revision, status='partial', warnings=['tutu:timeout'])

        graph = build_graph(AsyncMock(return_value=SupervisorDecision(action='transport', patch=TripDelta(service_class='C'))), run, InMemorySaver())
        result = await graph.ainvoke({**initial, 'calls': 0, 'messages': [HumanMessage(content='Теперь бизнес-класс')]},
            {'configurable': {'thread_id': 'owner:refine'}})
        self.assertEqual(result['revision'], 2)
        self.assertEqual(len(result['cards']), 120)
        self.assertEqual(result['results']['transport']['observations'][0]['data'], flight_data())

    async def test_known_seatmap_ref_and_schema_are_forwarded(self):
        import jsonschema
        from pathlib import Path
        data = {'offers': [{'offer_id': 'rail-1', 'details_ref': {'departure_station_code': '2000003',
            'arrival_station_code': '2064130', 'departure_at': '2026-11-12T19:50:00+03:00', 'train_number': '304М'}}]}
        observation = SourceObservation(id='response:rail', role='transport', revision=1, provider='tutu', tool='search_rail',
            arguments={}, status='ok', source=SOURCE, data=data)
        with patch('travel_agent.tools.runtime_call', new=AsyncMock(return_value={'status': 'ok', 'data': {'cars': [], 'new_data': True}})) as network:
            async with httpx.AsyncClient() as client:
                tools = {t.name: t for t in build_tools('transport', TRIP, 2, client, {}, {observation.id: observation}, [], {'tools': 0})}
                result = await tools['rail_seatmap'].ainvoke({'source_id': 'rail:rail-1', 'task': 'together', 'seats_together': 2})
        args = network.await_args.args[3]
        schema = next(t['inputSchema'] for t in json.loads(Path('reports/tutu_mcp_schema.json').read_text())['tools'] if t['name'] == 'get_rail_seatmap')
        jsonschema.validate(args, schema)
        self.assertEqual(args['details_ref'], data['offers'][0]['details_ref'])
        self.assertEqual(result['data'], {'cars': [], 'new_data': True})

    async def test_llm_payment_error_preserves_data_and_explains_cause(self):
        from openai import APIStatusError
        from travel_agent.graph import supervise
        error = APIStatusError('insufficient balance', response=httpx.Response(402, request=httpx.Request('POST', 'https://example.invalid/chat/completions')), body={})
        result = await supervise({'constraints': {}, 'calls': 0}, AsyncMock(side_effect=error))
        self.assertIn('баланса', result['answer'])
        self.assertEqual(result['status'], 'error')

    async def test_provider_secret_is_redacted_without_truncating_other_fields(self):
        secret = 'provider-secret-for-test'
        data = {'results': [{'url': 'https://example.com', 'content': secret}], 'future': {'retained': 'X' * 10000}}
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=data))) as client:
            evidence = {}
            tools = {t.name: t for t in build_tools('stays', TRIP, 1, client, {'TAVILY_API_KEY': secret}, evidence, [], {'tools': 0})}
            result = await tools['tavily_search'].ainvoke({'query': 'Условия'})
        self.assertNotIn(secret, json.dumps(result))
        self.assertEqual(result['data']['future'], data['future'])

    def test_cabin_and_conditions_cannot_be_inferred_from_requested_arguments(self):
        observation = SourceObservation(id='response:flight', role='transport', revision=1, provider='tutu', tool='search_avia',
            arguments={'service_class': 'BUSINESS'}, constraints=TRIP.model_dump(mode='json'), status='ok', source=SOURCE, data=flight_data())
        card = flight_card(2)
        card.field_refs['service_class'].path = ['arguments', 'service_class']
        with self.assertRaises(ValueError):
            validate_candidate(card, 'transport', {observation.id: observation})
