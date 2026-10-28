import asyncio
import json
import logging
from datetime import datetime, timezone

import httpx
from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
)
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError
from langchain.agents.structured_output import ToolStrategy, StructuredOutputError
from langchain_core.exceptions import OutputParserException
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langgraph.errors import GraphRecursionError
from openai import APIError
from pydantic import ValidationError

from integrations.schemas.models import Coordinates
from travel_agent.schemas import (
    Candidate,
    Role,
    SpecialistResult,
    SpecialistSelection,
    TripConstraints,
)
from travel_agent.tools import build_tools


async def run_react(
    role: Role,
    trip: TripConstraints,
    revision: int,
    task: str,
    model: BaseChatModel,
    client: httpx.AsyncClient,
    env: dict[str, str],
    prompt: str,
    primary: str,
    fallback: str | None = None,
    center: Coordinates | None = None,
    deadline: int = 90,
    autonomous: bool = False,
    previous: list[Candidate] | None = None,
) -> SpecialistResult:
    sources = []
    evidence: dict[str, Candidate] = {c.id: c for c in previous or [] if autonomous and c.role == role and c.source.expires_at and c.source.expires_at > datetime.now(timezone.utc)}
    warnings: list[str] = []
    selected_ids: list[str] = []
    days, assumptions, gaps = [], [], []
    counts = {"tools": 0}
    tools = build_tools(
        role, trip, revision, client, env, evidence, warnings, counts, center, web_evidence=sources, autonomous=autonomous
    )
    by_name = {t.name: t for t in tools}

    try:
        async with asyncio.timeout(deadline):
            observations = [{'tool': 'saved_evidence', 'result': {'candidates': [c.model_dump(mode='json', exclude={'provider_details'}) for c in evidence.values()]}}] if evidence else []
            if not autonomous:
                observations = [
                    {"tool": primary, "result": await by_name[primary].ainvoke({})}
                ]
                primary_status = observations[0]['result'].get('status', 'schema_error')
                if primary_status not in ('ok', 'empty'):
                    warnings.append(f'{primary}:{primary_status}')
                if not evidence and fallback is not None:
                    observations.append(
                        {"tool": fallback, "result": await by_name[fallback].ainvoke({})}
                    )
                if role in ("transport", "stays") and not evidence and env.get("TAVILY_API_KEY"):
                    query = f"Авиабилеты {trip.origin} Сочи AER {trip.date_from or trip.start or trip.travel_month} {trip.date_to or trip.end or ''} Туту Aviasales расписание цены" if role == "transport" else f"Отели {trip.destination} {trip.hotel or ''} {trip.stay_start} {trip.stay_end} {trip.adults} взрослых Туту"
                    observations.append({"tool": "tavily_search", "result": await by_name["tavily_search"].ainvoke({
                        "query": query})})
            agent = create_agent(
                model=model,
                tools=tools,
                system_prompt=prompt,
                checkpointer=False,
                response_format=ToolStrategy(SpecialistSelection, handle_errors=True),
                middleware=[
                    ModelCallLimitMiddleware(run_limit=8, exit_behavior="error"),
                    ToolCallLimitMiddleware(run_limit=12 if autonomous else 6, exit_behavior="error"),
                ],
            )
            result = await agent.ainvoke(
                {
                    "messages": [
                        HumanMessage(
                            content=json.dumps(
                                {
                                    "mode": "autonomous" if autonomous else "staged",
                                    "task": task,
                                    "constraints": trip.model_dump(mode="json"),
                                    "observations": observations,
                                },
                                ensure_ascii=False,
                            )
                        )
                    ]
                },
                {"recursion_limit": 32},
            )
            selection = SpecialistSelection.model_validate(
                result.get("structured_response")
            )
            if any(ident not in evidence for ident in selection.source_ids):
                warnings.append("unverified_source_ids")
            elif not selection.source_ids and evidence:
                warnings.append("empty_selection")
            else:
                selected_ids = selection.source_ids
                evidence = {
                    **{ident: evidence[ident] for ident in selection.source_ids},
                    **evidence,
                }
            if all(ident in evidence for day in selection.days for ident in day.source_ids):
                days = selection.days
            else:
                warnings.append('unverified_day_source_ids')
            assumptions, gaps = selection.assumptions, selection.gaps
            if autonomous and not evidence:
                warnings.append('no_evidence')
            usage = [
                m.usage_metadata
                for m in result["messages"]
                if getattr(m, "usage_metadata", None)
            ]
            logging.getLogger(__name__).info(
                "role=%s revision=%s usage=%s", role, revision, usage
            )
    except (
        TimeoutError,
        GraphRecursionError,
        ModelCallLimitExceededError,
        ToolCallLimitExceededError,
    ) as exc:
        logging.getLogger(__name__).warning("role=%s outcome=agent_limit reason=%s tools=%s", role, type(exc).__name__, counts["tools"])
        warnings.append("agent_limit")
    except (APIError, OutputParserException, ValidationError, StructuredOutputError):
        warnings.append("llm_error")
    return SpecialistResult(
        role=role,
        revision=revision,
        status="partial" if warnings else ("ok" if evidence else "empty"),
        candidates=list(evidence.values()),
        warnings=list(dict.fromkeys(warnings)),
        tool_calls=counts["tools"], sources=list({source.url: source for source in sources}.values())[:20],
        selected_ids=selected_ids,
        days=days, assumptions=assumptions, gaps=gaps,
    )
