import asyncio

import httpx
from langchain_core.tools import BaseTool, tool

from integrations.schemas.models import Coordinates
from travel_agent.engine import CENTERS
from travel_agent.schemas import Candidate, TripConstraints
from integrations.providers import geoapify, openmeteo, opentripmap, timepad


TOOL_NAMES = frozenset([
    'geocode_destination', 'search_places', 'route', 'geoapify_places', 'weather',
    'events', 'attractions', 'tavily_search', 'tavily_extract',
])


def build_tools(
    trip: TripConstraints,
    client: httpx.AsyncClient,
    env: dict[str, str],
    evidence: dict[str, Candidate],
    mcp,
    rest,
    center: Coordinates | None = None,
    *, autonomous: bool = False,
) -> list[BaseTool]:
    locations: dict[str, dict] = {}
    location_locks: dict[str, asyncio.Lock] = {}

    @tool
    async def geocode_destination(location: str | None = None) -> dict:
        """Resolve any Russian city or resort into coordinates, region and timezone. Review ambiguous matches."""
        name = (location or trip.destination).strip()
        async with location_locks.setdefault(name, asyncio.Lock()):
            if name not in locations:
                locations[name] = await rest('geocode_destination', 'openmeteo', None,
                    lambda: openmeteo.geocode(client, name))
            return locations[name]

    async def point(area: str | None = None, latitude: float | None = None, longitude: float | None = None) -> Coordinates | None:
        if latitude is not None and longitude is not None:
            return Coordinates(lat=latitude, lon=longitude)
        if not area and center:
            return center
        name = area or trip.destination
        if name in CENTERS:
            lat, lon = CENTERS[name]
            return Coordinates(lat=lat, lon=lon)
        result = await geocode_destination.ainvoke({'location': name})
        matches = result.get('locations', [])
        if not matches:
            return None
        return Coordinates(lat=matches[0]['latitude'], lon=matches[0]['longitude'])

    @tool
    async def search_places(query: str = 'Достопримечательности', area: str | None = None,
                            latitude: float | None = None, longitude: float | None = None,
                            radius: int = 10000) -> dict:
        """Search real places in any Russian destination; explicit coordinates may come from geocoding."""
        place = await point(area, latitude, longitude)
        if place is None:
            return {'status': 'missing_location', 'reason': 'Resolve a city, resort or nearby settlement first'}
        return await mcp('search_places', '2gis', 'search_places', {
            'query': query[:200], 'latitude': place.lat, 'longitude': place.lon,
            'radius': max(100, min(radius, 50000)), 'page_size': 10,
        })

    @tool
    async def route(source_id: str, origin_location: str | None = None) -> dict:
        """Read a route from the hotel or a resolved Russian location to an observed place."""
        candidate = evidence.get(source_id)
        start = await point(origin_location)
        if candidate is None or candidate.coordinates is None or start is None:
            return {'status': 'missing_location'}
        return await mcp('route', '2gis', 'build_route', {
            'points': [start.model_dump(), candidate.coordinates.model_dump()], 'transport': 'driving',
        })

    @tool
    async def geoapify_places(area: str | None = None) -> dict:
        """Read nearby sightseeing around a hotel, Russian city or resort."""
        place = await point(area)
        if place is None:
            return {'status': 'missing_location'}
        return await rest('geoapify_places', 'geoapify', 'GEOAPIFY_API_KEY',
            lambda: geoapify.places(client, env.get('GEOAPIFY_API_KEY', ''), place.lat, place.lon))

    @tool
    async def weather(area: str | None = None) -> dict:
        """Read the destination forecast in local time; dates outside its horizon stay unknown."""
        place = await point(area)
        if place is None:
            return {'status': 'missing_location'}
        return await rest('weather', 'openmeteo', None, lambda: openmeteo.forecast(client, place.lat, place.lon))

    @tool
    async def events(city: str | None = None) -> dict:
        """Read Timepad events in the requested Russian city and trip dates."""
        location = await geocode_destination.ainvoke({'location': city or trip.destination})
        matches = location.get('locations', [])
        timezone_name = matches[0].get('timezone') if matches else None
        return await rest('events', 'timepad', 'TIMEPAD_TOKEN', lambda: timepad.events(
            client, env.get('TIMEPAD_TOKEN', ''), str(trip.start), str(trip.end), city=city or trip.destination, timezone_name=timezone_name))

    @tool
    async def attractions(area: str | None = None) -> dict:
        """Read the attraction catalog near the hotel or any resolved Russian destination."""
        place = await point(area)
        if place is None:
            return {'status': 'missing_location'}
        return await rest('attractions', 'opentripmap', 'OPENTRIPMAP_API_KEY',
            lambda: opentripmap.places(client, env.get('OPENTRIPMAP_API_KEY', ''), place.lat, place.lon))

    return [geocode_destination, search_places, route, geoapify_places, weather, events, attractions]
