import json
import logging
from datetime import date, datetime, timezone
from functools import partial

from langchain_core.exceptions import OutputParserException
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from openai import APIError
from pydantic import ValidationError

from travel_agent.engine import apply_delta, compose, usable
from travel_agent.schemas import (
    Candidate,
    SpecialistResult,
    SupervisorDecision,
    TripConstraints,
)
from travel_agent.state import TripState


def all_candidates(state: TripState) -> list[Candidate]:
    return [
        Candidate.model_validate(c)
        for r in state.get("results", {}).values()
        for c in r.get("candidates", [])
    ]


async def supervise(state: TripState, decide) -> dict:
    if state.get("calls", 0) >= 7:
        return {
            "decision": {"action": "compose"},
            "answer": "Достигнут лимит делегаций; доступен частичный результат.",
        }
    try:
        decision = SupervisorDecision.model_validate(await decide(state))
        current = TripConstraints.model_validate(state.get("constraints", {}))
        revised, affected = (
            apply_delta(current, decision.patch)
            if not state.get("calls", 0)
            else (current, set())
        )
    except (ValidationError, OutputParserException, APIError, TimeoutError):
        if state.get("calls", 0):
            return {"decision": {"action": "compose"}, "status": "partial"}
        return {
            "decision": {"action": "clarify"},
            "status": "error",
            "options": [],
            "selected": None,
            "answer": "Не удалось обработать новое сообщение. Ограничения сохранены; повторите запрос.",
        }
    changed = revised != current
    if not state.get("calls", 0):
        affected.update(decision.refresh)
        now = datetime.now(timezone.utc)
        for role, result in state.get("results", {}).items():
            rows = [Candidate.model_validate(c) for c in result.get("candidates", [])]
            if rows and all(
                c.source.expires_at is None or c.source.expires_at <= now for c in rows
            ):
                affected.add(role)
    if (
        current.hotel != revised.hotel
        and revised.hotel
        and "stays" not in decision.refresh
        and any(
            candidate.role == "stays"
            and usable(candidate, revised, datetime.now(timezone.utc))
            for candidate in all_candidates(state)
        )
    ):
        affected.discard("stays")
    if "stays" in affected:
        affected.add("experience")
    results = {k: v for k, v in state.get("results", {}).items() if k not in affected}
    revision = state.get("revision", 0) + int(changed or bool(affected))
    action = decision.action
    answer = ""
    if action == "unsupported":
        answer = (
            "Полное планирование поддерживает только Большой Сочи и поездки взрослых."
        )
    elif revised.missing():
        action = "clarify"
        answer = decision.question or "Уточните: " + ", ".join(revised.missing())
    elif revised.start < date.today():
        action = "clarify"
        answer = "Укажите будущие даты поездки."
    elif action == "clarify":
        answer = decision.question or "Уточните параметры поездки."
    elif action == "answer":
        evidence = {c.id: c for c in all_candidates(state)}
        selected = [
            evidence[i].model_dump(mode="json")
            for i in decision.source_ids
            if i in evidence
        ]
        answer = (
            json.dumps(selected, ensure_ascii=False)
            if selected
            else "В сохранённых источниках нет подтверждённых данных для ответа."
        )
    else:
        missing = [r for r in ("transport", "stays", "experience") if r not in results]
        if action == "compose" and missing:
            action = missing[0]
        if action in results:
            action = missing[0] if missing else "compose"
        if action == "experience" and "stays" not in results:
            action = "stays"
        if action in ("transport", "stays", "experience"):
            fingerprint = f"{revision}:{action}"
            if fingerprint in state.get("attempts", []):
                action = "compose"
    update = {
        "constraints": revised.model_dump(mode="json"),
        "revision": revision,
        "results": results,
        "decision": {**decision.model_dump(mode="json"), "action": action},
        "calls": state.get("calls", 0) + 1,
        "answer": answer,
    }
    if action in ("clarify", "unsupported"):
        update["status"] = "needs_input" if action == "clarify" else "unsupported"
    if changed or affected or action in ("clarify", "unsupported"):
        update.update(options=[], selected=None)
    return update


async def specialist(state: TripState, run, config: RunnableConfig) -> dict:
    role = state["decision"]["action"]
    logging.getLogger(__name__).info(
        "thread=%s role=%s revision=%s",
        config.get("configurable", {}).get("thread_id"),
        role,
        state["revision"],
    )
    result = SpecialistResult.model_validate(
        await run(
            TripConstraints.model_validate(state["constraints"]),
            state["revision"],
            state["decision"].get("task", ""),
            [
                c
                for c in all_candidates(state)
                if role == "experience" and c.role == "stays"
            ],
        )
    )
    if (
        result.revision != state["revision"]
        or result.role != role
        or any(c.role != role for c in result.candidates)
    ):
        result = SpecialistResult(
            role=role,
            revision=state["revision"],
            status="partial",
            warnings=["stale_or_invalid_result"],
        )
    return {
        "results": {**state.get("results", {}), role: result.model_dump(mode="json")},
        "attempts": [*state.get("attempts", []), f"{state['revision']}:{role}"],
    }


def planning(state: TripState) -> dict:
    options = compose(
        TripConstraints.model_validate(state.get("constraints", {})),
        all_candidates(state),
        state.get("revision", 0),
    )
    complete = any(
        option.transport is not None and option.stay is not None for option in options
    )
    if complete:
        answer = "Найдены варианты транспорта и проживания. Полная стоимость и бронирование не подтверждены."
    elif options:
        answer = "Получен частичный план: не хватает проверенного транспорта или проживания. Можно повторить поиск недостающего компонента."
    else:
        answer = "Недостаточно проверенных предложений для сборки поездки. Ошибки источников доступны в results."
    return {
        "options": [o.model_dump(mode="json") for o in options],
        "answer": answer,
        "status": "ready" if complete else ("partial" if options else "unavailable"),
    }


def finish(state: TripState) -> dict:
    return {"messages": [AIMessage(content=state.get("answer", ""))]}


def build_graph(decide, run, checkpointer):
    workflow = StateGraph(TripState)
    workflow.add_node("supervisor", partial(supervise, decide=decide))
    if not isinstance(run, dict):
        original = run
        run = {
            role: partial(original, role)
            for role in ("transport", "stays", "experience")
        }
    for role in ("transport", "stays", "experience"):
        workflow.add_node(role, partial(specialist, run=run[role]))
    workflow.add_node("engine", planning)
    workflow.add_node("finish", finish)
    workflow.add_edge(START, "supervisor")
    workflow.add_conditional_edges(
        "supervisor",
        lambda s: s["decision"]["action"],
        {
            "clarify": "finish",
            "unsupported": "finish",
            "answer": "finish",
            "compose": "engine",
            "transport": "transport",
            "stays": "stays",
            "experience": "experience",
        },
    )
    for role in ("transport", "stays", "experience"):
        workflow.add_edge(role, "supervisor")
    workflow.add_edge("engine", "finish")
    workflow.add_edge("finish", END)
    return workflow.compile(checkpointer=checkpointer)
