from travel_agent.agents.react import run_react
from travel_agent.schemas import Candidate, ResearchResult, SourceObservation, TripConstraints, WebEvidence


async def research(state, *, models, client, env, prompt) -> ResearchResult:
    role = state["decision"]["research_role"]
    stored = state.get("results", {}).get(role, {})
    query = state["decision"].get("task", "")
    if not query.strip():
        return ResearchResult(role=role, warnings=["missing_query"])
    observed = [*stored.get("observations", []), *state.get("research", {}).get("observations", [])]
    observations = list({row["id"]: SourceObservation.model_validate(row) for row in observed if row["role"] == role}.values())
    result = await run_react(role, TripConstraints.model_validate(state.get("constraints", {})), state.get("revision", 0),
        query, models[role], client, env, prompt,
        observations=observations,
        previous=[Candidate.model_validate(row) for row in stored.get("candidates", [])], deadline=90)
    sources = []
    for observation in result.observations:
        if observation.provider == "tavily" and isinstance(observation.data, dict):
            for row in observation.data.get("results", []):
                if row.get("url"):
                    sources.append(WebEvidence(url=row["url"], title=row.get("title", ""), text=row.get("content") or row.get("raw_content") or "", retrieved_at=observation.source.retrieved_at))
    return ResearchResult(role=role, sources=sources, observations=result.observations, candidates=result.candidates,
        explanation=result.explanation, warnings=result.warnings)
