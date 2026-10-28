import asyncio
import json

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
)
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError
from langchain.agents.structured_output import ToolStrategy, StructuredOutputError
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage
from langgraph.errors import GraphRecursionError
from openai import APIError
from pydantic import ValidationError

from travel_agent.schemas import (
    Candidate,
    ResearchResult,
    SpecialistSelection,
    TripConstraints,
)
from travel_agent.tools import build_tools


async def research(state, *, models, client, env, prompt) -> ResearchResult:
    role = state["decision"]["research_role"]
    sources = []
    warnings = []
    candidates = {
        c.id: c
        for r in state.get("results", {}).values()
        for row in r.get("candidates", [])
        if (c := Candidate.model_validate(row)).role == role
    }
    ids = state["decision"].get("source_ids") or [state.get("selected_stay")]
    evidence = (
        {ident: candidates[ident] for ident in ids if ident in candidates}
        if role == "stays"
        else {}
    )
    tools = build_tools(
        role,
        TripConstraints.model_validate(state.get("constraints", {})),
        state.get("revision", 0),
        client,
        env,
        evidence,
        warnings,
        {"tools": 0},
        web_evidence=sources,
        autonomous=bool(state.get("autonomous")),
    )
    tools = [
        t
        for t in tools
        if t.name in ("tavily_search", "tavily_extract", "hotel_details")
    ]
    query = state["decision"].get("task", "")
    if not query.strip():
        return ResearchResult(role=role, warnings=["missing_query"])
    try:
        async with asyncio.timeout(70):
            observations = []
            if evidence:
                result = await next(
                    t for t in tools if t.name == "hotel_details"
                ).ainvoke({"source_id": next(iter(evidence))})
                observations.append({"tool": "hotel_details", "result": result})
            if env.get("TAVILY_API_KEY") or not sources:
                result = await next(
                    t for t in tools if t.name == "tavily_search"
                ).ainvoke({"query": query})
                observations.append({"tool": "tavily_search", "result": result})
            if sources:
                agent = create_agent(
                    model=models[role],
                    tools=tools,
                    system_prompt=prompt,
                    checkpointer=False,
                    response_format=ToolStrategy(
                        SpecialistSelection, handle_errors=False
                    ),
                    middleware=[
                        ModelCallLimitMiddleware(run_limit=3, exit_behavior="error"),
                        ToolCallLimitMiddleware(run_limit=2, exit_behavior="error"),
                    ],
                )
                await agent.ainvoke(
                    {
                        "messages": [
                            HumanMessage(
                                content=json.dumps(
                                    {
                                        "role": role,
                                        "task": query,
                                        "observations": observations,
                                    },
                                    ensure_ascii=False,
                                )
                            )
                        ]
                    },
                    {"recursion_limit": 12},
                )
    except (
        TimeoutError,
        GraphRecursionError,
        ModelCallLimitExceededError,
        ToolCallLimitExceededError,
    ):
        warnings.append("research_limit")
    except (APIError, OutputParserException, ValidationError, StructuredOutputError):
        warnings.append("llm_error")
    unique = {s.url: s for s in sources}
    return ResearchResult(
        role=role,
        sources=list(unique.values())[:20],
        warnings=list(dict.fromkeys(warnings)),
    )
