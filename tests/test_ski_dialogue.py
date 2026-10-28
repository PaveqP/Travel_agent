import unittest
from datetime import date, timedelta
from unittest.mock import AsyncMock, Mock, patch

import httpx
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import ValidationError

from integrations.schemas.models import Coordinates
from travel_agent.agents.supervisor.agent import llm_planner
from travel_agent.agents.supervisor.response import render_options, render_stays
from travel_agent.engine import apply_delta, compose_packages, search_dates
from travel_agent.graph import build_graph
from travel_agent.schemas import AgentTask, ProposedDay, RepairPlan, SpecialistResult, TripConstraints, TripDelta, TurnPlan
from travel_agent.tools import build_tools
from test_travel_agent import candidates


SKI = TripConstraints(destination='Красная Поляна', origin='Санкт-Петербург', purpose='горнолыжный отдых', holiday_type='ski', adults=2, travel_month='2026-12', nights=7)


def hotel_result(trip, revision):
    hotel = next(c for c in candidates() if c.role == 'stays')
    hotel = hotel.model_copy(update={'name': 'Горный отель (fixture)', 'start': trip.start, 'end': trip.end,
                                     'area': 'Красная Поляна', 'coordinates': Coordinates(lat=43.68, lon=40.2)})
    return SpecialistResult(role='stays', revision=revision, status='ok', candidates=[hotel], selected_ids=[hotel.id])


