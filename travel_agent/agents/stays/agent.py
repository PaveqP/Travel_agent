import httpx
from langchain_core.language_models import BaseChatModel

from travel_agent.agents.react import run_react
from travel_agent.schemas import Candidate, SourceObservation, SpecialistResult, TripConstraints


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
    observations: list[SourceObservation] | None = None,
) -> SpecialistResult:
    return await run_react(
        "stays",
        trip,
        revision,
        task,
        model,
        client,
        env,
        prompt,
        deadline=deadline,
        observations=observations,
        previous=previous,
    )
