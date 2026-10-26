from typing import Annotated, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


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
    stage: str
    scenarios: list[dict]
    selected_scenario: str | None
    selected_transport: str | None
    selected_stay: str | None
    choices: list[dict]
    pending_check_in: str | None
    requested_choice: str | None
