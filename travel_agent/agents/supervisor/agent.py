import json
from datetime import date

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.language_models import BaseChatModel
from langchain_core.exceptions import OutputParserException
from pydantic import ValidationError

from travel_agent.schemas import Candidate, SupervisorDecision, TripDelta
from travel_agent.prompts import load_prompt
from travel_agent.state import TripState
from travel_agent.destinations import DESTINATION_GROUPS
from travel_agent.agents.supervisor.response import option_context


def llm_decider(model: BaseChatModel, prompt: str):
    structured = model.with_structured_output(
        SupervisorDecision, method="function_calling"
    )

    extraction = model.with_structured_output(TripDelta, method="function_calling")
    extraction_prompt = load_prompt("request")

    async def decide(state: TripState) -> SupervisorDecision:
        context = {
            "today": str(date.today()),
            "phase": "delegate" if state.get("calls", 0) else "extract_request",
            "constraints": state.get("constraints", {}),
            "options": option_context(state),
            "selected": state.get("selected"),
            "stage": state.get("stage", "scenarios"),
            "scenarios": state.get("scenarios", []),
            "selected_scenario": state.get("selected_scenario"),
            "selected_transport": state.get("selected_transport"),
            "selected_stay": state.get("selected_stay"),
            "choices": state.get("choices", []),
            "pending_check_in": state.get("pending_check_in"),
            "diagnostics": state.get("diagnostics", {}),
            "receipt": state.get("receipt", {}),
            "results": {
                r: {"status": v["status"], "warnings": v["warnings"]}
                for r, v in state.get("results", {}).items()
            },
            "source_ids": [
                {"id": c.id, "name": c.name}
                for c in [
                    Candidate.model_validate(c)
                    for r in state.get("results", {}).values()
                    for c in r.get("candidates", [])
                ]
            ],
        }
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=json.dumps(context, ensure_ascii=False)),
            *state.get("messages", [])[-12:],
        ]
        for attempt in range(2):
            try:
                decision = SupervisorDecision.model_validate(
                    await structured.ainvoke(messages)
                )
                if decision.action in (
                    "scenarios",
                    "clarify",
                    "compose",
                    "transport",
                    "stays",
                    "experience",
                ):
                    latest = next(
                        (
                            m
                            for m in reversed(state.get("messages", []))
                            if isinstance(m, HumanMessage)
                        ),
                        HumanMessage(content=""),
                    )
                    delta = TripDelta.model_validate(
                        await extraction.ainvoke(
                            [
                                SystemMessage(content=extraction_prompt),
                                HumanMessage(
                                    content=json.dumps(
                                        {
                                            "today": context["today"],
                                            "constraints": context["constraints"],
                                        },
                                        ensure_ascii=False,
                                    )
                                ),
                                latest,
                            ]
                        )
                    )
                    patch = {
                        **decision.patch.model_dump(
                            exclude_none=True, exclude={"clear"}
                        ),
                        **delta.model_dump(exclude_none=True, exclude={"clear"}),
                    }
                    cleared = list(
                        dict.fromkeys(
                            [
                                name
                                for name in decision.patch.clear
                                if getattr(delta, name) is None
                            ]
                            + delta.clear
                        )
                    )
                    for name in delta.clear:
                        patch.pop(name, None)
                    decision.patch = TripDelta.model_validate(
                        {**patch, "clear": cleared}
                    )
                return decision
            except (ValidationError, OutputParserException) as exc:
                if attempt:
                    raise
                fields = (
                    [
                        (e["loc"], e["type"])
                        for e in exc.errors(include_input=False, include_url=False)
                    ]
                    if isinstance(exc, ValidationError)
                    else ["output_format"]
                )
                messages.insert(
                    2,
                    HumanMessage(
                        content="Исправь только формат SupervisorDecision по схеме, сохрани смысл последнего сообщения. Диапазон дат записывается в patch.date_from/date_to; не выдумывай точные даты. Ошибки полей: "
                        + json.dumps(fields)
                    ),
                )
        raise OutputParserException("Supervisor structured output unavailable")

    return decide


