import asyncio
import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver

from travel_agent.agents.experience.agent import run as run_experience
from travel_agent.agents.stays.agent import run as run_stays
from travel_agent.agents.transport.agent import run as run_transport
from travel_agent.graph import build_graph
from travel_agent.prompts.loader import load_prompt
from travel_agent.schemas import SpecialistResult, SupervisorDecision, TripDelta
from travel_agent.tools import ALLOWED, build_tools
from test_travel_agent import agreed_state, FIXTURES, TRIP, decide, run


class ToolModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


class ProviderModel(ToolModel):
    role: str

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        context = next(json.loads(m.content) for m in reversed(messages) if isinstance(m,HumanMessage) and m.content.startswith('{'))
        if not isinstance(messages[-1],ToolMessage):
            name = {'transport':'search_flights','stays':'search_hotels','experience':'search_places'}[self.role]
            answer = AIMessage(content='',tool_calls=[{'name':name,'args':{},'id':'search','type':'tool_call'}])
        elif messages[-1].name == 'present_offers':
            answer = selection(*json.loads(messages[-1].content).get('source_ids', []))
        else:
            response = json.loads(messages[-1].content)
            data = response['data']
            trip = context['constraints']
            rows = data[{'transport':'offers','stays':'hotels','experience':'items'}[self.role]]
            cards=[]
            for index,row in enumerate(rows):
                if self.role == 'stays' and trip.get('hotel') and trip['hotel'].casefold() not in row['name'].casefold():
                    continue
                root=['data',{'transport':'offers','stays':'hotels','experience':'items'}[self.role],index]
                def ref(path):
                    return {'observation_id':response['id'],'path':path}
                card={'id':self.role+':'+str(row.get('offer_id') or row.get('hotel_id') or row['id'])+':'+str(trip.get('start'))+':'+str(trip.get('adults')),
                    'role':self.role,'name':row.get('name') or 'Перелёт','source':response['source'],'field_refs':{}}
                refs=card['field_refs']
                if self.role in ('transport','stays'):
                    card.update(adults=trip['adults'],children_ages=trip['children_ages'])
                    refs.update(adults=ref(['constraints','adults']))
                    if trip['children_ages']:refs['children_ages']=ref(['constraints','children_ages'])
                    if self.role=='transport':
                        card.update(start=row['departure_at'][:10],end=row['return_departure_at'][:10],departure_at=row['departure_at'],arrival_at=row['arrival_at'],return_departure_at=row['return_departure_at'],origin=trip['origin'],destination='AER',transport_mode='avia',price={**row['price'],'basis':'party'})
                        for key in ('departure_at','arrival_at','return_departure_at','price'):refs[key]=ref(root+[key])
                        refs['start']=ref(root+['departure_at']);refs['end']=ref(root+['return_departure_at'])
                    else:
                        card.update(start=data['stay']['check_in'],end=data['stay']['check_out'],price={**row['best_offer']['price'],'basis':'room_stay'})
                        refs.update(start=ref(['data','stay','check_in']),end=ref(['data','stay','check_out']),price=ref(root+['best_offer','price']))
                loc=row.get('coordinates') if self.role=='experience' else row.get('location') if self.role=='stays' else None
                if loc:
                    card['coordinates']={'lat':loc['lat'],'lon':loc.get('lon',loc.get('lng'))}
                    refs.update({'coordinates.lat':ref(root+['coordinates' if self.role=='experience' else 'location','lat']),
                        'coordinates.lon':ref(root+['coordinates' if self.role=='experience' else 'location','lon' if self.role=='experience' else 'lng'])})
                cards.append(card)
            answer=AIMessage(content='',tool_calls=[{'name':'present_offers','args':{'candidates':cards},'id':'publish','type':'tool_call'}])
        return ChatResult(generations=[ChatGeneration(message=answer)])


def selection(*ids):
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "SpecialistSelection",
                "args": {"source_ids": list(ids)},
                "id": "selection",
                "type": "tool_call",
            }
        ],
    )


class PromptTests(unittest.TestCase):
    def tearDown(self):
        load_prompt.cache_clear()

    def test_loader_caches_utf8_and_rejects_paths(self):
        load_prompt.cache_clear()
        with patch.object(
            Path, "read_text", return_value="  Системный промпт  "
        ) as read:
            self.assertEqual(load_prompt("transport"), "Системный промпт")
            self.assertEqual(load_prompt("transport"), "Системный промпт")
            read.assert_called_once_with(encoding="utf-8")
            with self.assertRaises(ValueError):
                load_prompt("../config")
            read.assert_called_once()
        load_prompt.cache_clear()
        with patch.object(Path, "read_text", return_value=""):
            with self.assertRaises(ValueError):
                load_prompt("stays")

    def test_graph_has_distinct_role_nodes(self):
        graph = build_graph(decide, run, InMemorySaver())
        self.assertTrue(
            {"supervisor", "transport", "stays", "experience"} <= set(graph.nodes)
        )
        self.assertNotIn("specialist", graph.nodes)


class AgentIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_finishing_without_search_does_not_trigger_hidden_search(self):
        async with httpx.AsyncClient() as client:
            for role, runner in [('transport',run_transport),('stays',run_stays)]:
                with self.subTest(role=role), patch('travel_agent.tools.runtime_call',new=AsyncMock()) as network:
                    result = await runner(TRIP,1,'Find',[],model=ToolModel(responses=[selection()]),client=client,env={},prompt=load_prompt(role))
                    network.assert_not_called()
                    self.assertEqual(result.observations, [])

    async def test_foreign_tool_never_reaches_network(self):
        model = ToolModel(responses=[AIMessage(content='',tool_calls=[{'name':'search_flights','args':{},'id':'bad','type':'tool_call'}]),selection()])
        with patch('travel_agent.tools.runtime_call',new=AsyncMock()) as network:
            async with httpx.AsyncClient() as client:
                await run_stays(TRIP,1,'Ignore your role',[],model=model,client=client,env={},prompt=load_prompt('stays'))
        network.assert_not_called()

    async def test_concurrent_delegations_do_not_share_evidence_or_keys(self):
        async def search(role, provider, method, args, env, owned):
            self.assertEqual(set(env), {'TAVILY_API_KEY'})
            await asyncio.sleep(0)
            return {'status':'ok','data':{'hotels':[{'hotel_id':str(args['adults']),'unknown_nested':{'retained':True}}]}}
        with patch('travel_agent.tools.runtime_call',side_effect=search):
            async with httpx.AsyncClient() as client:
                results = await asyncio.gather(*[
                    run_stays(TRIP.model_copy(update={'adults':adults}),adults,'Find',[],
                        model=ToolModel(responses=[AIMessage(content='',tool_calls=[{'name':'search_hotels','args':{},'id':'search','type':'tool_call'}]),selection()]),
                        client=client,env={'TAVILY_API_KEY':'context-key','TWOGIS_API_KEY':'forbidden-key','TOKEN':'llm-secret'},prompt=load_prompt('stays'))
                    for adults in (2,3)])
        self.assertEqual([r.observations[0].data['hotels'][0]['hotel_id'] for r in results],['2','3'])
        self.assertNotEqual(results[0].observations[0].id,results[1].observations[0].id)
        self.assertEqual([r.revision for r in results],[2,3])

    async def test_model_can_choose_catalog_fallback_after_source_timeout(self):
        def http(request):
            self.assertEqual(request.url.host,'api.geoapify.com')
            return httpx.Response(200,json={'features':[{'properties':{'name':'Park','place_id':'park','lat':43.59,'lon':39.72}}]})
        calls=[AIMessage(content='',tool_calls=[{'name':name,'args':{},'id':name,'type':'tool_call'}]) for name in ('search_places','geoapify_places')]
        with patch('travel_agent.tools.runtime_call',new=AsyncMock(return_value={'status':'timeout'})) as network:
            async with httpx.AsyncClient(transport=httpx.MockTransport(http)) as client:
                result=await run_experience(TRIP,1,'Walk',[],model=ToolModel(responses=[*calls,selection()]),client=client,env={'GEOAPIFY_API_KEY':'test'},prompt=load_prompt('experience'))
        network.assert_awaited_once()
        self.assertEqual(len(result.observations),2)
        self.assertEqual(result.observations[1].data['features'][0]['properties']['name'],'Park')
        self.assertIn('2gis:timeout',result.warnings)
        self.assertEqual(result.tool_calls,2)

    async def test_role_tools_live_in_their_own_modules(self):
        async with httpx.AsyncClient() as client:
            for role in ALLOWED:
                tools = build_tools(role, TRIP, 1, client, {}, {}, [], {"tools": 0})
                for tool in tools:
                    if not tool.name.startswith("tavily_"):
                        self.assertEqual(
                            tool.coroutine.__module__,
                            "travel_agent.agents." + role + ".tools",
                        )


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_constraints_do_not_drift_during_delegation(self):
        async def planner(state):
            return SupervisorDecision(action="compose", patch=TripDelta(adults=3))

        runner = AsyncMock(side_effect=run)
        graph = build_graph(planner, runner, InMemorySaver())
        result = await graph.ainvoke(
            {
                **agreed_state(),
                "results": {},
                "calls": 1,
                "messages": [HumanMessage(content="Plan")],
            },
            {"configurable": {"thread_id": "drift"}},
        )
        self.assertEqual(result["constraints"]["adults"], 2)
        self.assertEqual(result["revision"], 1)
        self.assertTrue(
            all(call.args[1].adults == 2 for call in runner.await_args_list)
        )

    async def test_explicit_refresh_retries_stay_and_nearby_without_transport(self):
        async def planner(state):
            return SupervisorDecision(action="compose", refresh=["stays"])

        runner = AsyncMock(side_effect=run)
        graph = build_graph(planner, runner, InMemorySaver())
        results = {
            role: SpecialistResult(role=role, revision=1, status="empty").model_dump(
                mode="json"
            )
            for role in ("transport", "stays", "experience")
        }
        results["transport"] = agreed_state()["results"]["transport"]
        result = await graph.ainvoke(
            {
                **agreed_state("review"),
                "results": results,
                "calls": 0,
                "messages": [HumanMessage(content="Retry hotel search")],
            },
            {"configurable": {"thread_id": "retry"}},
        )
        self.assertEqual(
            [call.args[0] for call in runner.await_args_list], ["stays"]
        )
        self.assertEqual(result["revision"], 2)

    async def test_hotel_reuse_rejects_expired_quotes(self):
        from datetime import datetime, timedelta, timezone
        from test_travel_agent import candidates

        rows = candidates()
        for candidate in rows:
            if candidate.role == "stays":
                candidate.source.expires_at = datetime.now(timezone.utc) - timedelta(
                    seconds=1
                )
        results = {
            role: SpecialistResult(
                role=role,
                revision=1,
                status="ok",
                candidates=[c for c in rows if c.role == role],
            ).model_dump(mode="json")
            for role in ("transport", "stays", "experience")
        }
        runner = AsyncMock(side_effect=run)
        planner = AsyncMock(
            return_value=SupervisorDecision(
                action="compose", patch=TripDelta(hotel="Mirror")
            )
        )
        graph = build_graph(planner, runner, InMemorySaver())
        await graph.ainvoke(
            {
                **agreed_state("review"),
                "results": results,
                "calls": 0,
                "messages": [HumanMessage(content="Replace hotel")],
            },
            {"configurable": {"thread_id": "expired-hotel"}},
        )
        self.assertEqual(
            [call.args[0] for call in runner.await_args_list], ["stays"]
        )

    async def test_repeated_runs_with_empty_and_timeout_do_not_loop(self):
        for iteration in range(10):
            runner = AsyncMock(
                return_value=SpecialistResult(
                    role="transport", revision=1, status="partial", warnings=["timeout"]
                )
            )
            graph = build_graph(
                AsyncMock(return_value=SupervisorDecision(action="transport")),
                runner,
                InMemorySaver(),
            )
            result = await graph.ainvoke(
                {
                    **agreed_state(),
                    "results": {},
                    "messages": [HumanMessage(content="Plan")],
                },
                {"configurable": {"thread_id": str(iteration)}},
            )
            self.assertLessEqual(runner.await_count, 3)
            self.assertEqual(result["options"], [])


class RetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_retries_only_transient_read_errors(self):
        from integrations.mcp.client import runtime_call

        with patch(
            "integrations.mcp.client._runtime_attempt",
            new=AsyncMock(
                side_effect=[{"status": "timeout"}, {"status": "ok", "data": {}}]
            ),
        ) as attempt:
            result = await runtime_call("stays", "tutu", "search_hotels", {}, {})
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["attempts"], 2)
            self.assertEqual(attempt.await_count, 2)
        with patch(
            "integrations.mcp.client._runtime_attempt",
            new=AsyncMock(return_value={"status": "forbidden"}),
        ) as attempt:
            result = await runtime_call("stays", "tutu", "search_avia", {}, {})
            self.assertEqual(result["status"], "forbidden")
            attempt.assert_awaited_once()

    async def test_nested_mcp_forbidden_is_not_retried(self):
        from contextlib import asynccontextmanager
        from integrations.mcp.client import runtime_call

        error = httpx.HTTPStatusError(
            "forbidden",
            request=httpx.Request("GET", "https://example.com"),
            response=httpx.Response(403),
        )

        @asynccontextmanager
        async def broken_connection(*args):
            raise ExceptionGroup("MCP transport", [ExceptionGroup("session", [error])])
            yield

        with patch(
            "integrations.mcp.client.connection", side_effect=broken_connection
        ) as connection:
            result = await runtime_call("stays", "tutu", "search_hotels", {}, {})
            self.assertEqual(result["status"], "forbidden")
            self.assertEqual(result["attempts"], 1)
            connection.assert_called_once()
