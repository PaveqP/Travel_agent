import asyncio
import ipaddress
import json
import logging
import socket
import time
from hashlib import sha256
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlparse

import httpx
from langchain_core.tools import tool
from pydantic import ValidationError

from integrations.mcp.client import runtime_call
from integrations.schemas.models import Coordinates, Money, Provenance
from travel_agent.engine import area_of
from travel_agent.schemas import Candidate, Role, TripConstraints, WebEvidence

from travel_agent.agents.transport.tools import (
    TOOL_NAMES as TRANSPORT_TOOLS,
    build_tools as transport_tools,
)
from travel_agent.agents.stays.tools import (
    TOOL_NAMES as STAY_TOOLS,
    build_tools as stay_tools,
)
from travel_agent.agents.experience.tools import (
    TOOL_NAMES as EXPERIENCE_TOOLS,
    build_tools as experience_tools,
)

ALLOWED = {
    "transport": TRANSPORT_TOOLS,
    "stays": STAY_TOOLS,
    "experience": EXPERIENCE_TOOLS,
}
logger = logging.getLogger(__name__)


def public_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        return False
    if "." not in host or host.endswith((".local", ".internal", ".localhost")):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return True


def hotel_amenities(hotel: dict[str, Any]) -> list[str]:
    labels: list[str] = []

    def collect(items: object) -> None:
        if not isinstance(items, list):
            return
        for item in items:
            if isinstance(item, str) and item.strip():
                labels.append(item.strip())
            elif isinstance(item, dict):
                if item.get("available") is False or item.get("included") is False:
                    continue
                nested = item.get("amenities", item.get("items"))
                if isinstance(nested, list):
                    collect(nested)
                else:
                    label = item.get("name") or item.get("label") or item.get("text")
                    if isinstance(label, str) and label.strip():
                        labels.append(label.strip())

    collect(hotel.get("amenities"))
    collect(hotel.get("amenity_groups"))
    return list(dict.fromkeys(labels))[:60]


def hotel_photos(hotel: dict[str, Any]) -> list[str]:
    return list(dict.fromkeys(url for url in (hotel.get("photos") or [])
                              if isinstance(url, str) and public_url(url)))[:10]


