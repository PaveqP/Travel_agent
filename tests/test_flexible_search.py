import copy
import json
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import httpx
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import ValidationError

from travel_agent.agents.supervisor.agent import llm_decider
from travel_agent.engine import compose, offer_card, quote_current
from travel_agent.graph import build_graph, present_stage
from travel_agent.schemas import Candidate, OfferCard, SpecialistResult, SupervisorDecision, TripConstraints, TripDelta
from travel_agent.tools import build_tools
from test_travel_agent import FIXTURES, TRIP, agreed_state, candidates, run


class FlexibleDateTests(unittest.TestCase):
    def test_flexible_dates_remain_user_constraints_without_python_probes(self):
        trip=TripConstraints(origin='Москва',adults=2,date_from='2026-12-01',date_to='2026-12-20',nights=7)
        self.assertIsNone(trip.start)
        self.assertEqual(trip.date_to,date(2026,12,20))
        with self.assertRaises(ValidationError):
            TripConstraints(date_from='2026-12-20',date_to='2026-12-01')

    def test_cards_preserve_actual_money_dates_source_and_unknown_price(self):
        flight=next(c for c in candidates() if c.role=='transport')
        card=OfferCard.model_validate(offer_card(flight,TRIP).model_dump(mode='json'))
        self.assertEqual(card.price.amount,flight.price.amount)
        self.assertEqual(card.price.basis,'party')
        self.assertEqual(card.price_per_person.amount,flight.price.amount/TRIP.adults)
        self.assertEqual(card.action,'select')
        flight.price=None
        self.assertEqual(offer_card(flight,TRIP).action,'verify')
        self.assertFalse(quote_current(flight))

    def test_no_card_limit_or_price_order_overrides_agent_order(self):
        state=agreed_state('stays')
        stay=Candidate.model_validate(state['results']['stays']['candidates'][0])
        state['results']['stays']['candidates']=[stay.model_copy(update={'id':f'hotel:{i}'}).model_dump(mode='json') for i in range(40)]
        state['results']['stays']['selected_ids']=['hotel:39']
        result=present_stage(state)
        self.assertEqual(len(result['cards']),40)
        self.assertEqual(result['cards'][0]['id'],'hotel:39')


class FlexibleSearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_is_one_explicit_request_with_full_response(self):
        data=copy.deepcopy(FIXTURES['search_avia'])
        data['unknown_new_field']={'nested':[None,{'future_condition':'retained'}]}
        with patch('travel_agent.tools.runtime_call',new=AsyncMock(return_value={'status':'ok','data':data})) as network:
            async with httpx.AsyncClient() as client:
                evidence={}
                tools={t.name:t for t in build_tools('transport',TRIP,1,client,{},evidence,[],{'tools':0})}
                result=await tools['search_flights'].ainvoke({'departure_date':'2026-12-03','return_date':'2026-12-10','page':2,'sort':'price_desc','service_class':'C'})
        network.assert_awaited_once()
        self.assertEqual(network.await_args.args[3]['page'],2)
        self.assertEqual(network.await_args.args[3]['service_class'],'C')
        self.assertEqual(result['data'],data)
        self.assertEqual(next(iter(evidence.values())).data,data)

    async def test_web_context_is_not_truncated_or_converted_to_quotes(self):
        data={'results':[{'url':'https://example.com','title':'T'*300,'content':'X'*12000}],'new_property':{'raw':True}}
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=data))) as client:
            evidence={}
            tools={t.name:t for t in build_tools('stays',TRIP,1,client,{'TAVILY_API_KEY':'test'},evidence,[],{'tools':0})}
            result=await tools['tavily_search'].ainvoke({'query':'Условия'})
        self.assertEqual(result['data'],data)
        self.assertNotIn('candidates',result)

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
        flight = next(c for c in candidates() if c.role == 'transport')
        for field in ('departure_at','arrival_at','return_departure_at'):
            setattr(flight,field,getattr(flight,field)+timedelta(days=1))
        flight.start += timedelta(days=1)
        flight.end += timedelta(days=1)
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

        async def empty(role, trip, revision, task, previous, *, observations=None):
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
        model.with_structured_output.assert_called_once_with(SupervisorDecision, method='function_calling', strict=True)
        self.assertEqual(json.loads(structured.await_args_list[0].args[0][2].content)['user_request'], 'С 1 по 20 декабря')
        self.assertEqual(result.patch.date_to, date(2026, 12, 20))
        self.assertEqual(structured.await_count, 2)
        self.assertIn('patch.date_from/date_to', structured.await_args.args[0][-1].content)
