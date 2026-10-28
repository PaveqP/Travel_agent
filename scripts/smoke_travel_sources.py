import argparse
import asyncio
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from travel_agent.config import environment
from travel_agent.engine import offer_card
from travel_agent.schemas import TripConstraints
from travel_agent.tools import build_tools


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Explicit read-only provider smoke, no LLM calls"
    )
    parser.add_argument("--read-only", action="store_true", required=True)
    parser.add_argument("--extended", action="store_true")
    parser.add_argument("--origin", default="Москва")
    parser.add_argument(
        "--start", type=date.fromisoformat, default=date.today() + timedelta(days=15)
    )
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--output", default="/tmp/travel-sources.json")
    args = parser.parse_args()
    env = environment()
    trip = TripConstraints(
        origin=args.origin,
        start=args.start,
        end=args.end or args.start + timedelta(days=4),
        adults=2,
    )
    results = []
    async with httpx.AsyncClient(timeout=35, follow_redirects=False) as client:
        cases = [
            (
                "stays",
                "search_hotels",
                {},
                trip.model_copy(update={"destination": area}),
            )
            for area in ("Адлер", "Красная Поляна")
        ]
        cases += [
            ("transport", "search_flights", {}, trip),
            (
                "transport",
                "yandex_schedule",
                {"origin": "Адлер", "destination": "Роза Хутор"},
                trip,
            ),
            ("transport", "cached_flights", {}, trip),
        ]
        cases += [
            ("experience", name, {}, trip)
            for name in (
                "search_places",
                "geoapify_places",
                "weather",
                "events",
                "attractions",
            )
        ]
        cases += [("stays", "tavily_search", {"query": "Сочи"}, trip)]
        if args.extended:
            cases += [
                ("transport", "search_trains", {"mode": mode}, trip)
                for mode in ("rail", "etrain")
            ]
        for role, name, arguments, constraints in cases:
            evidence, warnings, counts = {}, [], {"tools": 0}
            tools = {
                t.name: t
                for t in build_tools(
                    role, constraints, 1, client, env, evidence, warnings, counts
                )
            }

            async def invoke(tool_name: str, tool_args: dict) -> None:
                before = set(evidence)
                started = monotonic()
                result = await tools[tool_name].ainvoke(tool_args)
                cards = [
                    offer_card(c, constraints).model_dump(mode="json")
                    for c in evidence.values()
                ]
                context = result.get("context")
                record = {
                    "role": role,
                    "tool": tool_name,
                    "arguments": tool_args,
                    "destination": constraints.destination,
                    "start": str(constraints.start),
                    "end": str(constraints.end),
                    "status": result["status"],
                    "duration_seconds": round(monotonic() - started, 2),
                    "candidates": len(evidence),
                    "new_candidates": len(set(evidence) - before),
                    "selectable": sum(c["selectable"] for c in cards),
                    "areas": sorted({c.area for c in evidence.values() if c.area}),
                    "context_returned": bool(context),
                    "context_counts": {
                        k: len(v) for k, v in context.items() if isinstance(v, list)
                    }
                    if isinstance(context, dict)
                    else {},
                    "covers_trip": result.get("covers_trip"),
                    "warnings": list(warnings),
                    "evidence": [c.model_dump(mode="json") for c in evidence.values()],
                }
                results.append(record)
                Path(args.output).write_text(
                    json.dumps(
                        {
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "results": results,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                print(
                    json.dumps(
                        {k: v for k, v in record.items() if k != "evidence"},
                        ensure_ascii=False,
                    ),
                    flush=True,
                )

            await invoke(name, arguments)
            if not args.extended:
                continue
            if name in ("search_hotels", "search_flights") and evidence:
                await invoke(
                    "hotel_details" if role == "stays" else "transport_details",
                    {"source_id": next(iter(evidence))},
                )
            if name == "search_places":
                await invoke("search_places", {"query": "Рестораны", "area": "Сочи"})
                await invoke(
                    "search_places",
                    {"query": "Достопримечательности", "area": "Красная Поляна"},
                )
                if evidence:
                    await invoke("route", {"source_id": next(iter(evidence))})
            if name == "tavily_search" and env.get("TAVILY_API_KEY"):
                sources = [c.url for c in evidence.values() if c.url]
                if sources:
                    await invoke("tavily_extract", {"selected_urls": sources[:1]})


if __name__ == "__main__":
    asyncio.run(main())
