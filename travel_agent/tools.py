import asyncio
import ipaddress
import json
import logging
import socket
import time
from hashlib import sha256
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from langchain_core.tools import BaseTool, tool
from pydantic import ValidationError

from integrations.mcp.client import SERVERS, runtime_call
from integrations.schemas.models import Coordinates, Provenance
from travel_agent.schemas import Role, SourceObservation, TripConstraints, WebEvidence
from travel_agent.agents.transport.tools import TOOL_NAMES as TRANSPORT_TOOLS, build_tools as transport_tools
from travel_agent.agents.stays.tools import TOOL_NAMES as STAY_TOOLS, build_tools as stay_tools
from travel_agent.agents.experience.tools import TOOL_NAMES as EXPERIENCE_TOOLS, build_tools as experience_tools

ALLOWED = {"transport": TRANSPORT_TOOLS, "stays": STAY_TOOLS, "experience": EXPERIENCE_TOOLS}
logger = logging.getLogger(__name__)


def public_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
        return False
    if "." not in host or host.endswith((".local", ".internal", ".localhost")):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return True


def build_tools(
    role: Role,
    trip: TripConstraints,
    revision: int,
    client: httpx.AsyncClient,
    env: dict[str, str],
    evidence: dict[str, SourceObservation],
    warnings: list[str],
    counts: dict[str, int],
    center: Coordinates | None = None,
    web_evidence: list[WebEvidence] | None = None,
) -> list[BaseTool]:
    key_names = {
        "transport": ("TRAVELPAYOUTS_TOKEN", "YANDEX_RASP_API_KEY", "TAVILY_API_KEY"),
        "stays": ("TAVILY_API_KEY",),
        "experience": ("TWOGIS_API_KEY", "GEOAPIFY_API_KEY", "TIMEPAD_TOKEN", "OPENTRIPMAP_API_KEY", "TAVILY_API_KEY"),
    }
    env = {key: env[key] for key in key_names[role] if key in env}
    urls: set[str] = set()
    owned: dict[tuple[str, str], dict] = {}
    responses: dict[str, dict] = {}

    def register(observation: SourceObservation) -> None:
        if observation.role != role:
            raise ValueError("Foreign role observation")
        data = observation.data
        if observation.provider != "tutu" or observation.status != "ok" or not isinstance(data, dict):
            return
        products = {"search_avia": "avia", "search_rail": "rail", "search_etrain": "etrain", "search_bus": "bus", "search_hotels": "hotels"}
        product = products.get(observation.tool)
        if product:
            rows = data.get("hotels" if product == "hotels" else "offers", [])
            if not isinstance(rows, list):
                return
            for row in rows:
                if not isinstance(row, dict):
                    continue
                ident = row.get("hotel_id" if product == "hotels" else "offer_id")
                if ident is not None:
                    owned[product, str(ident)] = row

    for observation in evidence.values():
        register(observation)
        if observation.provider == "tavily" and isinstance(observation.data, dict):
            urls.update(row["url"] for row in observation.data.get("results", []) if public_url(row.get("url", "")))

    async def execute(name: str, provider: str, operation: Callable[[], Awaitable[httpx.Response | dict]], method: str = "", arguments: dict | None = None) -> dict:
        if name not in ALLOWED[role]:
            return {"status": "forbidden"}
        if counts["tools"] >= 8:
            warnings.append("tool_limit")
            return {"status": "cost_guard"}
        counts["tools"] += 1
        started = time.monotonic()
        status = "ok"
        data = None
        raw = None
        try:
            async with asyncio.timeout(65 if provider in ("tutu", "2gis") else 40):
                response = await operation()
            if isinstance(response, httpx.Response):
                response.raise_for_status()
                data = response.json()
            else:
                status = response.get("status", "schema_error")
                data = response.get("data")
                raw = response.get("response")
        except (TimeoutError, httpx.TimeoutException):
            status = "timeout"
        except httpx.HTTPStatusError as exc:
            status = {401: "unauthorized", 403: "forbidden", 429: "rate_limited"}.get(exc.response.status_code, "network_error")
            data = {"http_status": exc.response.status_code, "body": exc.response.text}
        except httpx.RequestError:
            status = "network_error"
        except (ValueError, ValidationError):
            status = "schema_error"
        for value in env.values():
            if value and len(value) >= 8:
                encoded = json.dumps(value)[1:-1]
                data = json.loads(json.dumps(data).replace(encoded, "[REDACTED]"))
                raw = json.loads(json.dumps(raw).replace(encoded, "[REDACTED]"))
        now = datetime.now(timezone.utc)
        source_url = SERVERS[provider][0] if provider in SERVERS else {
            "travelpayouts": "https://www.aviasales.ru/", "yandex_rasp": "https://rasp.yandex.ru/",
            "tavily": "https://tavily.com/", "openmeteo": "https://open-meteo.com/",
            "timepad": "https://timepad.ru/", "opentripmap": "https://opentripmap.com/",
        }[provider]
        kind = "cached" if provider == "travelpayouts" else "live" if provider == "tutu" and method.startswith("search_") else "catalog"
        if provider == "tutu" and method == "get_offer_details":
            kind = "live" if (arguments or {}).get("product_type") in ("hotels", "rail", "bus") else "derived"
        if status != "ok":
            kind = "catalog"
        observation = SourceObservation(
            id="response:" + uuid4().hex, role=role, revision=revision, provider=provider,
            tool=method or name, arguments=arguments or {}, constraints=trip.model_dump(mode="json"), status=status,
            source=Provenance(provider=provider, source_url=source_url, retrieved_at=now,
                expires_at=now + timedelta(minutes=10 if kind == "live" else 60), evidence=kind),
            data=data, response=raw,
        )
        evidence[observation.id] = observation
        register(observation)
        if provider == "tavily" and isinstance(data, dict):
            for row in data.get("results", []):
                url = row.get("url", "")
                if public_url(url):
                    urls.add(url)
                    if web_evidence is not None:
                        web_evidence.append(WebEvidence(url=url, title=row.get("title", ""), text=row.get("content") or row.get("raw_content") or "", retrieved_at=now))
        if status != "ok":
            warnings.append(provider + ":" + status)
        logger.info("role=%s tool=%s provider=%s revision=%s status=%s duration_ms=%s", role, name, provider, revision, status, round((time.monotonic() - started) * 1000))
        return observation.model_dump(mode="json")

    async def mcp(name: str, provider: str, method: str, args: dict) -> dict:
        if method in ("get_offer_details", "get_rail_seatmap"):
            product = "rail" if method == "get_rail_seatmap" else args.get("product_type")
            ident = args.get("hotel_id") if product == "hotels" else args.get("offer_id")
            row = owned.get((product, ident))
            if row is None:
                return {"status": "forbidden"}
            if product != "hotels":
                args = {**args, "details_ref": row.get("details_ref") or row}
                if method == "get_rail_seatmap":
                    args.pop("offer_id", None)
        key = json.dumps([name, provider, method, args], sort_keys=True)
        if key in responses:
            return responses[key]
        result = await execute(name, provider, lambda: runtime_call(role, provider, method, args, env, frozenset(owned) | frozenset(("rail_ref", sha256(json.dumps(row.get("details_ref"), sort_keys=True).encode()).hexdigest()) for (product, _), row in owned.items() if product == "rail" and row.get("details_ref"))), method, args)
        responses[key] = result
        return result

    async def rest(name: str, provider: str, key_name: str | None, operation: Callable[[], Awaitable[httpx.Response | dict]], arguments: dict | None = None) -> dict:
        if name not in ALLOWED[role]:
            return {"status": "forbidden"}
        if key_name and not env.get(key_name):
            async def missing():
                return {"status": "missing_key"}
            return await execute(name, provider, missing, arguments=arguments)
        return await execute(name, provider, operation, arguments=arguments)

    @tool
    async def tavily_search(query: str) -> dict:
        """Search public context; prices and availability remain unverified."""
        return await rest("tavily_search", "tavily", "TAVILY_API_KEY", lambda: client.post(
            "https://api.tavily.com/search", headers={"Authorization": "Bearer " + env.get("TAVILY_API_KEY", "")},
            json={"query": query, "max_results": 5, "include_answer": False, "include_raw_content": True}), {"query": query})

    @tool
    async def tavily_extract(selected_urls: list[str]) -> dict:
        """Extract up to three public HTTPS URLs previously returned by this role's search."""
        if not 1 <= len(selected_urls) <= 3 or any(u not in urls or not public_url(u) for u in selected_urls):
            return {"status": "forbidden"}
        for url in selected_urls:
            try:
                addresses = await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(urlparse(url).hostname, 443, type=socket.SOCK_STREAM), timeout=3)
            except (OSError, TimeoutError):
                return {"status": "forbidden"}
            if not addresses or any(not ipaddress.ip_address(address[4][0]).is_global for address in addresses):
                return {"status": "forbidden"}
        return await rest("tavily_extract", "tavily", "TAVILY_API_KEY", lambda: client.post(
            "https://api.tavily.com/extract", headers={"Authorization": "Bearer " + env.get("TAVILY_API_KEY", "")}, json={"urls": selected_urls}), {"urls": selected_urls})

    selected = {"transport": transport_tools, "stays": stay_tools, "experience": experience_tools}[role](trip, client, env, evidence, mcp, rest, center)
    selected += [tavily_search, tavily_extract]
    if {t.name for t in selected} != ALLOWED[role]:
        raise ValueError("Role tool registry does not match allowlist")
    return selected
