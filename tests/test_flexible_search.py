import copy
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import httpx
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import ValidationError

from travel_agent.agents.supervisor.agent import llm_decider
from travel_agent.engine import compose, offer_card, search_dates, transport_matches, usable
from travel_agent.graph import build_graph, present_stage
from travel_agent.schemas import Candidate, OfferCard, SpecialistResult, SupervisorDecision, TripConstraints, TripDelta
from travel_agent.tools import build_tools, normalize
from test_travel_agent import FIXTURES, TRIP, agreed_state, candidates, run


def flight_data(args):
    data = copy.deepcopy(FIXTURES['search_avia'])
    data['meta']['pricing']['passengers']['full'] = args['adults']
    for row in data['offers']:
        row['offer_id'] += args['departure_date']
        for field in ('departure_at', 'arrival_at'):
            row[field] = args['departure_date'] + row[field][10:]
        row['return_departure_at'] = args['return_date'] + row['return_departure_at'][10:]
    return data


class FlexibleDateTests(unittest.TestCase):
    def test_nearest_dates_keep_duration_and_respect_strict_dates(self):
        pairs = search_dates(TRIP)
        self.assertEqual(pairs[:3], [(TRIP.start, TRIP.end), (TRIP.start - timedelta(days=1), TRIP.end - timedelta(days=1)), (TRIP.start + timedelta(days=1), TRIP.end + timedelta(days=1))])
        self.assertEqual(search_dates(TRIP.model_copy(update={'date_flexibility': 0})), [(TRIP.start, TRIP.end)])

    def test_explicit_window_and_month_work_without_exact_dates(self):
        trip = TripConstraints(origin='Санкт-Петербург', adults=4, date_from='2026-12-01', date_to='2026-12-20')
        pairs = search_dates(trip)
        self.assertEqual(pairs[0], (date(2026, 12, 1), date(2026, 12, 8)))
        self.assertEqual(pairs[-1], (date(2026, 12, 13), date(2026, 12, 20)))
        self.assertTrue(all(trip.date_from <= start < end <= trip.date_to for start, end in pairs))
        month = TripConstraints(travel_month='2026-12', nights=7)
        self.assertEqual(search_dates(month)[0], pairs[0])
        self.assertEqual(search_dates(month)[-1][1], date(2026, 12, 31))
        with self.assertRaises(ValidationError):
            TripConstraints(date_from='2026-12-20', date_to='2026-12-01')

    def test_cards_preserve_actual_money_dates_source_and_unknown_price(self):
        flight = next(c for c in candidates() if c.role == 'transport')
        card = OfferCard.model_validate(offer_card(flight, TRIP).model_dump(mode='json'))
        self.assertEqual(card.aggregator, 'Туту')
        self.assertEqual(card.url, flight.url)
        self.assertEqual(card.dates.start, flight.start)
        self.assertEqual(card.price.amount, flight.price.amount)
        self.assertEqual(card.price.basis, 'party')
        self.assertEqual(card.price_per_person.amount, flight.price.amount / TRIP.adults)
        self.assertEqual(card.action, 'select')
        activity = next(c for c in candidates() if c.role == 'experience')
        place = offer_card(activity, TRIP)
        self.assertTrue(place.url.startswith('https://2gis.ru/'))
        self.assertIsNone(place.price)
        self.assertEqual(place.action, 'view')

    def test_cached_fare_is_visible_but_cannot_enter_checkout(self):
        data = {'data': [{'origin': 'MOW', 'destination': 'AER', 'price': 12345, 'airline': 'SU', 'departure_at': '2026-11-12T08:00:00+03:00', 'return_at': '2026-11-16T19:00:00+03:00', 'link': '/search/MOW1211AER16111', 'transfers': 0}]}
        cached = normalize('travelpayouts', '', data, TRIP, datetime.now(timezone.utc))[0]
        card = offer_card(cached, TRIP)
        self.assertEqual(card.price.basis, 'person')
        self.assertEqual(card.price.amount, Decimal('12345'))
        self.assertEqual(card.adults, 1)
        self.assertEqual(card.evidence, 'cached')
        self.assertEqual(card.action, 'verify')
        self.assertIn('different_party', card.warnings)
        self.assertIsNone(cached.arrival_at)
        self.assertFalse(usable(cached, TRIP, datetime.now(timezone.utc)))
        self.assertFalse(any(o.transport for o in compose(TRIP, [cached, *[c for c in candidates() if c.role == 'stays']], 1)))
        self.assertTrue(card.url.startswith('https://www.aviasales.ru/search/'))

    def test_hotel_without_verified_total_stays_visible_with_unknown_price(self):
        data = copy.deepcopy(FIXTURES['search_hotels'])
        data['hotels'][0]['best_offer'] = {}
        rows = normalize('tutu', 'search_hotels', data, TRIP, datetime.now(timezone.utc))
        self.assertEqual(len(rows), 3)
        card = offer_card(rows[0], TRIP)
        self.assertIsNone(card.price)
        self.assertEqual(card.action, 'verify')
        self.assertFalse(usable(rows[0], TRIP, datetime.now(timezone.utc)))

    def test_all_ten_stays_and_all_activity_cards_are_presented(self):
        state = agreed_state('stays')
        stay = Candidate.model_validate(state['results']['stays']['candidates'][0])
        state['results']['stays']['candidates'] = [stay.model_copy(update={'id': f'hotel:{i}'}).model_dump(mode='json') for i in range(10)]
        result = present_stage(state)
        self.assertEqual(len(result['cards']), 10)
        self.assertEqual(len(result['choices']), 10)
        self.assertTrue(all(c['url'] and c['aggregator'] and c['description'] for c in result['cards']))
        activities = present_stage(agreed_state('itinerary'))['cards']
        self.assertTrue(activities)
        self.assertTrue(all(c['action'] == 'view' and c['price'] is None for c in activities))


class FlexibleSearchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})))
        self.evidence = {}
        self.warnings = []
        self.counts = {'tools': 0}

    async def asyncTearDown(self):
        await self.client.aclose()

    def tools(self, trip=TRIP, role='transport', env=None):
        return {t.name: t for t in build_tools(role, trip, 1, self.client, env or {}, self.evidence, self.warnings, self.counts)}

    async def test_empty_exact_search_probes_neighbors_and_keeps_real_dates(self):
        async def source(role, provider, method, args, env, owned):
            data = flight_data(args)
            if args['departure_date'] == str(TRIP.start):
                data = {'offers': []}
            return {'status': 'ok', 'data': data}

        with patch('travel_agent.tools.runtime_call', new=AsyncMock(side_effect=source)) as network:
            result = await self.tools()['search_flights'].ainvoke({})
        self.assertEqual(network.await_count, 6)
        self.assertTrue(self.evidence)
        self.assertTrue(all(c.start != TRIP.start and transport_matches(c, TRIP, datetime.now(timezone.utc)) for c in self.evidence.values()))
        self.assertFalse(result['exhaustive'])
        self.assertTrue(all(c.args[3]['sort'] == 'price_asc' for c in network.await_args_list))

    async def test_fresh_exact_offers_stop_additional_probes(self):
        with patch('travel_agent.tools.runtime_call', new=AsyncMock(return_value={'status': 'ok', 'data': FIXTURES['search_avia']})) as network:
            result = await self.tools()['search_flights'].ainvoke({})
        self.assertEqual(network.await_count, 1)
        self.assertTrue(result['candidates'])

    async def test_window_uses_aggregator_filters_without_asking_exact_dates(self):
        trip = TripConstraints(origin='Москва', adults=2, date_from='2026-12-01', date_to='2026-12-20', nights=7, direct_only=True)

        async def source(role, provider, method, args, env, owned):
            return {'status': 'ok', 'data': flight_data(args)}

        with patch('travel_agent.tools.runtime_call', new=AsyncMock(side_effect=source)) as network:
            await self.tools(trip)['search_flights'].ainvoke({})
        self.assertLessEqual(network.await_count, 6)
        for call in network.await_args_list:
            args = call.args[3]
            self.assertTrue(args['direct_only'])
            self.assertTrue(trip.date_from <= date.fromisoformat(args['departure_date']) < date.fromisoformat(args['return_date']) <= trip.date_to)
        self.assertTrue(self.evidence)

    async def test_source_failure_does_not_repeat_six_identical_failures(self):
        with patch('travel_agent.tools.runtime_call', new=AsyncMock(return_value={'status': 'forbidden'})) as network:
            result = await self.tools()['search_flights'].ainvoke({})
        self.assertEqual(network.await_count, 1)
        self.assertEqual(result['status'], 'forbidden')

    async def test_cached_fallback_resolves_known_origin_and_month_filters(self):
        trip = TripConstraints(origin='Санкт-Петербург', adults=4, date_from='2026-12-01', date_to='2026-12-20')
        response = httpx.Response(200, json={'success': True, 'data': []}, request=httpx.Request('GET', 'https://api.travelpayouts.com/'))
        with patch('travel_agent.agents.transport.tools.travelpayouts.prices', new=AsyncMock(return_value=response)) as network:
            await self.tools(trip, env={'TRAVELPAYOUTS_TOKEN': 'test-token'})['cached_flights'].ainvoke({})
        self.assertEqual(network.await_args.args[2:], ('LED', '2026-12', '2026-12'))

    async def test_web_hotel_reference_keeps_source_and_unknown_price(self):
        data = {'results': [{'url': 'https://hotel.tutu.ru/hotel/example', 'title': 'Наблюдённый отель', 'content': 'Описание со страницы источника'}]}
        response = httpx.Response(200, json=data, request=httpx.Request('POST', 'https://api.tavily.com/search'))
        with patch.object(self.client, 'post', new=AsyncMock(return_value=response)):
            await self.tools(role='stays', env={'TAVILY_API_KEY': 'test-key'})['tavily_search'].ainvoke({'query': 'Отель'})
        card = offer_card(next(iter(self.evidence.values())), TRIP)
        self.assertEqual(card.url, data['results'][0]['url'])
        self.assertEqual(card.description, data['results'][0]['content'])
        self.assertEqual(card.evidence, 'catalog')
        self.assertIsNone(card.price)
        self.assertFalse(card.selectable)


