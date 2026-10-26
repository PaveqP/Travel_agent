import asyncio
import json
import logging
from pathlib import Path

import httpx
from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.exceptions import OutputParserException
from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError
from openai import APIError
from pydantic import ValidationError

from travel_agent.config import Settings
from travel_agent.schemas import Candidate, Role, SpecialistResult, SpecialistSelection, TripConstraints
from travel_agent.tools import build_tools


def read_prompts() -> dict[str, str]:
    return {name: (Path(__file__).parent / 'prompts' / (name+'.md')).read_text(encoding='utf-8')
            for name in ('supervisor', 'transport', 'stays', 'experience')}


def create_model(config: Settings, client: httpx.AsyncClient) -> ChatOpenAI:
    return ChatOpenAI(model=config.model, api_key=config.token.get_secret_value(), base_url=config.base_url,
                      http_async_client=client, max_retries=0, timeout=45, max_tokens=1800,
                      use_responses_api=False)


async def run_specialist(role: Role, trip: TripConstraints, revision: int, task: str,
                         model, client: httpx.AsyncClient, env: dict[str, str], prompts: dict[str, str],
                         previous: list[Candidate], deadline: int = 90) -> SpecialistResult:
    evidence: dict[str, Candidate] = {}
    warnings: list[str] = []
    counts = {'tools': 0}
    center = next((c.coordinates for c in previous if c.role == 'stays' and c.coordinates), None)
    tools = build_tools(role, trip, revision, client, env, evidence, warnings, counts, center)
    agent = create_agent(model=model, tools=tools, system_prompt=prompts[role], middleware=[
        ModelCallLimitMiddleware(run_limit=6, exit_behavior='error'),
        ToolCallLimitMiddleware(run_limit=8, exit_behavior='error'),
    ])
    try:
        async with asyncio.timeout(deadline):
            result = await agent.ainvoke({'messages': [HumanMessage(content=json.dumps({
                'task': task, 'constraints': trip.model_dump(mode='json')}, ensure_ascii=False))]}, {'recursion_limit': 24})
            usage = [m.usage_metadata for m in result['messages'] if getattr(m, 'usage_metadata', None)]
            logging.getLogger(__name__).info('role=%s revision=%s usage=%s', role, revision, usage)
            if evidence:
                selection = await model.with_structured_output(SpecialistSelection, method='json_schema').ainvoke([
                    SystemMessage(content=prompts[role]),
                    HumanMessage(content=json.dumps({'select_source_ids': [c.model_dump(mode='json', include={'id', 'name', 'price', 'area'}) for c in evidence.values()],
                                                   'task': task}, ensure_ascii=False))])
                selection = SpecialistSelection.model_validate(selection)
                if any(ident not in evidence for ident in selection.source_ids):
                    warnings.append('unverified_source_ids')
                elif not selection.source_ids:
                    warnings.append('empty_selection')
                else:
                    evidence = {**{ident: evidence[ident] for ident in selection.source_ids}, **evidence}
    except (TimeoutError, GraphRecursionError, ModelCallLimitExceededError, ToolCallLimitExceededError):
        warnings.append('agent_limit')
    except (APIError, OutputParserException, ValidationError):
        warnings.append('llm_error')
    return SpecialistResult(role=role, revision=revision,
                            status='partial' if warnings else ('ok' if evidence else 'empty'),
                            candidates=list(evidence.values()), warnings=warnings, tool_calls=counts['tools'])
