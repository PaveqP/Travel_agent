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
