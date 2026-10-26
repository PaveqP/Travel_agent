import asyncio
import json
import logging

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
) -> SpecialistResult:
    evidence: dict[str, Candidate] = {}
    warnings: list[str] = []
    counts = {"tools": 0}
    tools = build_tools(
        role, trip, revision, client, env, evidence, warnings, counts, center
    )
    by_name = {t.name: t for t in tools}
    try:
        async with asyncio.timeout(deadline):
            observations = [
                {"tool": primary, "result": await by_name[primary].ainvoke({})}
            ]
            if not evidence and fallback is not None:
                observations.append(
                    {"tool": fallback, "result": await by_name[fallback].ainvoke({})}
                )
            agent = create_agent(
                model=model,
                tools=tools,
                system_prompt=prompt,
                response_format=ToolStrategy(SpecialistSelection, handle_errors=False),
                middleware=[
                    ModelCallLimitMiddleware(run_limit=4, exit_behavior="error"),
                    ToolCallLimitMiddleware(run_limit=6, exit_behavior="error"),
                ],
            )
            result = await agent.ainvoke(
                {
                    "messages": [
                        HumanMessage(
                            content=json.dumps(
                                {
                                    "task": task,
                                    "constraints": trip.model_dump(mode="json"),
                                    "observations": observations,
                                },
                                ensure_ascii=False,
                            )
                        )
                    ]
                },
                {"recursion_limit": 20},
            )
            selection = SpecialistSelection.model_validate(
                result.get("structured_response")
            )
            if any(ident not in evidence for ident in selection.source_ids):
                warnings.append("unverified_source_ids")
            elif not selection.source_ids and evidence:
                warnings.append("empty_selection")
            else:
                evidence = {
                    **{ident: evidence[ident] for ident in selection.source_ids},
                    **evidence,
                }
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
    ):
        warnings.append("agent_limit")
    except (APIError, OutputParserException, ValidationError, StructuredOutputError):
        warnings.append("llm_error")
    return SpecialistResult(
        role=role,
        revision=revision,
        status="partial" if warnings else ("ok" if evidence else "empty"),
        candidates=list(evidence.values()),
        warnings=list(dict.fromkeys(warnings)),
        tool_calls=counts["tools"],
    )
