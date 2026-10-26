import asyncio
from datetime import date, datetime, timezone
from typing import Literal

import httpx
from langchain_core.tools import BaseTool, tool

from integrations.schemas.models import Coordinates
from travel_agent.schemas import Candidate, TripConstraints
from integrations.providers import travelpayouts, yandex_rasp
from travel_agent.engine import search_dates, transport_matches


TOOL_NAMES = frozenset(
    [
        "search_flights",
        "search_trains",
        "transport_details",
        "yandex_schedule",
        "cached_flights",
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
    @tool
    async def search_flights() -> dict:
        """Search the user's dates, then bounded nearby dates; explicit windows sample up to six date pairs."""
        pairs = search_dates(trip)[:6]
        if not pairs:
            return {"status": "empty", "candidates": []}
        semaphore = asyncio.Semaphore(2)
        searched = []

        async def query(start: date, end: date) -> dict:
            async with semaphore:
                searched.append({"start": str(start), "end": str(end)})
                try:
                    async with asyncio.timeout(25):
                        return await mcp("search_flights", "tutu", "search_avia", {
                            "origin": trip.origin, "destination": "AER", "departure_date": str(start),
                            "return_date": str(end), "adults": trip.adults, "page_size": 10,
                            "sort": "price_asc", "direct_only": trip.direct_only})
                except TimeoutError:
                    return {"status": "timeout"}

        first = {"status": "empty"}
        try:
            async with asyncio.timeout(55):
                first = await query(*pairs[0])
                fresh = any(transport_matches(c, trip, datetime.now(timezone.utc)) for c in evidence.values())
                if first["status"] in ("ok", "empty", "no_availability") and (not fresh or trip.date_from and trip.date_to):
                    await asyncio.gather(*(query(start, end) for start, end in pairs[1:]))
        except TimeoutError:
            first = {"status": "timeout"}
        return {"status": "ok" if evidence else first["status"],
                "candidates": [c.model_dump(mode="json") for c in list(evidence.values())[:20]],
                "searched_dates": searched, "exhaustive": False, "search_limit": 6}

    @tool
    async def search_trains(mode: Literal["rail", "etrain"] = "rail") -> dict:
        """Search outbound rail schedules; not a complete round-trip quote."""
        return await mcp(
            "search_trains",
            "tutu",
            "search_" + mode,
            {
                "origin": trip.origin,
                "destination": "Сочи",
                "departure_date": str(trip.start),
                "page_size": 10,
            },
        )

    @tool
    async def transport_details(source_id: str) -> dict:
        """Read flight details only for a flight obtained in this delegation."""
        return await mcp(
            "transport_details",
            "tutu",
            "get_offer_details",
            {"product_type": "avia", "offer_id": source_id.removeprefix("avia:")},
        )

    @tool
    async def yandex_schedule(
        origin: Literal["Сочи", "Адлер", "Роза Хутор"],
        destination: Literal["Сочи", "Адлер", "Роза Хутор"],
    ) -> dict:
        """Read suburban schedules between verified station IDs; no seat guarantee."""
        stations = {"Сочи": "s9613034", "Адлер": "s9613054", "Роза Хутор": "s9812791"}
        return await rest(
            "yandex_schedule",
            "yandex_rasp",
            "YANDEX_RASP_API_KEY",
            lambda: yandex_rasp.schedule(
                client,
                env.get("YANDEX_RASP_API_KEY", ""),
                stations[origin],
                stations[destination],
                str(trip.start),
            ),
        )

    @tool
    async def cached_flights(origin_iata: str | None = None) -> dict:
        """Read Travelpayouts cached fares for a known origin IATA; not live availability."""
        if origin_iata is None:
            known = {"москва": "MOW", "санкт-петербург": "LED", "санкт петербург": "LED", "петербург": "LED"}
            value = trip.origin or ""
            origin_iata = value.upper() if len(value) == 3 and value.isascii() else known.get(value.casefold())
        if not origin_iata or len(origin_iata) != 3 or not origin_iata.isascii() or not origin_iata.isalpha():
            return {"status": "schema_error"}
        pairs = search_dates(trip)
        if not pairs:
            return {"status": "empty"}
        start, end = pairs[0]
        broad = bool(trip.date_from and trip.date_to or not trip.start and trip.travel_month)
        return await rest(
            "cached_flights",
            "travelpayouts",
            "TRAVELPAYOUTS_TOKEN",
            lambda: travelpayouts.prices(
                client,
                env.get("TRAVELPAYOUTS_TOKEN", ""),
                origin_iata.upper(),
                start.strftime("%Y-%m") if broad else str(start),
                end.strftime("%Y-%m") if broad else str(end),
            ),
        )

    return [
        search_flights,
        search_trains,
        transport_details,
        yandex_schedule,
        cached_flights,
    ]
