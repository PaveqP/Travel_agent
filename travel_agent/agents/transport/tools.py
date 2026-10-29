import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from itertools import product
from typing import Literal

import httpx
from langchain_core.tools import BaseTool, tool

from integrations.schemas.models import Coordinates, Money, Provenance
from travel_agent.schemas import Candidate, TripConstraints, TransportLeg
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
    *, autonomous: bool = False,
) -> list[BaseTool]:
    @tool
    async def search_flights(departure_date: date | None = None, return_date: date | None = None, direct_only: bool | None = None,
                             service_class: Literal['Y', 'S', 'C', 'F'] = 'Y', carriers: list[str] | None = None,
                             flight_numbers: list[str] | None = None, page: int = 1,
                             sort: Literal['price_asc', 'price_desc', 'duration_asc', 'departure_asc'] = 'price_asc',
                             destination: str | None = None) -> dict:
        """Search the user's dates, then bounded nearby dates; explicit windows sample up to six date pairs."""
        allowed = search_dates(trip)
        if departure_date is not None or return_date is not None:
            if (departure_date, return_date) not in allowed:
                return {'status': 'forbidden', 'reason': 'Dates outside the agreed search window'}
            pairs = [(departure_date, return_date)]
        else:
            pairs = allowed[:1 if autonomous else 6]
        if not pairs:
            return {"status": "empty", "candidates": []}
        semaphore = asyncio.Semaphore(2)
        searched = []
        found: dict[str, dict] = {}

        async def query(start: date, end: date) -> dict:
            async with semaphore:
                searched.append({"start": str(start), "end": str(end)})
                try:
                    async with asyncio.timeout(63):
                        result = await mcp("search_flights", "tutu", "search_avia", {
                            "origin": trip.origin, "destination": destination or trip.destination, "departure_date": str(start),
                            "return_date": str(end), "adults": trip.adults, "page_size": 10,
                            "sort": sort, "service_class": service_class, "page": page,
                            "direct_only": trip.direct_only or bool(direct_only),
                            **({'carriers': carriers} if carriers is not None else {}),
                            **({'flight_numbers': flight_numbers} if flight_numbers is not None else {})})
                        found.update({c['id']: c for c in result.get('candidates', [])})
                        return result
                except TimeoutError:
                    return {"status": "timeout"}

        first = {"status": "empty"}
        try:
            async with asyncio.timeout(65):
                first = await query(*pairs[0])
                fresh = any(transport_matches(c, trip, datetime.now(timezone.utc)) for c in evidence.values())
                if first["status"] in ("ok", "empty", "no_availability") and (not fresh or trip.date_from and trip.date_to):
                    await asyncio.gather(*(query(start, end) for start, end in pairs[1:]))
        except TimeoutError:
            first = {"status": "timeout"}
        return {"status": ("partial" if first["status"] == "timeout" else "ok") if found else first["status"],
                "candidates": list(found.values())[:20], "total_candidates": len(found),
                "searched_dates": searched, "exhaustive": False, "search_limit": 6}

    @tool
    async def search_trains(mode: Literal["rail", "etrain"] = "rail", destination: str | None = None,
                            departure_date: date | None = None, return_date: date | None = None) -> dict:
        """In autonomous mode compare round-trip rail fares for the party; staged mode returns outbound schedules."""
        pairs = search_dates(trip)
        if departure_date is not None or return_date is not None:
            if (departure_date, return_date) not in pairs:
                return {'status': 'forbidden', 'reason': 'Dates outside the agreed search window'}
            pairs = [(departure_date, return_date)]
        if not pairs:
            return {'status': 'schema_error'}
        start, end = pairs[0]
        if not autonomous or mode == 'etrain':
            return await mcp(
                "search_trains",
                "tutu",
                "search_" + mode,
                {
                    "origin": trip.origin,
                    "destination": destination or trip.destination,
                    "departure_date": str(start),
                    "page_size": 10,
                },
            )
        outbound, inbound = await asyncio.gather(*(
            mcp('search_trains', 'tutu', 'search_rail', {'origin': origin, 'destination': destination,
                'departure_date': str(day), 'passengers': trip.adults, 'page_size': 5, 'direct_only': trip.direct_only})
            for origin, destination, day in ((trip.origin, destination or trip.destination, start), (destination or trip.destination, trip.origin, end))
        ))
        if any(r['status'] not in ('ok', 'empty') for r in (outbound, inbound)):
            return {'status': next(r['status'] for r in (outbound, inbound) if r['status'] not in ('ok', 'empty'))}
        data_out, data_back = outbound.get('context', {}), inbound.get('context', {})
        try:
            rows = rail_candidates(data_out, data_back, trip, start, end)
        except (KeyError, TypeError, ValueError):
            return {'status': 'schema_error'}
        evidence.update({c.id: c for c in rows})
        return {'status': 'ok' if rows else 'empty', 'candidates': [c.summary() for c in rows]}

    @tool
    async def transport_details(source_id: str) -> dict:
        """Read flight details only for a flight obtained in this delegation."""
        candidate = evidence.get(source_id)
        if candidate is None or candidate.role != 'transport' or candidate.source.provider != 'tutu':
            return {'status': 'forbidden'}
        return await mcp(
            "transport_details", "tutu", "get_offer_details",
            {"product_type": "avia", "offer_id": candidate.provider_id or source_id.removeprefix("avia:")},
        )

    @tool
    async def yandex_schedule(origin: str, destination: str, day: date | None = None,
                              transport_type: Literal['suburban', 'train', 'plane', 'bus'] = 'suburban',
                              result_timezone: str | None = None) -> dict:
        """Read schedules using real Yandex station codes or city names resolved by Yandex."""
        stations = {"Сочи": "s9613034", "Адлер": "s9613054", "Роза Хутор": "s9812791"}
        pairs = search_dates(trip)
        search_day = day or (pairs[0][0] if pairs else None)
        if search_day is None:
            return {'status': 'schema_error'}
        return await rest('yandex_schedule', 'yandex_rasp', 'YANDEX_RASP_API_KEY',
            lambda: yandex_rasp.schedule(client, env.get('YANDEX_RASP_API_KEY', ''),
                stations.get(origin, origin), stations.get(destination, destination), str(search_day),
                transport_type=transport_type, result_timezone=result_timezone))

    @tool
    async def cached_flights(origin_iata: str | None = None, destination_iata: str | None = None) -> dict:
        """Read Travelpayouts cached fares for a known origin IATA; not live availability."""
        if origin_iata is None:
            known = {"москва": "MOW", "санкт-петербург": "LED", "санкт петербург": "LED", "петербург": "LED"}
            value = trip.origin or ""
            origin_iata = value.upper() if len(value) == 3 and value.isascii() else known.get(value.casefold())
        if not origin_iata or len(origin_iata) != 3 or not origin_iata.isascii() or not origin_iata.isalpha():
            return {"status": "schema_error"}
        if not destination_iata:
            return {"status": "schema_error", "reason": "Pass the destination IATA from a verified transport result"}
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
                destination=destination_iata,
            ),
        )

    return [
        search_flights,
        search_trains,
        transport_details,
        yandex_schedule,
        cached_flights,
    ]


