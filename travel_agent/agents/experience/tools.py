from collections.abc import Awaitable, Callable
import httpx
from langchain_core.tools import BaseTool, tool

from integrations.schemas.models import Coordinates
from travel_agent.engine import CENTERS
from travel_agent.schemas import Area, SourceObservation, TripConstraints
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
    evidence: dict[str, SourceObservation],
    mcp: Callable[[str, str, str, dict], Awaitable[dict]],
    rest: Callable[..., Awaitable[dict]],
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
                "query": query,
                "latitude": search_lat,
                "longitude": search_lon,
                "radius": 7000,
                "page_size": 10,
            },
        )

    @tool
    async def route(source_id: str) -> dict:
        """Get a driving route from the hotel to a place found in this delegation."""
        target = None
        for observation in evidence.values():
            if observation.provider == '2gis' and isinstance(observation.data, dict):
                for row in observation.data.get('items', []):
                    if row.get('id') == source_id.removeprefix('2gis:'):
                        target = row.get('coordinates')
        if target is None:
            return {"status": "forbidden"}
        return await mcp("route", "2gis", "build_route", {
            "points": [{"lat": lat, "lon": lon}, target], "transport": "driving"})

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
