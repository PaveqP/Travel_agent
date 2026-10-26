import argparse
import asyncio
import json
import sys
from functools import partial
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from travel_agent.agents.model import create_model
from travel_agent.agents.supervisor.response import llm_presenter
from travel_agent.agents.research import research
from travel_agent.agents.transport.agent import run as run_transport
from travel_agent.agents.stays.agent import run as run_stays
from travel_agent.agents.experience.agent import run as run_experience
from travel_agent.agents.supervisor.agent import llm_decider
from travel_agent.prompts import read_prompts
from travel_agent.config import environment, settings
from travel_agent.graph import build_graph


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget-usd", required=True, type=Decimal)
    parser.add_argument("--output", default="/tmp/travel-live.json")
    parser.add_argument("--extended", action="store_true")
    parser.add_argument("--dialogue", action="store_true")
    parser.add_argument("--repeat", type=int, choices=range(1, 4), default=1)
    args = parser.parse_args()
    if not 0 < args.budget_usd <= 1:
        raise ValueError("Authorized budget is at most $1")
    reserved = Decimal(0)
    spent = Decimal(0)
    calls = 0
    role_results = []
    pending = Decimal(0)

    def save_budget():
        Path(args.output + ".budget.json").write_text(
            json.dumps(
                {
                    "calls": calls,
                    "reserved_usd": str(reserved),
                    "reported_cost_usd": str(spent),
                    "pending_reserve_usd": str(pending),
                    "role_results": role_results,
                },
                ensure_ascii=False,
            )
        )

    async def guard(request: httpx.Request):
        nonlocal reserved, calls, pending
        if request.url.path.endswith("/chat/completions"):
            body = json.loads(request.content)
            reserve = Decimal(
                len(request.content)
                + body.get("max_tokens", body.get("max_completion_tokens", 1800))
            ) * Decimal("0.000002")
            if spent + pending + reserve > args.budget_usd:
                raise RuntimeError("Live cost guard reached")
            reserved += reserve
            pending += reserve
            request.extensions["cost_reserve"] = reserve
            calls += 1
            save_budget()

    async def usage(response: httpx.Response):
        nonlocal spent, pending
        if response.request.url.path.endswith("/chat/completions"):
            await response.aread()
            reserve = response.request.extensions.get("cost_reserve", Decimal(0))
            pending -= reserve
            if response.status_code == 200:
                spent += Decimal(
                    str(response.json().get("usage", {}).get("cost", reserve))
                )
            else:
                spent += reserve
            save_budget()

    env = environment()
    config = settings(env)
    results = []
    async with httpx.AsyncClient(
        timeout=45,
        follow_redirects=False,
        event_hooks={"request": [guard], "response": [usage]},
    ) as client:
        model = create_model(config, client, max_tokens=4096)
        prompts = read_prompts()
        runners = {
            "transport": run_transport,
            "stays": run_stays,
            "experience": run_experience,
        }

        async def run(role, trip, revision, task, previous):
            result = await runners[role](
                trip,
                revision,
                task,
                previous,
                model=create_model(config, client),
                client=client,
                env=env,
                prompt=prompts[role],
            )
            role_results.append(result.model_dump(mode="json"))
            save_budget()
            print(
                json.dumps(
                    {
                        "role": role,
                        "status": result.status,
                        "tools": result.tool_calls,
                        "candidates": len(result.candidates),
                        "warnings": result.warnings,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            return result

        graph = build_graph(
            llm_decider(model, prompts["supervisor"]),
            run,
            InMemorySaver(),
            present=llm_presenter(
                create_model(config, client, max_tokens=4096), prompts["response"]
            ),
            research=partial(
                research,
                models={r: create_model(config, client) for r in runners},
                client=client,
                env=env,
                prompt=prompts["research"],
            ),
        )
        messages = [
            "Хочу из Москвы в Сочи, двое взрослых, бюджет 100000 рублей, интересуют море и прогулки.",
            "С 12 по 16 ноября 2026 года. Подбери варианты перелёта, отеля и прогулок.",
        ]
        if args.dialogue:
            messages = [
                "Хочу из Москвы в Сочи с 12 по 16 ноября 2026 года. Двое взрослых, бюджет 100000 рублей.",
                "Цель — спокойный отдых, гулять у моря. Подбери разные варианты.",
                "Сколько стоят согласованные билеты и проживание на человека? Ничего не меняй.",
                "Есть ли бассейн у согласованного отеля? Проверь в интернете, поездку не меняй.",
            ]
        if args.extended:
            messages += [
                "Замени отель на Mirror Residence, билеты оставь прежними.",
                "Сдвинь поездку на 13–17 ноября 2026 года, оставь Mirror Residence.",
            ]
        for repetition in range(args.repeat):
            cfg = {
                "configurable": {"thread_id": f"live-smoke-{repetition}"},
                "recursion_limit": 32,
            }
            for message in messages:
                before = len(role_results)
                result = await graph.ainvoke(
                    {
                        "messages": [HumanMessage(content=message)],
                        "calls": 0,
                        "attempts": [],
                    },
                    cfg,
                )
                for _ in range(5):
                    if result.get("stage") not in ("scenarios", "transport", "stays", "itinerary") or not result.get("choices") or result.get("pending_check_in"):
                        break
                    result = await graph.ainvoke({"requested_choice": result["choices"][0]["id"], "calls": 0}, cfg)
                record = {
                    k: result.get(k)
                    for k in [
                        "constraints",
                        "revision",
                        "decision",
                        "results",
                        "options",
                        "answer",
                        "status",
                        "stage",
                        "choices",
                        "selected_transport",
                        "selected_stay",
                    ]
                }
                record.update(
                    repetition=repetition,
                    message=message,
                    delegated=[r["role"] for r in role_results[before:]],
                )
                results.append(record)
                Path(args.output).write_text(
                    json.dumps(
                        {
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "results": results,
                            "calls": calls,
                            "reserved_usd": str(reserved),
                            "reported_cost_usd": str(spent),
                            "pending_reserve_usd": str(pending),
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                print(
                    json.dumps(
                        {
                            "repetition": repetition,
                            "answer": result.get("answer"),
                            "delegated": record["delegated"],
                            "options": len(result.get("options", [])),
                            "calls": calls,
                            "reserved_usd": str(reserved),
                            "reported_cost_usd": str(spent),
                            "pending_reserve_usd": str(pending),
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
        checks = []
        for repetition in range(args.repeat):
            turns = [r for r in results if r["repetition"] == repetition]
            checks.append(
                {
                    "repetition": repetition,
                    "clarified_without_search": not turns[0]["delegated"]
                    and turns[0]["status"] == "needs_input",
                    "full_plan": bool(turns[1]["options"])
                    and all(o["stay"] and o["transport"] for o in turns[1]["options"]),
                }
            )
            if args.dialogue:
                checks[-1].update(
                    purpose_clarified=not turns[0]["constraints"].get("purpose"),
                    natural_answer="Билеты и проживание:" in turns[1]["answer"]
                    and "known_subtotal" not in turns[1]["answer"],
                    comparison_without_search=not turns[2]["delegated"]
                    and turns[2]["revision"] == turns[1]["revision"],
                    research_without_replanning=not turns[3]["delegated"]
                    and turns[3]["decision"]["action"] == "research"
                    and turns[3]["options"] == turns[1]["options"],
                )
            if args.extended:
                hotel_turn = turns[4 if args.dialogue else 2]
                dates_turn = turns[5 if args.dialogue else 3]
                checks[-1].update(
                    hotel_preserves_transport="transport" not in hotel_turn["delegated"]
                    and bool((turns[1]["results"] or {}).get("transport"))
                    and (turns[1]["results"] or {}).get("transport")
                    == (hotel_turn["results"] or {}).get("transport"),
                    hotel_matches=bool(hotel_turn["options"])
                    and all(
                        option["stay"] and "mirror" in option["stay"]["name"].casefold()
                        for option in hotel_turn["options"]
                    ),
                    dates_refresh=set(dates_turn["delegated"])
                    == {"transport", "stays", "experience"},
                    dates_match=dates_turn["constraints"]["start"] == "2026-11-13"
                    and dates_turn["constraints"]["end"] == "2026-11-17",
                    changed_plan=bool(dates_turn["options"])
                    and all(o["stay"] and o["transport"] for o in dates_turn["options"]),
                )
        report = json.loads(Path(args.output).read_text())
        report["checks"] = checks
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(
            json.dumps(
                {"checks": checks, "reported_cost_usd": str(spent)}, ensure_ascii=False
            ),
            flush=True,
        )
        if any(
            not value
            for check in checks
            for key, value in check.items()
            if key != "repetition"
        ):
            raise SystemExit("Live acceptance failed; inspect the saved report")


if __name__ == "__main__":
    asyncio.run(main())