def llm_planner(model: BaseChatModel, prompt: str):
    from travel_agent.schemas import TurnPlan, RepairPlan

    structured = model.with_structured_output(TurnPlan, method='function_calling')
    extraction = model.with_structured_output(TripDelta, method='function_calling')
    extraction_prompt = load_prompt('request')
    repair_model = model.with_structured_output(RepairPlan, method='function_calling')

    async def plan(state: TripState) -> TurnPlan:
        options = option_context(state)
        context = {
            'today': str(date.today()), 'constraints': state.get('constraints', {}),
            'phase': 'repair' if state.get('repair_decision') else 'user_turn',
            'feedback': state.get('feedback', []), 'options': options[:5],
            'selected': state.get('selected'), 'focus': state.get('focus'),
            'scenarios': state.get('scenarios', []), 'receipt': state.get('receipt', {}),
            'destination_ideas': DESTINATION_GROUPS if state.get('constraints', {}).get('destination', 'Россия') == 'Россия' else {},
            'results': {role: {'status': row['status'], 'warnings': row.get('warnings', []),
                'candidates': [{'id': c['id'], 'name': c['name'], 'start': c.get('start'), 'end': c.get('end'), 'area': c.get('area')} for c in row.get('candidates', [])[:12]]}
                for role, row in state.get('results', {}).items()},
        }
        messages = [SystemMessage(content=prompt), HumanMessage(content=json.dumps(context, ensure_ascii=False)), *[AIMessage(content=m.content[:500]) if isinstance(m, AIMessage) and isinstance(m.content, str) else m for m in state.get('messages', [])[-6:]]]
        if state.get('repair_decision'):
            repair = RepairPlan.model_validate(await repair_model.ainvoke(messages))
            return TurnPlan(action='plan', tasks=repair.tasks, reply=repair.reply)
        for attempt in range(2):
            try:
                decision = TurnPlan.model_validate(await structured.ainvoke(messages))
                break
            except (ValidationError, OutputParserException) as exc:
                if attempt:
                    raise
                errors = [(e['loc'], e['type']) for e in exc.errors(include_input=False, include_url=False)] if isinstance(exc, ValidationError) else ['output_format']
                messages.insert(1, HumanMessage(content=json.dumps({'validation_errors': errors, 'patch_extracted_separately': True})))
        if not state.get('repair_decision') and (decision.action in ('plan', 'clarify') or decision.action == 'select' and decision.patch.model_dump(exclude_none=True, exclude={'clear'})):
            extraction_messages = [SystemMessage(content=extraction_prompt), HumanMessage(content=json.dumps({
                'today': context['today'], 'constraints': context['constraints'],
                'proposed_patch': decision.patch.model_dump(mode='json', exclude_none=True),
            }, ensure_ascii=False)), *[m for m in state.get('messages', []) if isinstance(m, HumanMessage)][-6:]]
            for attempt in range(2):
                try:
                    delta = TripDelta.model_validate(await extraction.ainvoke(extraction_messages))
                    break
                except (ValidationError, OutputParserException) as exc:
                    if attempt:
                        raise
                    errors = [(e['loc'], e['type']) for e in exc.errors(include_input=False, include_url=False)] if isinstance(exc, ValidationError) else ['output_format']
                    extraction_messages.insert(1, HumanMessage(content=json.dumps({'validation_errors': errors})))
            patch = {**decision.patch.model_dump(exclude_none=True, exclude={'clear'}), **delta.model_dump(exclude_none=True, exclude={'clear'})}
            cleared = list(dict.fromkeys([name for name in decision.patch.clear if getattr(delta, name) is None] + delta.clear))
            for name in cleared:
                patch.pop(name, None)
            decision.patch = TripDelta(**patch, clear=cleared)
        return decision

    return plan
