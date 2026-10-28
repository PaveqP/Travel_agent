from typing import Annotated, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from travel_agent.schemas import Stage


def merge_task_results(previous: dict, update: dict) -> dict:
    return {**previous, **update}


class TripState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    constraints: dict
    revision: int
    results: dict
    options: list[dict]
    decision: dict
    calls: int
    attempts: list[str]
    status: str
    answer: str
    bookings: dict
    selected: str | None

    research: dict
    plan_answer: str
    diagnostics: dict
    stage: Stage
    scenarios: list[dict]
    selected_scenario: str | None
    selected_transport: str | None
    selected_stay: str | None
    choices: list[dict]
    pending_check_in: str | None
    requested_choice: str | None
    receipt: dict
    profile_update: list[str] | None
    cards: list[dict]
    notice: str

    focus: str | None
    autonomous: bool
    tasks: list[dict]
    task_results: Annotated[dict, merge_task_results]
    search_round: int
    feedback: list[dict]
    route: str
    repair_decision: bool
    preserved_roles: list[str]
    plan_review: dict
