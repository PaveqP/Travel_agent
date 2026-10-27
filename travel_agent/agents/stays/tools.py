from collections.abc import Awaitable, Callable
from typing import Literal

import httpx
from langchain_core.tools import BaseTool, tool

from integrations.schemas.models import Coordinates
from travel_agent.schemas import SourceObservation, TripConstraints

TOOL_NAMES = frozenset({"search_hotels", "hotel_details", "tavily_search", "tavily_extract"})


def build_tools(trip: TripConstraints, client: httpx.AsyncClient, env: dict[str, str], evidence: dict[str, SourceObservation], mcp: Callable[[str, str, str, dict], Awaitable[dict]], rest: Callable[..., Awaitable[dict]], center: Coordinates | None = None) -> list[BaseTool]:
    @tool
    async def search_hotels(city_name: str | None = None, check_in: str | None = None, check_out: str | None = None,
        adults: int | None = None, children_ages: list[int] | None = None, page: int = 1, page_size: int = 10,
        stars: list[int] | None = None, price_max: int | None = None, meals: list[str] | None = None,
        hotel_types: list[str] | None = None, min_rating: float | None = None, free_cancellation: bool | None = None,
        breakfast_included: bool | None = None, hotel_amenities: list[str] | None = None,
        room_amenities: list[str] | None = None, view: Literal["compact", "full"] = "full") -> dict:
        """Search hotels with the requested guest composition, dates, amenities and page; return the complete provider response."""
        return await mcp("search_hotels", "tutu", "search_hotels", {
            "city_name": city_name if city_name is not None else trip.destination,
            "check_in": check_in if check_in is not None else str(trip.stay_start) if trip.stay_start else None,
            "check_out": check_out if check_out is not None else str(trip.stay_end) if trip.stay_end else None,
            "adults": adults if adults is not None else trip.adults,
            "children_ages": children_ages if children_ages is not None else trip.children_ages,
            "page": page, "page_size": page_size, "stars": stars, "price_max": price_max, "meals": meals,
            "hotel_types": hotel_types, "min_rating": min_rating, "free_cancellation": free_cancellation,
            "breakfast_included": breakfast_included, "hotel_amenities": hotel_amenities, "room_amenities": room_amenities, "view": view})

    @tool
    async def hotel_details(source_id: str, check_in: str | None = None, check_out: str | None = None,
        adults: int | None = None, children_ages: list[int] | None = None,
        view: Literal["compact", "rules", "reviews", "full"] = "full", review_limit: int = 5,
        review_offset: int = 0, review_topics: str | None = None) -> dict:
        """Read rooms, rates, rules and reviews only for a previously observed hotel."""
        return await mcp("hotel_details", "tutu", "get_offer_details", {
            "product_type": "hotels", "hotel_id": source_id.removeprefix("hotel:"),
            "check_in": check_in if check_in is not None else str(trip.stay_start) if trip.stay_start else None,
            "check_out": check_out if check_out is not None else str(trip.stay_end) if trip.stay_end else None,
            "adults": adults if adults is not None else trip.adults,
            "children_ages": children_ages if children_ages is not None else trip.children_ages,
            "view": view, "review_limit": review_limit, "review_offset": review_offset, "review_topics": review_topics})

    return [search_hotels, hotel_details]
