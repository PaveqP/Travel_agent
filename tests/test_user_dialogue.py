import asyncio
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from travel_agent.agents.research import research
from travel_agent.agents.supervisor.response import llm_presenter, render_options
from travel_agent.engine import apply_delta, compose
from travel_agent.graph import build_graph
from travel_agent.prompts import load_prompt
from travel_agent.schemas import (
    ResearchResult,
    SupervisorDecision,
    TripDelta,
    UserResponse,
)
from test_agent_isolation import ToolModel, selection
from test_travel_agent import TRIP, candidates, run


class ResponseModel:
    def __init__(self, response):
        self.response = response
        self.messages = []

    def with_structured_output(self, schema, **kwargs):
        async def respond(messages):
            self.messages = messages
            return self.response

        return RunnableLambda(respond)


def planned():
    return {
        "constraints": TRIP.model_dump(mode="json"),
        "revision": 1,
        "options": [o.model_dump(mode="json") for o in compose(TRIP, candidates(), 1)],
        "decision": {"action": "compose"},
        "messages": [HumanMessage(content="Сравни варианты")],
    }


class DialogueTests(unittest.IsolatedAsyncioTestCase):
    async def test_purpose_required_before_any_search_and_can_continue(self):
        async def decide(state):
            return SupervisorDecision(
                action="compose",
                patch=TripDelta(purpose="Гулять")
                if state["messages"][-1].content == "Гулять"
                else TripDelta(),
            )

        runner = AsyncMock(side_effect=run)
        graph = build_graph(decide, runner, InMemorySaver())
        config = {"configurable": {"thread_id": "purpose"}}
        initial = TRIP.model_dump(mode="json")
        initial["purpose"] = None
        result = await graph.ainvoke(
            {
                "constraints": initial,
                "messages": [HumanMessage(content="Поездка")],
                "calls": 0,
            },
            config,
        )
        self.assertEqual(result["status"], "needs_input")
        self.assertIn("Какой отдых", result["answer"])
        runner.assert_not_called()
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="Гулять")], "calls": 0, "attempts": []},
            config,
        )
        self.assertEqual(result["stage"], "scenarios")
        runner.assert_not_called()
        result = await graph.ainvoke({"requested_choice": result["choices"][0]["id"], "calls": 0}, config)
        self.assertEqual(result["stage"], "transport")
        self.assertEqual(runner.await_count, 1)

    async def test_research_preserves_quotes_revision_selection_and_constraints(self):
        state = planned()
        state["selected"] = state["options"][1]["id"]
        state["results"] = {
            "transport": {"status": "ok", "warnings": [], "candidates": []}
        }
        state["calls"] = 0
        lookup = AsyncMock(return_value=ResearchResult(role="stays"))
        presenter = AsyncMock(return_value="Проверил сведения об отеле.")
        runner = AsyncMock()
        decide = AsyncMock(
            return_value=SupervisorDecision(
                action="research",
                research_role="stays",
                task="Mirror: есть ли бассейн?",
                patch=TripDelta(adults=6),
                refresh=["transport"],
            )
        )
        graph = build_graph(decide, runner, InMemorySaver(), presenter, lookup)
        result = await graph.ainvoke(state, {"configurable": {"thread_id": "question"}})
        self.assertEqual(result["options"], state["options"])
        self.assertEqual(result["constraints"], state["constraints"])
        self.assertEqual(result["revision"], 1)
        self.assertEqual(result["selected"], state["selected"])
        runner.assert_not_called()
        lookup.assert_awaited_once()
        self.assertEqual(result["answer"], "Проверил сведения об отеле.")

    async def test_real_research_agent_calls_search_and_extract_without_mcp(self):
        requests = []

        def handle(request):
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "url": "https://example.com/hotel",
                            "title": "Отель",
                            "content": "Есть бассейн по описанию отеля.",
                        }
                    ]
                },
            )

        from langchain_core.messages import AIMessage

        extract = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "tavily_extract",
                    "args": {"selected_urls": ["https://example.com/hotel"]},
                    "id": "extract",
                    "type": "tool_call",
                }
            ],
        )
        state = planned()
        state["decision"] = {"research_role": "stays", "task": "Mirror Сочи бассейн"}
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            with (
                patch("travel_agent.tools.runtime_call", new=AsyncMock()) as mcp,
                patch.object(
                    asyncio.get_running_loop(),
                    "getaddrinfo",
                    new=AsyncMock(return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]),
                ),
            ):
                result = await research(
                    state,
                    models={"stays": ToolModel(responses=[extract, selection()])},
                    client=client,
                    env={"TAVILY_API_KEY": "fixture-key"},
                    prompt=load_prompt("research"),
                )
                mcp.assert_not_called()
        self.assertEqual([r.url.path for r in requests], ["/search", "/extract"])
        self.assertEqual(
            json.loads(requests[0].content)["query"], "Mirror Сочи бассейн"
        )
        self.assertEqual(result.sources[0].url, "https://example.com/hotel")
        self.assertIn("бассейн", result.sources[0].text)

    async def test_missing_web_key_does_not_claim_web_success(self):
        state = planned()
        state["decision"] = {
            "action": "research",
            "research_role": "stays",
            "task": "Отзывы",
        }
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: self.fail("Network forbidden"))
        ) as client:
            result = await research(
                state, models={}, client=client, env={}, prompt=load_prompt("research")
            )
        self.assertIn("tavily:missing_key", result.warnings)
        state["research"] = result.model_dump(mode="json")
        present = llm_presenter(
            ResponseModel(UserResponse(text="invented")), load_prompt("response")
        )
        answer = await present(state)
        self.assertIn("Сохранённые варианты", answer)
        self.assertNotIn("не удалось", answer)

    async def test_response_grounded_ids_prices_and_source_links(self):
        state = planned()
        response = UserResponse(
            text="Сравнил варианты для прогулок.",
            options=[
                {
                    "option_id": o["id"],
                    "benefit": "Можно сравнить известные расходы.",
                    "tradeoff": "Удобства пока не проверены.",
                }
                for o in state["options"]
            ],
        )
        model = ResponseModel(response)
        text = await llm_presenter(model, load_prompt("response"))(state)
        self.assertIn("**Москва → Сочи**", text)
        self.assertIn("**19 590 ₽ за группу**", text)
        self.assertNotIn("T15:", text)
        self.assertNotIn("Полная стоимость неизвестна", text)
        self.assertLess(len(text), 1200)
        self.assertEqual(model.messages, [])
        self.assertNotIn("known_subtotal", text)
        response.options[0].option_id = "fabricated"
        self.assertEqual(
            await llm_presenter(model, load_prompt("response"))(state),
            render_options(state),
        )

    async def test_sqlite_trip_and_research_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "trip.sqlite")
            config = {"configurable": {"thread_id": "owner:trip"}}
            for iteration in range(2):
                async with AsyncSqliteSaver.from_conn_string(path) as saver:
                    graph = build_graph(
                        AsyncMock(return_value=SupervisorDecision(action="answer")),
                        AsyncMock(),
                        saver,
                    )
                    if not iteration:
                        state = planned()
                        state["research"] = {
                            "role": "stays",
                            "sources": [
                                {
                                    "url": "https://example.com/hotel",
                                    "title": "Отель",
                                    "text": "Описание",
                                    "retrieved_at": datetime.now(
                                        timezone.utc
                                    ).isoformat(),
                                }
                            ],
                        }
                        await graph.aupdate_state(config, state)
                    else:
                        restored = (await graph.aget_state(config)).values
                        self.assertEqual(restored["options"], state["options"])
                        self.assertEqual(restored["research"], state["research"])
                        self.assertFalse(
                            (
                                await graph.aget_state(
                                    {"configurable": {"thread_id": "other:trip"}}
                                )
                            ).values
                        )

    def test_five_distinct_hotels_and_goal_change_dependencies(self):
        rows = candidates()
        hotel = next(c for c in rows if c.role == "stays")
        rows += [
            hotel.model_copy(
                update={"id": f"hotel:extra{i}", "name": f"Дополнительный {i}"}
            )
            for i in range(4)
        ]
        options = compose(TRIP, rows, 1)
        self.assertEqual(len(options), 5)
        self.assertEqual(len({o.stay.id for o in options}), 5)
        self.assertEqual(
            apply_delta(TRIP, TripDelta(purpose="Работа"))[1], {"experience"}
        )

    async def test_clarification_keeps_existing_options(self):
        state = planned()
        state["calls"] = 0
        graph = build_graph(
            AsyncMock(
                return_value=SupervisorDecision(
                    action="clarify", question="Какой именно отель?"
                )
            ),
            AsyncMock(),
            InMemorySaver(),
        )
        result = await graph.ainvoke(
            state, {"configurable": {"thread_id": "ambiguous"}}
        )
        self.assertEqual(result["options"], state["options"])
        self.assertEqual(result["revision"], state["revision"])
        self.assertEqual(result["answer"], "Какой именно отель?")

    async def test_web_response_cites_only_observed_sources(self):
        state = planned()
        state["decision"] = {"action": "research"}
        state["research"] = {
            "sources": [
                {
                    "url": "https://example.com/hotel",
                    "text": "Есть бассейн",
                    "title": "Отель",
                }
            ]
        }
        state["answer"] = "Нет проверенного ответа."
        response = UserResponse(
            text="По описанию отеля есть бассейн.",
            source_urls=["https://example.com/hotel"],
        )
        model = ResponseModel(response)
        answer = await llm_presenter(model, load_prompt("response"))(state)
        self.assertIn("https://example.com/hotel", answer)
        response.source_urls = ["https://fabricated.example/"]
        self.assertEqual(
            await llm_presenter(model, load_prompt("response"))(state), state["answer"]
        )

    async def test_console_only_prints_user_text(self):
        import io
        from contextlib import redirect_stdout
        from travel_agent.__main__ import dialogue

        state = {
            "revision": 2,
            "answer": "Ответ о районе",
            "plan_answer": "Ваши варианты поездки",
            "options": [],
            "selected": None,
        }

        def handle(request):
            return httpx.Response(
                200,
                json=state
                if request.method == "GET"
                else {
                    "answer": "Расскажите о цели поездки.",
                    "internal": "DO_NOT_DISPLAY",
                },
            )

        output = io.StringIO()
        async with httpx.AsyncClient(
            base_url="http://local", transport=httpx.MockTransport(handle)
        ) as client:
            with (
                patch("builtins.input", side_effect=["Привет", "/show", "/quit"]),
                redirect_stdout(output),
            ):
                await dialogue(client, "trip")
        self.assertIn("Расскажите о цели", output.getvalue())
        self.assertIn("Ваши варианты поездки", output.getvalue())
        self.assertNotIn("DO_NOT_DISPLAY", output.getvalue())
        self.assertNotIn("revision", output.getvalue())

    def test_specialist_preferences_rank_before_cheapest_fallback(self):
        rows = candidates()
        stay = max((c for c in rows if c.role == "stays"), key=lambda c: c.price.amount)
        options = compose(TRIP, rows, 1, preferred_stays=[stay.id])
        self.assertEqual(options[0].stay.id, stay.id)
        self.assertEqual(len(options), 3)

    async def test_greeting_bypasses_trip_requirements_and_extra_model_calls(self):
        runner, present, lookup = AsyncMock(), AsyncMock(), AsyncMock()
        decision = SupervisorDecision(
            action="chat", reply="Привет! Я помогу спланировать поездку в Большой Сочи."
        )
        graph = build_graph(
            AsyncMock(return_value=decision), runner, InMemorySaver(), present, lookup
        )
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="Привет, кто ты такой?")], "calls": 0},
            {"configurable": {"thread_id": "hello"}},
        )
        self.assertEqual(result["answer"], decision.reply)
        self.assertEqual(result["messages"][-1].content, decision.reply)
        self.assertNotIn("origin", result["answer"])
        for dependency in (runner, present, lookup):
            dependency.assert_not_called()

    async def test_smalltalk_cannot_mutate_existing_trip(self):
        state = planned()
        state.update(
            calls=0, selected=state["options"][0]["id"], research={"sources": []}
        )
        decision = SupervisorDecision(
            action="chat",
            reply="Пожалуйста!",
            patch=TripDelta(adults=6),
            refresh=["transport"],
        )
        runner = AsyncMock()
        graph = build_graph(AsyncMock(return_value=decision), runner, InMemorySaver())
        result = await graph.ainvoke(state, {"configurable": {"thread_id": "thanks"}})
        for field in ("constraints", "revision", "options", "selected", "research"):
            self.assertEqual(result[field], state[field])
        runner.assert_not_called()

    async def test_greeting_then_planning_asks_human_question(self):
        decisions = AsyncMock(
            side_effect=[
                SupervisorDecision(action="chat", reply="Привет! Чем помочь?"),
                SupervisorDecision(
                    action="compose", patch=TripDelta(origin="Москва", adults=2)
                ),
            ]
        )
        runner = AsyncMock()
        graph = build_graph(decisions, runner, InMemorySaver())
        cfg = {"configurable": {"thread_id": "conversation"}}
        await graph.ainvoke(
            {"messages": [HumanMessage(content="Привет")], "calls": 0}, cfg
        )
        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="Хочу из Москвы, нас двое")],
                "calls": 0,
            },
            cfg,
        )
        self.assertEqual(result["constraints"]["origin"], "Москва")
        self.assertEqual(result["constraints"]["adults"], 2)
        self.assertIn("Какой отдых", result["answer"])
        self.assertEqual(len(result["messages"]), 4)
        runner.assert_not_called()
