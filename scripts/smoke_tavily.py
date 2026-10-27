import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from travel_agent.config import environment
from travel_agent.schemas import TripConstraints
from travel_agent.tools import build_tools


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Isolated read-only Tavily Search and Extract; no LLM, MCP or trip workflow"
    )
    parser.add_argument("--read-only", required=True, action="store_true")
    parser.add_argument("--output", default="/tmp/tavily-smoke.json")
    args = parser.parse_args()
    env = environment()
    calls = []
    results = []

    async def guard(request: httpx.Request) -> None:
        if request.url.host != "api.tavily.com" or request.url.path not in (
            "/search",
            "/extract",
        ):
            raise RuntimeError("Unexpected network operation in isolated Tavily test")
        calls.append(request.url.path)

    async with httpx.AsyncClient(
        timeout=35, follow_redirects=False, event_hooks={"request": [guard]}
    ) as client:
        for role, query in (
            (
                "transport",
                "Международный аэропорт Сочи общественный транспорт как добраться",
            ),
            ("stays", "Mirror Residence Сочи официальный сайт услуги"),
            ("experience", "Сочинский Дендрарий официальный сайт часы работы"),
        ):
            evidence, sources, warnings = {}, [], []
            tools = {
                t.name: t
                for t in build_tools(
                    role,
                    TripConstraints(),
                    0,
                    client,
                    env,
                    evidence,
                    warnings,
                    {"tools": 0},
                    web_evidence=sources,
                )
            }
            started = monotonic()
            search = await tools["tavily_search"].ainvoke({"query": query})
            search_rows = search.get("results", [])
            urls = list(
                dict.fromkeys(row["url"] for row in search_rows if row.get("text"))
            )[:3]
            search_time = round(monotonic() - started, 2)
            extract = {"status": "not_run", "results": []}
            extract_time = 0
            before = len(sources)
            if urls:
                started = monotonic()
                extract = await tools["tavily_extract"].ainvoke({"selected_urls": urls})
                extract_time = round(monotonic() - started, 2)
            row = {
                "role": role,
                "query": query,
                "search_status": search["status"],
                "search_results": len(search_rows),
                "search_seconds": search_time,
                "extract_status": extract["status"],
                "extract_seconds": extract_time,
                "requested_urls": urls,
                "extracted": [
                    {"url": item["url"], "text_characters": len(item.get("text", ""))}
                    for item in extract.get("results", [])
                ],
                "stored_extracted_sources": len(sources) - before,
                "catalog_only": all(
                    c.price is None and c.source.evidence == "catalog"
                    for c in evidence.values()
                ),
                "skipped_urls": extract.get("skipped_urls", []),
                "warnings": warnings,
            }
            row["passed"] = (
                row["search_status"] == "ok"
                and row["extract_status"] == "ok"
                and row["stored_extracted_sources"] > 0
                and all(item["text_characters"] >= 100 for item in row["extracted"])
                and row["catalog_only"]
            )
            results.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "Isolated tools only; no LLM, MCP or trip flow",
        "requests": calls,
        "results": results,
        "passed": all(r["passed"] for r in results),
    }
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if env.get("TAVILY_API_KEY") and env["TAVILY_API_KEY"] in serialized:
        raise RuntimeError("Secret detected in report")
    Path(args.output).write_text(serialized + "\n")
    if not report["passed"]:
        raise SystemExit("Isolated Tavily acceptance failed; inspect report")


if __name__ == "__main__":
    asyncio.run(main())