class FlexibleGraphTests(unittest.IsolatedAsyncioTestCase):
    async def test_ten_expired_unselected_fares_refresh_and_remain_visible_on_failure(self):
        state = agreed_state()
        flight = Candidate.model_validate(state['results']['transport']['candidates'][0])
        flight.source.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        state['results']['transport']['candidates'] = [flight.model_copy(update={'id': f'avia:{i}'}).model_dump(mode='json') for i in range(10)]
        runner = AsyncMock(return_value=SpecialistResult(role='transport', revision=1, status='partial', warnings=['tutu:timeout']))
        graph = build_graph(AsyncMock(return_value=SupervisorDecision(action='compose')), runner, InMemorySaver())
        result = await graph.ainvoke({**state, 'calls': 0, 'messages': [HumanMessage(content='Дай доступные варианты')]}, {'configurable': {'thread_id': 'expired-ten'}})
        runner.assert_awaited_once()
        self.assertEqual(len(result['cards']), 10)
        self.assertTrue(all(c['action'] == 'verify' and 'expired_quote' in c['warnings'] for c in result['cards']))
        self.assertEqual(result['diagnostics']['rejected']['expired_quote'], 10)
        self.assertIn('https://', result['answer'])
        self.assertNotIn('предложений нет', result['answer'])
        self.assertIsNone(result.get('selected_transport'))

    async def test_range_request_delegates_even_if_supervisor_tries_to_clarify(self):
        patch_delta = TripDelta(date_from='2026-12-01', date_to='2026-12-20')
        planner = AsyncMock(return_value=SupervisorDecision(action='clarify', patch=patch_delta, question='Какие точные даты?'))
        runner = AsyncMock(side_effect=run)
        graph = build_graph(planner, runner, InMemorySaver())
        result = await graph.ainvoke({**agreed_state(), 'calls': 0, 'messages': [HumanMessage(content='Любые билеты с 1 по 20 декабря')]}, {'configurable': {'thread_id': 'window'}})
        self.assertEqual(runner.await_args.args[0], 'transport')
        self.assertEqual(runner.await_args.args[1].date_from, date(2026, 12, 1))
        self.assertEqual(result['stage'], 'transport')
        self.assertNotIn('Какие точные даты?', result['answer'])

    async def test_selecting_nearby_fare_accepts_dates_and_immediately_searches_stays(self):
        state = agreed_state()
        args = {'adults': 2, 'departure_date': '2026-11-13', 'return_date': '2026-11-17'}
        flight = normalize('tutu', 'search_avia', flight_data(args), TripConstraints(origin='Москва', adults=2, start=args['departure_date'], end=args['return_date']), datetime.now(timezone.utc))[0]
        state['results']['transport']['candidates'] = [flight.model_dump(mode='json')]
        runner = AsyncMock(side_effect=run)
        graph = build_graph(AsyncMock(), runner, InMemorySaver())
        result = await graph.ainvoke({**state, 'calls': 0, 'requested_choice': flight.id}, {'configurable': {'thread_id': 'shift-choice'}})
        self.assertEqual(result['constraints']['start'], args['departure_date'])
        self.assertEqual(result['constraints']['check_in'], args['departure_date'])
        self.assertEqual(result['selected_transport'], flight.id)
        self.assertEqual(runner.await_args.args[0], 'stays')
        self.assertIsNone(result['pending_check_in'])

    async def test_expired_card_selection_checks_source_without_accepting_old_price(self):
        state = agreed_state()
        flight = state['results']['transport']['candidates'][0]
        flight['source']['expires_at'] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        runner = AsyncMock(side_effect=run)
        graph = build_graph(AsyncMock(), runner, InMemorySaver())
        result = await graph.ainvoke({**state, 'requested_choice': flight['id'], 'calls': 0}, {'configurable': {'thread_id': 'verify'}})
        self.assertEqual(runner.await_args.args[0], 'transport')
        self.assertEqual(result['stage'], 'transport')
        self.assertIsNone(result['selected_transport'])
        self.assertEqual(result['cards'][0]['action'], 'select')

    async def test_explicit_refresh_failure_keeps_previous_cards(self):
        state = agreed_state()

        async def empty(role, trip, revision, task, previous):
            return SpecialistResult(role=role, revision=revision, status='partial', warnings=['tutu:timeout'])

        graph = build_graph(AsyncMock(return_value=SupervisorDecision(action='compose', refresh=['transport'])), empty, InMemorySaver())
        result = await graph.ainvoke({**state, 'calls': 0, 'messages': [HumanMessage(content='Обнови билеты')]}, {'configurable': {'thread_id': 'refresh-failed'}})
        self.assertTrue(result['cards'])
        self.assertEqual(result['cards'][0]['id'], state['results']['transport']['candidates'][0]['id'])
        self.assertEqual(result['revision'], 2)

    async def test_structured_range_format_is_repaired_once(self):
        try:
            SupervisorDecision.model_validate({'action': 'compose', 'patch': {'date_range': ['2026-12-01', '2026-12-20']}})
        except ValidationError as exc:
            error = exc
        structured = AsyncMock(side_effect=[error, SupervisorDecision(action='compose', patch=TripDelta(date_from='2026-12-01', date_to='2026-12-20'))])
        model = Mock()
        model.with_structured_output.return_value = Mock(ainvoke=structured)
        result = await llm_decider(model, 'Supervisor')({'messages': [HumanMessage(content='С 1 по 20 декабря')]})
        self.assertEqual(result.patch.date_to, date(2026, 12, 20))
        self.assertEqual(structured.await_count, 2)
        self.assertIn('patch.date_from/date_to', structured.await_args.args[0][-1].content)
