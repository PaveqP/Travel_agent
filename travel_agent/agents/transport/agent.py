import httpx
from langchain_core.language_models import BaseChatModel

from travel_agent.agents.react import run_react
from travel_agent.schemas import Candidate, SpecialistResult, TripConstraints


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
) -> SpecialistResult:
    return await run_react(
        "transport",
        trip,
        revision,
        task,
        model,
        client,
        env,
        prompt,
        primary="search_flights",
        fallback="cached_flights",
        deadline=deadline,
    )
