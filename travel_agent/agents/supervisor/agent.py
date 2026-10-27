import json
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.language_models import BaseChatModel
from langchain_core.exceptions import OutputParserException
from pydantic import ValidationError

from travel_agent.schemas import Candidate, SupervisorDecision
from travel_agent.state import TripState
from travel_agent.agents.supervisor.response import option_context


def llm_decider(model: BaseChatModel, prompt: str):
    structured = model.with_structured_output(
        SupervisorDecision, method="function_calling", strict=True
    )

    async def decide(state: TripState) -> SupervisorDecision:
        context = {
            "today": str(date.today()),
            "user_request": next((message.content for message in reversed(state.get("messages", [])) if message.type == "human"), ""),
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
            "results": state.get("results", {}),
            "research": state.get("research", {}),
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
                *state.get("messages", []),
                HumanMessage(content=json.dumps(context, ensure_ascii=False)),
            ]
        for attempt in range(2):
            try:
                decision = SupervisorDecision.model_validate(await structured.ainvoke(messages))
                if decision.action in ("transport", "stays", "experience") and not decision.task.strip():
                    raise OutputParserException("Delegation task must preserve the user request and its requirements")
                return decision
            except (ValidationError, OutputParserException) as exc:
                if attempt:
                    raise
                fields = [(e['loc'], e['type']) for e in exc.errors(include_input=False, include_url=False)] if isinstance(exc, ValidationError) else ['output_format']
                messages.append(HumanMessage(content='Исправь только формат SupervisorDecision по схеме, сохрани смысл последнего сообщения. Диапазон дат записывается в patch.date_from/date_to; не выдумывай точные даты. Ошибки полей: ' + json.dumps(fields)))
        raise OutputParserException('Supervisor structured output unavailable')

    return decide
