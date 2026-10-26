from typing import Literal

import httpx
from langchain_core.tools import BaseTool, tool

from integrations.schemas.models import Coordinates
from travel_agent.schemas import Candidate, TripConstraints
from integrations.providers import travelpayouts, yandex_rasp


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
        """Search round-trip flights for the server's dates, origin and adult party."""
        return await mcp(
            "search_flights",
            "tutu",
            "search_avia",
            {
                "origin": trip.origin,
                "destination": "AER",
                "departure_date": str(trip.start),
                "return_date": str(trip.end),
                "adults": trip.adults,
                "page_size": 10,
            },
        )

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
    async def cached_flights(origin_iata: str) -> dict:
        """Read Travelpayouts cached fares for a known origin IATA; not live availability."""
        if len(origin_iata) != 3 or not origin_iata.isalpha():
            return {"status": "schema_error"}
        return await rest(
            "cached_flights",
            "travelpayouts",
            "TRAVELPAYOUTS_TOKEN",
            lambda: travelpayouts.prices(
                client,
                env.get("TRAVELPAYOUTS_TOKEN", ""),
                origin_iata.upper(),
                str(trip.start),
                str(trip.end),
            ),
        )

    return [
        search_flights,
        search_trains,
        transport_details,
        yandex_schedule,
        cached_flights,
    ]
