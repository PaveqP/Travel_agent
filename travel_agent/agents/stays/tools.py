from datetime import date
from typing import Literal

import httpx
from langchain_core.tools import BaseTool, tool

from integrations.schemas.models import Coordinates
from travel_agent.schemas import Area, Candidate, TripConstraints


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
    *, autonomous: bool = False,
) -> list[BaseTool]:
    @tool
    async def search_hotels(area: Area | None = None, check_in: date | None = None, check_out: date | None = None,
                            min_stars: int | None = None, min_rating: float | None = None,
                            free_cancellation: bool | None = None, page: int = 1,
                            hotel_amenities: list[str] | None = None, room_amenities: list[str] | None = None,
                            meals: list[str] | None = None, breakfast_included: bool | None = None,
                            hotel_types: list[str] | None = None, price_max: int | None = None) -> dict:
        """Search hotels for the server's area, dates and adult party."""
        start, end = check_in or trip.stay_start, check_out or trip.stay_end
        lower, upper = trip.date_from or trip.start, trip.date_to or trip.end
        if not start or not end or not lower or not upper or not lower <= start < end <= upper:
            return {'status': 'schema_error', 'reason': 'Hotel dates must be within the trip'}
        stars = max(min_stars or 0, trip.min_hotel_stars or 0)
        rating = max(min_rating or 0, float(trip.min_hotel_rating or 0))
        if not 0 <= stars <= 5 or not 0 <= rating <= 10:
            return {'status': 'schema_error'}
        filters = {}
        if 'mountain_view' in trip.stay_preferences:
            filters['room_amenities'] = ['mountain_view']
        if trip.holiday_type == 'ski' or 'near_lift' in trip.stay_preferences:
            filters['hotel_amenities'] = ['skiing']
        if stars:
            filters['stars'] = list(range(stars, 6))
        if rating:
            filters['min_rating'] = rating
        if free_cancellation is not None:
            filters['free_cancellation'] = free_cancellation
        filters.update({key: value for key, value in {
            'hotel_amenities': hotel_amenities, 'room_amenities': room_amenities, 'meals': meals,
            'breakfast_included': breakfast_included, 'hotel_types': hotel_types, 'price_max': price_max,
        }.items() if value is not None})
        return await mcp(
            "search_hotels",
            "tutu",
            "search_hotels",
            {
                "city_name": area or ("Красная Поляна" if trip.holiday_type == "ski" else trip.destination),
                "check_in": str(start),
                "check_out": str(end),
                "adults": trip.adults,
                "page_size": 30 if trip.hotel else 10,
                "page": page,
                **filters,
            },
        )

    @tool
    async def hotel_details(source_id: str, view: Literal["rules", "compact", "full"] = "rules") -> dict:
        """Read hotel details only for a hotel obtained in this delegation."""
        candidate = evidence.get(source_id)
        if candidate is None or candidate.role != 'stays':
            return {'status': 'forbidden'}
        return await mcp(
            "hotel_details",
            "tutu",
            "get_offer_details",
            {
                "product_type": "hotels",
                "hotel_id": candidate.provider_id or source_id.removeprefix("hotel:"),
                "check_in": str(candidate.start),
                "check_out": str(candidate.end),
                "adults": trip.adults,
                "view": view,
            },
        )

    return [search_hotels, hotel_details]