def rail_candidates(outbound: dict, inbound: dict, trip: TripConstraints, start: date, end: date) -> list[Candidate]:
    for data in (outbound, inbound):
        pricing = data.get('meta', {}).get('pricing', {})
        if pricing.get('basis') != 'per_seat' or pricing.get('passengers') != trip.adults:
            raise ValueError('Rail pricing must explicitly state per-seat basis and party size')
    out_from, out_to = outbound['meta']['from'], outbound['meta']['to']
    back_from, back_to = inbound['meta']['from'], inbound['meta']['to']
    if out_to.get('geo_id') != back_from.get('geo_id') or out_from.get('geo_id') != back_to.get('geo_id'):
        raise ValueError('Rail route endpoints do not match a return trip')
    now = datetime.now(timezone.utc)
    source = Provenance(provider='tutu', source_url='https://mcp.tutu.ru/mcp', retrieved_at=now,
                        expires_at=now + timedelta(minutes=10), evidence='live')
    result = []
    for out, back in product(outbound.get('offers', [])[:3], inbound.get('offers', [])[:3]):
        depart, arrival, returning, home = [datetime.fromisoformat(value) for value in (out['departure_at'], out['arrival_at'], back['departure_at'], back['arrival_at'])]
        if any(value.tzinfo is None for value in (depart, arrival, returning, home)) or depart.date() != start or returning.date() != end or not depart < arrival < returning < home:
            continue
        if out['price']['currency'] != 'RUB' or back['price']['currency'] != 'RUB':
            continue
        amount = (Decimal(str(out['price']['amount'])) + Decimal(str(back['price']['amount']))) * trip.adults
        ident = sha256((out['offer_id'] + ':' + back['offer_id']).encode()).hexdigest()[:24]
        result.append(Candidate(id='rail:' + ident, role='transport', transport_mode='rail',
            name='ЖД: ' + ' / '.join(dict.fromkeys([*out.get('carriers', []), *back.get('carriers', [])])),
            source=source, price=Money(amount=amount, currency='RUB', basis='party'), start=start, end=end,
            adults=trip.adults, origin=trip.origin, destination=trip.destination, arrival_city=out_to.get('name'), departure_at=depart, arrival_at=arrival,
            return_departure_at=returning, duration_minutes=int((arrival-depart).total_seconds()/60),
            transfers=max(out.get('segments_count', 1)-1, back.get('segments_count', 1)-1),
            legs=[TransportLeg(mode='rail', origin=out_from.get('name') or trip.origin, destination=out_to.get('name') or trip.destination, departure_at=depart, arrival_at=arrival),
                  TransportLeg(mode='rail', origin=back_from.get('name') or trip.destination, destination=back_to.get('name') or trip.origin, departure_at=returning, arrival_at=home)],
            url=out.get('search_results_url'), description='Туда и обратно. Сумма рассчитана по тарифам за одно место для всей группы; наличие мест и итоговая цена перед покупкой требуют проверки.'))
    return result[:6]
