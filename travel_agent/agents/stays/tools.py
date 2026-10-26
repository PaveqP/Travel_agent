import httpx
from langchain_core.tools import BaseTool, tool

from integrations.schemas.models import Coordinates
from travel_agent.schemas import Candidate, TripConstraints


TOOL_NAMES = frozenset(
    ["search_hotels", "hotel_details", "tavily_search", "tavily_extract"]
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
    async def search_hotels() -> dict:
        """Search hotels for the server's area, dates and adult party."""
        return await mcp(
            "search_hotels",
            "tutu",
            "search_hotels",
            {
                "city_name": trip.destination,
                "check_in": str(trip.stay_start),
                "check_out": str(trip.stay_end),
                "adults": trip.adults,
                "page_size": 10,
            },
        )

    @tool
    async def hotel_details(source_id: str) -> dict:
        """Read hotel details only for a hotel obtained in this delegation."""
        return await mcp(
            "hotel_details",
            "tutu",
            "get_offer_details",
            {
                "product_type": "hotels",
                "hotel_id": source_id.removeprefix("hotel:"),
                "check_in": str(trip.stay_start),
                "check_out": str(trip.stay_end),
                "adults": trip.adults,
                "view": "rules",
            },
        )

    return [search_hotels, hotel_details]
