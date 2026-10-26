import json
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.language_models import BaseChatModel

from travel_agent.schemas import Candidate, SupervisorDecision
from travel_agent.state import TripState


def llm_decider(model: BaseChatModel, prompt: str):
    structured = model.with_structured_output(
        SupervisorDecision, method="function_calling"
    )

    async def decide(state: TripState) -> SupervisorDecision:
        context = {
            "today": str(date.today()),
            "phase": "delegate" if state.get("calls", 0) else "extract_request",
            "constraints": state.get("constraints", {}),
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
        return await structured.ainvoke(
            [
                SystemMessage(content=prompt),
                *state.get("messages", [])[-12:],
                HumanMessage(content=json.dumps(context, ensure_ascii=False)),
            ]
        )

    return decide
