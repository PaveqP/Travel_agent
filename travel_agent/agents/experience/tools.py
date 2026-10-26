import httpx
from langchain_core.tools import BaseTool, tool

from integrations.schemas.models import Coordinates
from travel_agent.engine import CENTERS
from travel_agent.schemas import Area, Candidate, TripConstraints
from integrations.providers import geoapify, openmeteo, opentripmap, timepad


TOOL_NAMES = frozenset(
    [
        "search_places",
        "route",
        "geoapify_places",
        "weather",
        "events",
        "attractions",
        "tavily_search",
        "tavily_extract",
    ]
)


def build_tools(
    trip: TripConstraints,
    client: httpx.AsyncClient,
    env: dict[str, str],
    evidence: dict[str, Candidate],
    mcp,
    rest,
    center: Coordinates | None = None,
) -> list[BaseTool]:
    lat, lon = (center.lat, center.lon) if center else CENTERS[trip.destination]

    @tool
    async def search_places(
        query: str = "Достопримечательности", area: Area | None = None
    ) -> dict:
        """Search places around the server-selected hotel or destination."""
        search_lat, search_lon = CENTERS[area] if area else (lat, lon)
        return await mcp(
            "search_places",
            "2gis",
            "search_places",
            {
                "query": query[:200],
                "latitude": search_lat,
                "longitude": search_lon,
                "radius": 7000,
                "page_size": 10,
            },
        )

    @tool
    async def route(source_id: str) -> dict:
        """Get a driving route from the hotel to a place found in this delegation."""
        candidate = evidence.get(source_id)
        if candidate is None or candidate.coordinates is None:
            return {"status": "forbidden"}
        return await mcp(
            "route",
            "2gis",
            "build_route",
            {
                "points": [
                    {"lat": lat, "lon": lon},
                    candidate.coordinates.model_dump(),
                ],
                "transport": "driving",
            },
        )

    @tool
    async def geoapify_places() -> dict:
        """Search nearby sightseeing catalog with Geoapify."""
        return await rest(
            "geoapify_places",
            "geoapify",
            "GEOAPIFY_API_KEY",
            lambda: geoapify.places(client, env.get("GEOAPIFY_API_KEY", ""), lat, lon),
        )

    @tool
    async def weather() -> dict:
        """Get Open-Meteo forecast; dates outside its horizon remain unknown."""
        return await rest(
            "weather", "openmeteo", None, lambda: openmeteo.forecast(client, lat, lon)
        )

    @tool
    async def events() -> dict:
        """Search Timepad events within trip dates."""
        return await rest(
            "events",
            "timepad",
            "TIMEPAD_TOKEN",
            lambda: timepad.events(
                client, env.get("TIMEPAD_TOKEN", ""), str(trip.start), str(trip.end)
            ),
        )

    @tool
    async def attractions() -> dict:
        """Search nearby OpenTripMap catalog."""
        return await rest(
            "attractions",
            "opentripmap",
            "OPENTRIPMAP_API_KEY",
            lambda: opentripmap.places(
                client, env.get("OPENTRIPMAP_API_KEY", ""), lat, lon
            ),
        )

    return [search_places, route, geoapify_places, weather, events, attractions]
