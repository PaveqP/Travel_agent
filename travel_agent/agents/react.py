import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from decimal import Decimal

import httpx
from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware, wrap_model_call
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError
from langchain.agents.structured_output import ToolStrategy, StructuredOutputError
from langchain_core.exceptions import OutputParserException
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langgraph.errors import GraphRecursionError
from openai import APIError
from pydantic import JsonValue, ValidationError

from integrations.schemas.models import Coordinates
from travel_agent.schemas import Candidate, FieldReference, Role, SourceObservation, SpecialistResult, SpecialistSelection, TripConstraints
from travel_agent.tools import build_tools


@wrap_model_call
async def enforce_tool_schema(request: ModelRequest, handler: Callable[[ModelRequest], Awaitable[ModelResponse]]) -> ModelResponse:
    return await handler(request.override(model_settings={**request.model_settings, "strict": True}))


def referenced_value(reference: FieldReference, observations: dict[str, SourceObservation]) -> JsonValue:
    observation = observations.get(reference.observation_id)
    if observation is None:
        raise ValueError("Unknown response ID")
    value = observation.model_dump(mode="json")
    try:
        for key in reference.path:
            value = value[key]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("Unknown source field") from exc
    return value


def validate_candidate(candidate: Candidate, role: Role, observations: dict[str, SourceObservation]) -> None:
    references = [*candidate.field_refs.values(), *(part.reference for part in candidate.price_parts)]
    if candidate.role != role or not references:
        raise ValueError("Card needs its role and exact source references")
    sources = [observations[ref.observation_id] for ref in references if ref.observation_id in observations]
    if not sources or any(s.role != role for s in sources) or candidate.source not in [s.source for s in sources]:
        raise ValueError("Unverified provenance")
    required = [key for key in ("start", "end", "departure_at", "arrival_at", "return_departure_at", "duration_minutes", "transfers", "adults", "url", "service_class") if getattr(candidate, key) is not None]
    required += ["children_ages"] if candidate.children_ages else []
    required += ["coordinates.lat", "coordinates.lon"] if candidate.coordinates else []
    required += ["facts." + key for key in candidate.facts]
    quote_sources = [row for row in sources if row.source.evidence == "live" and row.status == "ok"]
    if quote_sources and candidate.source.expires_at and any(row.source.expires_at and row.source.expires_at < candidate.source.expires_at for row in quote_sources):
        raise ValueError("Card freshness exceeds a referenced quote")
    missing = [field for field in required if field not in candidate.field_refs]
    if missing:
        raise ValueError("Missing field references: " + ", ".join(missing))
    for field, reference in candidate.field_refs.items():
        actual = referenced_value(reference, observations)
        if (field in ("service_class", "start", "end", "departure_at", "arrival_at", "return_departure_at", "duration_minutes", "transfers", "url") or field.startswith(("facts.", "coordinates."))) and (not reference.path or reference.path[0] != "data"):
            raise ValueError("Offer conditions must come from provider data")
        expected = candidate.model_dump(mode="json")
        try:
            for key in field.split("."):
                expected = expected[key]
        except (KeyError, TypeError) as exc:
            raise ValueError("Unknown card field: " + field) from exc
        if field in ("start", "end", "scheduled_date") and isinstance(actual, str):
            actual = actual[:10]
        if field in ("departure_at", "arrival_at", "return_departure_at"):
            if datetime.fromisoformat(str(actual)) != datetime.fromisoformat(str(expected)):
                raise ValueError("Unverified date: " + field)
        elif field == "price":
            if candidate.price is None or not isinstance(actual, dict) or Decimal(str(actual.get("amount"))) != candidate.price.amount or actual.get("currency") != candidate.price.currency:
                raise ValueError("Unverified price")
        elif actual != expected:
            raise ValueError("Unverified field: " + field)
    if candidate.price is not None:
        refs = [part.reference for part in candidate.price_parts] or [candidate.field_refs.get("price")]
        if refs == [None]:
            raise ValueError("Price requires a returned quote or referenced components")
        for reference in refs:
            if not reference.path or reference.path[0] != "data":
                raise ValueError("Prices must come from provider responses")
        if candidate.price_parts:
            for part in candidate.price_parts:
                raw = referenced_value(part.reference, observations)
                if not isinstance(raw, dict) or Decimal(str(raw.get("amount"))) != part.amount or raw.get("currency") != part.currency or part.currency != candidate.price.currency:
                    raise ValueError("Unverified price component")
            if sum((part.amount for part in candidate.price_parts), Decimal(0)) != candidate.price.amount:
                raise ValueError("Price components do not add up")
        aliases = {"party_total": {"party"}, "stay_total": {"room_stay"}, "per_seat": {"ticket", "person"}, "per_person": {"person"}}
        for reference in refs:
            observation = observations[reference.observation_id]
            data = observation.data
            parent = referenced_value(reference.model_copy(update={"path": reference.path[:-1]}), observations)
            basis = parent.get("price_basis") if isinstance(parent, dict) else None
            if "price_party" in reference.path:
                basis = "party_total"
            elif basis is None and isinstance(data, dict):
                basis = data.get("meta", {}).get("pricing", {}).get("basis")
            if basis in aliases and candidate.price.basis not in aliases[basis]:
                raise ValueError("Price basis disagrees with source")