class SkiDialogueTests(unittest.IsolatedAsyncioTestCase):
    def test_tenth_preserves_week_and_window_preserves_preferences(self):
        moved, affected = apply_delta(SKI, TripDelta(start='2026-12-10', stay_preferences=['near_lift', 'mountain_view'], option_limit=1))
        self.assertEqual(moved.end, date(2026, 12, 17))
        self.assertEqual(moved.nights, 7)
        ranged, _ = apply_delta(moved, TripDelta(date_from='2026-12-10', date_to='2026-12-25', clear=['start', 'end', 'check_in', 'check_out']))
        self.assertTrue(search_dates(ranged))
        self.assertEqual(ranged.stay_preferences, ['near_lift', 'mountain_view'])
        self.assertTrue(all((end-start).days == 7 and date(2026,12,10) <= start < end <= date(2026,12,25) for start,end in search_dates(ranged)))
        literal_days = SKI.model_copy(update={'nights': None, 'duration_days': 7})
        moved, _ = apply_delta(literal_days, TripDelta(start='2026-12-10'))
        self.assertEqual(moved.end, date(2026,12,16))

    async def test_hotel_request_has_complete_dates_and_does_not_search_restaurants(self):
        stays = AsyncMock(side_effect=lambda trip, revision, goal, previous: hotel_result(trip, revision))
        transport, experience = AsyncMock(), AsyncMock()
        planner = AsyncMock(side_effect=[
            TurnPlan(action='plan', focus='stays', patch=TripDelta(start='2026-12-10', stay_preferences=['near_lift','mountain_view'], option_limit=1),
                     tasks=[AgentTask(role=r, goal='Поиск') for r in ('transport','stays','experience')]),
            TurnPlan(action='plan', patch=TripDelta(date_from='2026-12-10', date_to='2026-12-25', clear=['start','end']))])
        graph = build_graph(planner, {'transport': transport, 'stays': stays, 'experience': experience}, InMemorySaver(), autonomous=True)
        config = {'configurable': {'thread_id': 'ski-user-regression'}}
        state = await graph.ainvoke({'constraints': SKI.model_dump(mode='json'), 'messages': [HumanMessage(content='Ближайший отель к подъёмникам с видом на горы с 10 числа, лучший вариант')]}, config)
        self.assertEqual(state['status'], 'ready')
        self.assertIn('Горный отель', state['answer'])
        self.assertEqual(stays.await_args.args[0].end, date(2026,12,17))
        self.assertEqual(state['constraints']['stay_preferences'], ['near_lift','mountain_view'])
        transport.assert_not_called()
        experience.assert_not_called()
        state = await graph.ainvoke({'messages': [HumanMessage(content='Рассматривай даты в диапазоне с 10 по 25 декабря')]}, config)
        self.assertEqual(state['status'], 'ready')
        self.assertEqual(state['constraints']['date_from'], '2026-12-10')
        self.assertIn('Горный отель', state['answer'])
        self.assertNotIn('Ривьера', state['answer'])
        selected = await graph.ainvoke({'requested_choice': state['choices'][0]['id']}, config)
        self.assertIsNotNone(selected['selected_stay'])
        self.assertIsNone(selected['selected'])
        self.assertIn('Отель выбран', selected['answer'])

    async def test_failed_hotel_search_does_not_return_old_restaurants(self):
        graph = build_graph(AsyncMock(return_value=TurnPlan(action='plan', focus='stays', patch=TripDelta(stay_preferences=['near_lift']))),
                            {'stays': AsyncMock(return_value=SpecialistResult(role='stays',revision=1,status='partial',warnings=['timeout'])),
                             'transport': AsyncMock(), 'experience': AsyncMock()}, InMemorySaver(), autonomous=True)
        restaurant = next(c for c in candidates() if c.role=='experience')
        state = await graph.ainvoke({'constraints': SKI.model_dump(mode='json'), 'results': {'experience': SpecialistResult(role='experience',revision=0,status='ok',candidates=[restaurant]).model_dump(mode='json')}}, {'configurable': {'thread_id':'hotel-failure'}})
        self.assertNotIn(restaurant.name, state['answer'])
        self.assertIn('отел', state['answer'])
        self.assertEqual(state['status'], 'partial')

    async def test_set_clear_conflict_is_retried_without_resetting_trip(self):
        with self.assertRaises(ValidationError) as caught:
            TripDelta(start='2026-12-10', clear=['start'])
        delta = TripDelta(date_from='2026-12-10', date_to='2026-12-25', clear=['start','end'])
        routes = Mock(ainvoke=AsyncMock(side_effect=[caught.exception, TurnPlan(action='plan', focus='stays', patch=delta)]))
        extraction = Mock(ainvoke=AsyncMock(side_effect=[caught.exception, delta]))
        model=Mock()
        model.with_structured_output.side_effect=lambda schema,**kwargs: {TurnPlan:routes, TripDelta:extraction, RepairPlan:Mock()}[schema]
        state={'constraints':SKI.model_dump(mode='json'), 'messages':[HumanMessage(content='Отель у подъёмника с видом на горы, диапазон с 10 по 25 декабря')]}
        result=await llm_planner(model,'Offline prompt')(state)
        self.assertEqual(result.patch.date_to,date(2026,12,25))
        self.assertEqual(routes.ainvoke.await_count,2)
        extraction.ainvoke.assert_not_awaited()
        self.assertEqual(state['constraints']['nights'],7)

    async def test_hotel_preferences_are_forwarded_to_mcp_and_dates_can_move_inside_window(self):
        trip=SKI.model_copy(update={'start':date(2026,12,10),'end':date(2026,12,17),'date_from':date(2026,12,10),'date_to':date(2026,12,25),'stay_preferences':['near_lift','mountain_view']})
        async with httpx.AsyncClient() as client:
            tools={t.name:t for t in build_tools('stays',trip,1,client,{}, {},[],{'tools':0},autonomous=True)}
            with patch('travel_agent.tools.runtime_call',new=AsyncMock(return_value={'status':'ok','data':{'hotels':[]}})) as network:
                await tools['search_hotels'].ainvoke({'check_in':'2026-12-15','check_out':'2026-12-22'})
                args=network.await_args.args[3]
                self.assertEqual(args['room_amenities'],['mountain_view'])
                self.assertEqual(args['hotel_amenities'],['skiing'])
                self.assertEqual(args['check_out'],'2026-12-22')

    def test_ski_program_cannot_silently_become_seaside_sightseeing(self):
        from test_autonomous_planning import TRIP, ROLES, result
        trip=TRIP.model_copy(update={'holiday_type':'ski'})
        results={r:result(r,trip,1).model_dump(mode='json') for r in ROLES}
        options,feedback=compose_packages(trip,results,1)
        self.assertNotIn('ski_program_mismatch',[f.code for f in feedback])
        self.assertTrue(options)

    def test_existing_broken_state_can_recover_return_date(self):
        broken=SKI.model_copy(update={'start':date(2026,12,10),'end':None})
        fixed, affected=apply_delta(broken,TripDelta())
        self.assertEqual(fixed.end,date(2026,12,17))
        self.assertIn('transport',affected)

    async def test_month_search_waits_for_actual_transport_dates(self):
        from test_autonomous_planning import TRIP, ROLES, result
        calls=[]
        runners={}
        for role in ROLES:
            async def run(trip,revision,goal,previous,role=role):
                calls.append(role)
                if role != 'transport':
                    self.assertEqual(trip.start,TRIP.start)
                    self.assertEqual(trip.end,TRIP.end)
                return result(role,TRIP,revision)
            runners[role]=run
        tasks=[AgentTask(role=r,goal='Подбери поездку',depends_on=['stays'] if r=='transport' else []) for r in ROLES]
        graph=build_graph(AsyncMock(return_value=TurnPlan(action='plan',tasks=tasks)),runners,InMemorySaver(),autonomous=True)
        month=TRIP.model_copy(update={'start':None,'end':None,'travel_month':'2026-11','nights':4})
        state=await graph.ainvoke({'constraints':month.model_dump(mode='json')},{'configurable':{'thread_id':'actual-month-dates'}})
        self.assertEqual(calls[0],'transport')
        self.assertTrue(state['options'])

    async def test_six_search_tool_calls_leave_room_for_structured_finish(self):
        from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
        from langchain_core.messages import AIMessage
        from travel_agent.agents.stays.agent import run
        from travel_agent.prompts import read_prompts
        from test_travel_agent import TRIP, FIXTURES
        class ToolModel(FakeMessagesListChatModel):
            def bind_tools(self,tools,**kwargs):return self
        model=ToolModel(responses=[
            AIMessage(content='',tool_calls=[{'name':'search_hotels','args':{},'id':f'search-{i}','type':'tool_call'} for i in range(6)]),
            AIMessage(content='',tool_calls=[{'name':'SpecialistSelection','args':{'source_ids':[]},'id':'final','type':'tool_call'}])])
        async with httpx.AsyncClient() as client:
            with patch('travel_agent.tools.runtime_call',new=AsyncMock(return_value={'status':'ok','data':FIXTURES['search_hotels']})):
                row=await run(TRIP,1,'Найди',[],model=model,client=client,env={},prompt=read_prompts()['stays'],autonomous=True)
        self.assertNotIn('agent_limit',row.warnings)
        self.assertTrue(row.candidates)