def normalize(
    provider: str,
    method: str,
    data: dict[str, Any] | list,
    trip: TripConstraints,
    now: datetime,
) -> list[Candidate]:
    source = Provenance(
        provider=provider,
        source_url="https://mcp.tutu.ru/mcp"
        if provider == "tutu"
        else "https://2gis.ru/sochi",
        retrieved_at=now,
        expires_at=now + timedelta(minutes=10 if provider == "tutu" else 60),
        evidence="live" if provider == "tutu" else "catalog",
    )
    result = []
    if method == "search_hotels":
        if data.get("hotels") == []:
            return []
        stay = data.get("stay", {})
        if stay.get("check_in") != str(trip.stay_start) or stay.get("check_out") != str(
            trip.stay_end
        ):
            raise ValueError("Stay dates/party mismatch")
        for row in data.get("hotels", []):
            if row.get("checkout_ref", {}).get("adults") != trip.adults:
                continue
            offer = row.get("best_offer") or {}
            priced = bool(offer.get("price") and offer.get("price_basis") == "stay_total")
            loc = row.get("location") or {}
            coordinates = (
                Coordinates(lat=loc["lat"], lon=loc["lng"])
                if loc.get("lat") is not None
                else None
            )
            result.append(
                Candidate(
                    id="hotel:" + row["hotel_id"],
                    provider_id=row["hotel_id"],
                    role="stays",
                    name=row["name"],
                    stars=row.get("stars"), rating=row.get("rating"),
                    review_count=row.get("review_count"), address=row.get("address"),
                    amenities=hotel_amenities(row),
                    photos=hotel_photos(row),
                    description='; '.join(value for value in (
                        f"Звёзды: {row['stars']}" if row.get('stars') else '',
                        f"Оценка Туту: {row['rating']}/10" if row.get('rating') is not None else '',
                        f"Отзывов: {row['review_count']}" if row.get('review_count') is not None else '',
                        row.get('address') or '',
                    ) if value)[:1000],
                    coordinates=coordinates,
                    area=area_of(coordinates),
                    source=source if priced else source.model_copy(update={"evidence": "catalog"}),
                    start=trip.stay_start,
                    end=trip.stay_end,
                    adults=trip.adults,
                    price=Money(**offer["price"], basis="room_stay") if priced else None,
                    url=offer.get("checkout_url") or row.get("url") or "https://hotel.tutu.ru/",
                )
            )
    elif method == "search_avia":
        if data.get("offers") == []:
            return []
        if data.get("meta", {}).get("pricing", {}).get("basis") != "party_total":
            raise ValueError("Unverified price basis")
        if (
            data.get("meta", {}).get("pricing", {}).get("passengers", {}).get("full")
            != trip.adults
        ):
            raise ValueError("Passenger mismatch")
        for row in data.get("offers", []):
            legs = row.get("legs", [])
            if not row.get("is_round_trip") or len(legs) != 2:
                continue
            departure = datetime.fromisoformat(row["departure_at"])
            arrival = datetime.fromisoformat(row["arrival_at"])
            returning = datetime.fromisoformat(row["return_departure_at"])
            if (
                departure.date() != trip.start
                or returning.date() != trip.end
                or not arrival.tzinfo
                or not returning.tzinfo
            ):
                continue
            if "AER" not in legs[0].get("to", "") or "AER" not in legs[1].get(
                "from", ""
            ):
                continue
            result.append(
                Candidate(
                    id="avia:" + row["offer_id"],
                    role="transport",
                    name=" / ".join(row.get("carriers", [])) or "Перелёт Туту",
                    source=source,
                    start=departure.date(),
                    end=returning.date(),
                    adults=trip.adults,
                    origin=trip.origin,
                    destination="AER",
                    arrival_at=arrival,
                    baggage_included=row.get('baggage_included') if isinstance(row.get('baggage_included'), bool) else None,
                    sports_equipment_included=row.get('sports_equipment_included') if isinstance(row.get('sports_equipment_included'), bool) else None,
                    departure_at=departure,
                    duration_minutes=legs[0].get("duration_min"),
                    transfers=len(legs[0]["segments"]) - 1 if legs[0].get("segments") else None,
                    return_departure_at=returning,
                    return_arrival_at=row.get("return_arrival_at"),
                    legs=[{
                        "mode": "avia", "origin": leg["from"], "destination": leg["to"],
                        "departure_at": leg["departure_at"], "arrival_at": leg["arrival_at"],
                        "duration_minutes": leg.get("duration_min"),
                        "transfers": len(leg["segments"]) - 1 if leg.get("segments") else None,
                        "carriers": list(dict.fromkeys(s["carrier"] for s in leg.get("segments", []) if s.get("carrier")))[:10],
                        "flight_numbers": [s["voyage_no"] for s in leg.get("segments", []) if s.get("voyage_no")][:10],
                    } for leg in legs if all(leg.get(k) for k in ("from", "to", "departure_at", "arrival_at"))],
                    price=Money(**row["price"], basis="party"),
                    url=row.get("search_results_url") or "https://www.tutu.ru/avia/",
                    description="" if row.get("search_results_url") else "Поставщик не вернул ссылку на конкретный тариф; ссылка ведёт в общий поиск авиабилетов Туту.",
                )
            )
    elif provider == "travelpayouts":
        source = source.model_copy(update={"provider": provider, "source_url": "https://www.aviasales.ru/", "evidence": "cached"})
        for row in data.get("data", []):
            if row.get("destination") != "AER" or not row.get("price") or not row.get("departure_at") or not row.get("return_at"):
                continue
            departure = datetime.fromisoformat(row["departure_at"])
            returning = datetime.fromisoformat(row["return_at"])
            link = row.get("link") or "https://www.aviasales.ru/"
            if link.startswith("/search/"):
                link = "https://www.aviasales.ru" + link
            result.append(Candidate(
                id="aviasales:" + sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()[:24],
                role="transport", name="Aviasales — " + row.get("airline", "перелёт"), source=source,
                start=departure.date(), end=returning.date(), departure_at=departure, return_departure_at=returning,
                origin=row.get("origin"), destination="AER", adults=1, transfers=row.get("transfers"),
                duration_minutes=row.get("duration_to"), price=Money(amount=str(row["price"]), currency="RUB", basis="person"), url=link,
                description="Цена из кэша поисков Aviasales за одного пассажира. Наличие для всей группы и точное время прилёта требуют проверки."))
    elif provider == "2gis" and method == "search_places":
        for row in data.get("items", []):
            point = (
                Coordinates.model_validate(row["coordinates"])
                if row.get("coordinates")
                else None
            )
            result.append(
                Candidate(
                    id="2gis:" + row["id"],
                    role="experience",
                    name=row["name"],
                    description='; '.join(str(row[k]) for k in ('subtype', 'full_address_name') if row.get(k))[:1000],
                    source=source,
                    coordinates=point,
                    area=area_of(point),
                    url=row.get("url") or "https://2gis.ru/sochi/search/" + quote(row["name"], safe=""),
                )
            )
    elif provider == "geoapify":
        source = source.model_copy(
            update={"provider": provider, "source_url": "https://www.geoapify.com/"}
        )
        for row in data.get("features", []):
            props = row["properties"]
            if not props.get("name"):
                continue
            point = Coordinates(lat=props["lat"], lon=props["lon"])
            result.append(
                Candidate(
                    id="geoapify:" + props["place_id"],
                    role="experience",
                    name=props["name"],
                    source=source,
                    coordinates=point,
                    area=area_of(point),
                )
            )
    elif provider == "opentripmap":
        source = source.model_copy(
            update={"provider": provider, "source_url": "https://opentripmap.com/"}
        )
        for row in data:
            if not row.get("name"):
                continue
            point = Coordinates.model_validate(row["point"])
            result.append(
                Candidate(
                    id="otm:" + row["xid"],
                    role="experience",
                    name=row["name"],
                    source=source,
                    coordinates=point,
                    area=area_of(point),
                )
            )
    elif provider == "timepad":
        source = source.model_copy(
            update={"provider": provider, "source_url": "https://timepad.ru/"}
        )
        for row in data.get("values", []):
            loc = row.get("location") or {}
            coords = loc.get("coordinates") or {}
            if not coords or not row.get("starts_at"):
                continue
            point = (
                Coordinates(lat=coords[0], lon=coords[1])
                if isinstance(coords, list) and len(coords) == 2
                else Coordinates.model_validate(coords)
            )
            day = datetime.fromisoformat(row["starts_at"]).date()
            if trip.start <= day <= trip.end:
                result.append(
                    Candidate(
                        id="timepad:" + str(row["id"]),
                        role="experience",
                        name=row["name"],
                        source=source,
                        coordinates=point,
                        area=area_of(point),
                        start=day,
                        url=row.get("url"),
                    )
                )
    return result


