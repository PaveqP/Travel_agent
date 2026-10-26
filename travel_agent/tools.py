import asyncio
import ipaddress
import json
import logging
import socket
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

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
        stay = data.get("stay", {})
        if stay.get("check_in") != str(trip.stay_start) or stay.get("check_out") != str(
            trip.stay_end
        ):
            raise ValueError("Stay dates/party mismatch")
        for row in data.get("hotels", []):
            if row.get("checkout_ref", {}).get("adults") != trip.adults:
                continue
            offer = row.get("best_offer") or {}
            if not offer.get("price") or offer.get("price_basis") != "stay_total":
                continue
            loc = row.get("location") or {}
            coordinates = (
                Coordinates(lat=loc["lat"], lon=loc["lng"])
                if loc.get("lat") is not None
                else None
            )
            result.append(
                Candidate(
                    id="hotel:" + row["hotel_id"],
                    role="stays",
                    name=row["name"],
                    coordinates=coordinates,
                    area=area_of(coordinates),
                    source=source,
                    start=trip.stay_start,
                    end=trip.stay_end,
                    adults=trip.adults,
                    price=Money(**offer["price"], basis="room_stay"),
                    url=offer.get("checkout_url"),
                )
            )
    elif method == "search_avia":
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
                    name=" / ".join(row.get("carriers", [])),
                    source=source,
                    start=departure.date(),
                    end=returning.date(),
                    adults=trip.adults,
                    origin=trip.origin,
                    destination="AER",
                    arrival_at=arrival,
                    return_departure_at=returning,
                    price=Money(**row["price"], basis="party"),
                    url=row.get("search_results_url"),
                )
            )
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
                    source=source,
                    coordinates=point,
                    area=area_of(point),
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
    owned: set[tuple[str, str]] = set()
    responses: dict[str, dict] = {}

    async def execute(name: str, provider: str, operation, method: str = "") -> dict:
        if name not in ALLOWED[role]:
            return {"status": "forbidden"}
        if counts["tools"] >= 8:
            warnings.append("tool_limit")
            return {"status": "cost_guard"}
        counts["tools"] += 1
        started = time.monotonic()
        status = "ok"
        try:
            async with asyncio.timeout(65 if provider in ("tutu", "2gis") else 40):
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
                provider, method, data, trip, datetime.now(timezone.utc)
            )
            for candidate in candidates:
                evidence[candidate.id] = candidate
                if provider == "tutu":
                    product, ident = candidate.id.split(":", 1)
                    owned.add(("hotels" if product == "hotel" else product, ident))
            if candidates:
                return {
                    "status": "ok",
                    "candidates": [
                        c.model_dump(
                            mode="json",
                            include={
                                "id",
                                "name",
                                "price",
                                "area",
                                "start",
                                "end",
                                "arrival_at",
                                "return_departure_at",
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
        key = json.dumps([name, provider, method, args], sort_keys=True)
        if key in responses:
            return responses[key]
        result = await execute(
            name,
            provider,
            lambda: runtime_call(role, provider, method, args, env, frozenset(owned)),
            method,
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
        for url in selected_urls:
            try:
                addresses = await asyncio.wait_for(
                    asyncio.get_running_loop().getaddrinfo(
                        urlparse(url).hostname, 443, type=socket.SOCK_STREAM
                    ),
                    timeout=3,
                )
            except (OSError, TimeoutError):
                return {"status": "forbidden"}
            if not addresses or any(
                not ipaddress.ip_address(address[4][0]).is_global
                for address in addresses
            ):
                return {"status": "forbidden"}
        return await rest(
            "tavily_extract",
            "tavily",
            "TAVILY_API_KEY",
            lambda: client.post(
                "https://api.tavily.com/extract",
                headers={"Authorization": "Bearer " + env.get("TAVILY_API_KEY", "")},
                json={"urls": selected_urls},
            ),
        )

    builders = {
        "transport": transport_tools,
        "stays": stay_tools,
        "experience": experience_tools,
    }
    selected = builders[role](trip, client, env, evidence, mcp, rest, center)
    selected += [tavily_search, tavily_extract]
    if {t.name for t in selected} != ALLOWED[role]:
        raise ValueError("Role tool registry does not match allowlist")
    return selected
