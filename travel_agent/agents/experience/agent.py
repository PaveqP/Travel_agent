import httpx
from langchain_core.language_models import BaseChatModel

from travel_agent.agents.react import run_react
from travel_agent.engine import usable
from travel_agent.schemas import Candidate, SpecialistResult, TripConstraints
from datetime import datetime, timezone


async def run(
    trip: TripConstraints,
    revision: int,
    task: str,
    previous: list[Candidate],
    *,
    model: BaseChatModel,
    client: httpx.AsyncClient,
    env: dict[str, str],
    prompt: str,
    deadline: int = 90,
    autonomous: bool = False,
) -> SpecialistResult:
    stays = [
        c
        for c in previous
        if c.role == "stays" and usable(c, trip, datetime.now(timezone.utc))
    ]
    chosen = min(stays, key=lambda c: c.price.amount, default=None)
    return await run_react(
        "experience",
        trip,
        revision,
        task,
        model,
        client,
        env,
        prompt,
        primary="search_places",
        fallback="geoapify_places",
        center=chosen.coordinates if chosen else None,
        deadline=deadline,
        autonomous=autonomous,
        previous=previous,
    )