def build_tools(
    role: Role,
    trip: TripConstraints,
    revision: int,
    client: httpx.AsyncClient,
    env: dict[str, str],
    evidence: dict[str, Candidate],
    warnings: list[str],
    counts: dict[str, int],
    center: Coordinates | None = None,
    web_evidence: list[WebEvidence] | None = None,
    autonomous: bool = False,
):
    key_names = {
        "transport": ("TRAVELPAYOUTS_TOKEN", "YANDEX_RASP_API_KEY", "TAVILY_API_KEY"),
        "stays": ("TAVILY_API_KEY",),
        "experience": (
            "TWOGIS_API_KEY",
            "GEOAPIFY_API_KEY",
            "TIMEPAD_TOKEN",
            "OPENTRIPMAP_API_KEY",
            "TAVILY_API_KEY",
        ),
    }
    env = {key: env[key] for key in key_names[role] if key in env}
    urls: set[str] = set()
    owned: set[tuple[str, str]] = {
        ('hotels', c.provider_id or c.id.removeprefix('hotel:')) for c in evidence.values()
        if role == 'stays' and c.role == 'stays' and c.id.startswith('hotel:')
        and c.source.provider == 'tutu' and (c.start, c.end, c.adults) == (trip.stay_start, trip.stay_end, trip.adults)
    }
    responses: dict[str, dict] = {}
    flight_details: dict[str, dict] = {}

    async def execute(name: str, provider: str, operation, method: str = "", query_trip: TripConstraints | None = None,
                      hotel_ref: tuple[str, str, str] | None = None) -> dict:
        if name not in ALLOWED[role]:
            return {"status": "forbidden"}
        if counts["tools"] >= (6 if autonomous else 8):
            warnings.append("tool_limit")
            return {"status": "cost_guard"}
        counts["tools"] += 1
        started = time.monotonic()
        status = "ok"
        try:
            async with asyncio.timeout(12 if method == "build_route" else 20 if autonomous else 65 if provider in ("tutu", "2gis") else 40):
                response = await operation()
            if isinstance(response, httpx.Response):
                response.raise_for_status()
                data = response.json()
            else:
                status = response.get("status", "schema_error")
                data = response.get("data", {})
            if status != "ok":
                warnings.append(provider + ":" + status)
                return {"status": status}
            if isinstance(data, dict) and (
                data.get("error") or data.get("success") is False
            ):
                warnings.append(provider + ":schema_error")
                return {"status": "schema_error"}
            candidates = normalize(
                provider, method, data, query_trip or trip, datetime.now(timezone.utc)
            )
            if provider == 'tutu' and method == 'search_avia':
                verified = {c.id for c in candidates}
                flight_details.update({row['offer_id']: row for row in data.get('offers', []) if 'avia:' + row['offer_id'] in verified})
            for candidate in candidates:
                if autonomous and candidate.role == 'stays':
                    quote = sha256(f'{candidate.start}:{candidate.end}:{candidate.adults}'.encode()).hexdigest()[:10]
                    candidate.id += '@' + quote
                evidence[candidate.id] = candidate
                if provider == "tutu":
                    product, ident = candidate.id.split(":", 1)
                    owned.add(("hotels" if product == "hotel" else product, candidate.provider_id or ident))
            if candidates:
                return {
                    "status": "ok",
                    "candidates": [
                        c.model_dump(
                            mode="json",
                            include={
                                "id",
                                "name", "transport_mode", "baggage_included", "sports_equipment_included",
                                "stars", "rating", "review_count", "address", "description",
                                "price",
                                "area",
                                "start",
                                "end",
                                "arrival_at",
                                "departure_at",
                                "duration_minutes",
                                "transfers",
                                "return_departure_at",
                                "url",
                                "source",
                            },
                        )
                        for c in candidates
                    ],
                }
            if method in (
                "search_avia",
                "search_hotels",
                "search_places",
            ) or provider in ("geoapify", "timepad", "opentripmap"):
                return {"status": "empty", "candidates": []}
            if method in ('search_rail', 'search_etrain') or provider == 'yandex_rasp':
                rows = data.get('offers' if provider == 'tutu' else 'segments', [])
                return {'status': 'ok' if rows else 'empty', 'context': data,
                        'warning': 'Schedule context only; not a validated round-trip quote'}
            if provider == 'tutu' and method == 'get_offer_details' and role == 'stays':
                hotel = data.get('hotel', {})
                hotel_id = str(hotel.get('hotel_id') or hotel.get('id') or (hotel_ref[0] if hotel_ref else ''))
                if hotel_ref and hotel_id != hotel_ref[0]:
                    raise ValueError('Hotel details ID mismatch')
                for ident, candidate in evidence.items():
                    if candidate.role == 'stays' and hotel_ref == (candidate.provider_id or candidate.id.removeprefix('hotel:'), str(candidate.start), str(candidate.end)):
                        evidence[ident] = candidate.model_copy(update={
                            'amenities': hotel_amenities(hotel) or candidate.amenities,
                            'photos': hotel_photos(hotel) or candidate.photos,
                        })
            if provider == 'tutu' and method == 'get_offer_details' and web_evidence is not None:
                hotel = data.get('hotel', {})
                details = {'hotel': {k: hotel[k] for k in ('name', 'description', 'stars', 'rating', 'address', 'location', 'amenities', 'amenity_groups', 'review_summary', 'policies') if k in hotel},
                           'rooms': [{k: room[k] for k in ('room_name', 'room_amenities', 'max_occupancy') if k in room} for room in data.get('rooms', [])[:2]]}
                candidate = next((c for c in evidence.values() if (c.provider_id or c.id.removeprefix('hotel:')) == str(hotel.get('hotel_id') or hotel.get('id') or '')), None)
                if candidate is None and len(evidence) == 1:
                    candidate = next(iter(evidence.values()))
                if candidate is not None and details['hotel']:
                    web_evidence.append(WebEvidence(url=candidate.url or candidate.source.source_url,
                        title='Туту: ' + candidate.name, text=json.dumps(details, ensure_ascii=False)[:2000], retrieved_at=datetime.now(timezone.utc)))
            if provider == "openmeteo":
                daily = data.get("daily", {})
                dates = daily.get("time", [])
                covers = str(trip.start) in dates and str(trip.end) in dates
                if not covers:
                    warnings.append("weather_outside_forecast_horizon")
                return {"status": "ok", "covers_trip": covers, "daily": daily}
            if provider == "tavily":
                results = []
                for row in data.get("results", [])[:5]:
                    url = row.get("url", "")
                    if public_url(url):
                        urls.add(url)
                        results.append(
                            {
                                "url": url,
                                "title": row.get("title", "")[:200],
                                "text": (
                                    row.get("content") or row.get("raw_content") or ""
                                )[:2000],
                            }
                        )
                if web_evidence is not None:
                    web_evidence.extend(WebEvidence(**row, retrieved_at=datetime.now(timezone.utc)) for row in results)
                if role in ("transport", "stays") and not evidence:
                    for row in results:
                        ident = "web:" + sha256(row["url"].encode()).hexdigest()[:24]
                        evidence[ident] = Candidate(id=ident, role=role, name=row["title"],
                            source=Provenance(provider="tavily", source_url=row["url"], retrieved_at=datetime.now(timezone.utc), expires_at=datetime.now(timezone.utc) + timedelta(hours=1), evidence="catalog"),
                            url=row["url"], description=row["text"][:1000])
                return {
                    "status": "ok" if results else "empty",
                    "evidence": "catalog",
                    "results": results,
                }
            return {
                "status": "ok",
                "context": str(data)[:6000],
                "warning": "Context only, not a validated trip quote",
            }
        except (TimeoutError, httpx.TimeoutException):
            status = "timeout"
        except httpx.HTTPStatusError as exc:
            status = {401: "unauthorized", 403: "forbidden", 429: "rate_limited"}.get(
                exc.response.status_code, "network_error"
            )
        except httpx.RequestError:
            status = "network_error"
        except (ValueError, KeyError, TypeError, ValidationError):
            status = "schema_error"
        finally:
            logger.info(
                "role=%s tool=%s provider=%s revision=%s status=%s duration_ms=%s",
                role,
                name,
                provider,
                revision,
                status,
                round((time.monotonic() - started) * 1000),
            )
        warnings.append(provider + ":" + status)
        return {"status": status}

    async def mcp(name: str, provider: str, method: str, args: dict) -> dict:
        if method == 'get_offer_details' and args.get('product_type') == 'avia':
            ref = flight_details.get(args.get('offer_id'))
            if ref is not None:
                args = {**args, 'details_ref': ref}
        key = json.dumps([name, provider, method, args], sort_keys=True)
        if key in responses:
            return responses[key]
        query_trip = None
        if method == 'search_hotels':
            query_trip = TripConstraints.model_validate({**trip.model_dump(), 'start': args['check_in'], 'end': args['check_out'], 'check_in': args['check_in'], 'check_out': args['check_out']})
        if method == "search_avia":
            query_trip = TripConstraints.model_validate({**trip.model_dump(), "start": args["departure_date"], "end": args["return_date"], "check_in": None, "check_out": None})
        result = await execute(
            name,
            provider,
            lambda: runtime_call(role, provider, method, args, env, frozenset(owned)),
            method,
            query_trip,
            (str(args['hotel_id']), args['check_in'], args['check_out']) if role == 'stays' and method == 'get_offer_details' else None,
        )
        responses[key] = result
        return result

    async def rest(name: str, provider: str, key_name: str | None, operation) -> dict:
        if name not in ALLOWED[role]:
            return {"status": "forbidden"}
        if key_name and not env.get(key_name):
            warnings.append(provider + ":missing_key")
            return {"status": "missing_key"}
        return await execute(name, provider, operation)

    @tool
    async def tavily_search(query: str) -> dict:
        """Search public context, never live price or availability evidence."""
        return await rest(
            "tavily_search",
            "tavily",
            "TAVILY_API_KEY",
            lambda: client.post(
                "https://api.tavily.com/search",
                headers={"Authorization": "Bearer " + env.get("TAVILY_API_KEY", "")},
                json={
                    "query": query[:500],
                    "max_results": 5,
                    "include_answer": False,
                    "include_raw_content": False,
                },
            ),
        )

    @tool
    async def tavily_extract(selected_urls: list[str]) -> dict:
        """Extract up to three public HTTPS URLs returned by this delegation's search."""
        if not 1 <= len(selected_urls) <= 3 or any(
            u not in urls or not public_url(u) for u in selected_urls
        ):
            return {"status": "forbidden"}
        verified_urls = []
        skipped = []
        for url in selected_urls:
            try:
                addresses = await asyncio.wait_for(
                    asyncio.get_running_loop().getaddrinfo(
                        urlparse(url).hostname, 443, type=socket.SOCK_STREAM
                    ),
                    timeout=3,
                )
            except (OSError, TimeoutError) as exc:
                status = 'timeout' if isinstance(exc, TimeoutError) else 'network_error'
                warnings.append('tavily:dns_' + status)
                skipped.append({'url': url, 'status': status})
                continue
            if not addresses or any(
                not ipaddress.ip_address(address[4][0]).is_global
                for address in addresses
            ):
                return {"status": "forbidden"}
            verified_urls.append(url)
        if not verified_urls:
            return {'status': 'timeout' if any(row['status'] == 'timeout' for row in skipped) else 'network_error', 'skipped_urls': skipped}
        result = await rest(
            "tavily_extract",
            "tavily",
            "TAVILY_API_KEY",
            lambda: client.post(
                "https://api.tavily.com/extract",
                headers={"Authorization": "Bearer " + env.get("TAVILY_API_KEY", "")},
                json={"urls": verified_urls},
            ),
        )
        return {**result, 'skipped_urls': skipped}

    builders = {
        "transport": transport_tools,
        "stays": stay_tools,
        "experience": experience_tools,
    }
    selected = builders[role](trip, client, env, evidence, mcp, rest, center, autonomous=autonomous)
    selected += [tavily_search, tavily_extract]
    if {t.name for t in selected} != ALLOWED[role]:
        raise ValueError("Role tool registry does not match allowlist")
    return selected