async def run_react(
    role: Role, trip: TripConstraints, revision: int, task: str, model: BaseChatModel,
    client: httpx.AsyncClient, env: dict[str, str], prompt: str,
    center: Coordinates | None = None, deadline: int = 90,
    observations: list[SourceObservation] | None = None, previous: list[Candidate] | None = None,
) -> SpecialistResult:
    evidence = {row.id: row for row in observations or []}
    cards = {c.id: c for c in previous or [] if c.role == role}
    warnings: list[str] = []
    selected_ids: list[str] = []
    explanation = ""
    counts = {"tools": 0}
    tools = build_tools(role, trip, revision, client, env, evidence, warnings, counts, center)

    @tool
    async def present_offers(candidates: list[Candidate], explanation: str = "") -> dict:
        """Publish cards referencing exact fields of observed responses; validation errors can be corrected without repeating searches."""
        try:
            for candidate in candidates:
                validate_candidate(candidate, role, evidence)
        except (ValueError, TypeError, ArithmeticError) as exc:
            return {"status": "invalid_evidence", "reason": str(exc)}
        cards.update((candidate.id, candidate) for candidate in candidates)
        return {"status": "ok", "source_ids": [candidate.id for candidate in candidates], "explanation": explanation}

    try:
        async with asyncio.timeout(deadline):
            agent = create_agent(model=model, tools=[*tools, present_offers], system_prompt=prompt, checkpointer=False,
                response_format=ToolStrategy(SpecialistSelection, handle_errors=True),
                middleware=[enforce_tool_schema, ModelCallLimitMiddleware(run_limit=8, exit_behavior="error"), ToolCallLimitMiddleware(run_limit=10, exit_behavior="error")])
            result = await agent.ainvoke({"messages": [HumanMessage(content=json.dumps({
                "task": task, "constraints": trip.model_dump(mode="json"), "observations": [row.model_dump(mode="json") for row in evidence.values()],
                "previous_cards": [c.model_dump(mode="json") for c in cards.values()],
            }, ensure_ascii=False))]}, {"recursion_limit": 32})
            selection = SpecialistSelection.model_validate(result.get("structured_response"))
            if any(ident not in cards for ident in selection.source_ids):
                warnings.append("unverified_source_ids")
            else:
                selected_ids = selection.source_ids
            explanation = selection.explanation
            usage = [m.usage_metadata for m in result["messages"] if getattr(m, "usage_metadata", None)]
            logging.getLogger(__name__).info("role=%s revision=%s usage=%s", role, revision, usage)
    except (TimeoutError, GraphRecursionError, ModelCallLimitExceededError, ToolCallLimitExceededError):
        warnings.append("agent_limit")
    except APIError as exc:
        logging.getLogger(__name__).warning("role=%s revision=%s llm_error=%s status=%s", role, revision, type(exc).__name__, getattr(exc, "status_code", None))
        warnings.append("llm:payment_required" if getattr(exc, "status_code", None) == 402 else "llm_error")
    except (OutputParserException, ValidationError, StructuredOutputError):
        warnings.append("llm_error")
    return SpecialistResult(role=role, revision=revision, status="partial" if warnings else "ok" if cards or evidence else "empty",
        candidates=list(cards.values()), observations=list(evidence.values()), warnings=list(dict.fromkeys(warnings)),
        tool_calls=counts["tools"], selected_ids=selected_ids, explanation=explanation)
