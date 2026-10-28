import argparse
import asyncio
import json
import logging
import sys
import time
from functools import partial
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from travel_agent.agents.model import create_model
from travel_agent.agents.supervisor.response import llm_presenter
from travel_agent.agents.research import research
from travel_agent.agents.transport.agent import run as run_transport
from travel_agent.agents.stays.agent import run as run_stays
from travel_agent.agents.experience.agent import run as run_experience
from travel_agent.agents.supervisor.agent import llm_decider, llm_planner
from travel_agent.prompts import read_prompts
from travel_agent.config import environment, settings
from travel_agent.graph import build_graph


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget-usd", required=True, type=Decimal)
    parser.add_argument("--output", default="/tmp/travel-live.json")
    parser.add_argument("--ski", action="store_true")
    parser.add_argument("--resume")
    parser.add_argument("--changes-only", action="store_true")
    parser.add_argument("--autonomous", action="store_true")
    parser.add_argument("--extended", action="store_true")
    parser.add_argument("--dialogue", action="store_true")
    parser.add_argument("--mixed", action="store_true")
    parser.add_argument("--repeat", type=int, choices=range(1, 4), default=1)
    args = parser.parse_args()
    if not 0 < args.budget_usd <= 3:
        raise ValueError("Authorized budget is at most $3")
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

    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("travel_agent.tools").setLevel(logging.INFO)
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
                model=create_model(config, client, max_tokens=2800, timeout=20),
                client=client,
                env=env,
                prompt=prompts[role],
                autonomous=args.autonomous, deadline=65,
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

        decide = llm_planner(create_model(config, client, max_tokens=2600, timeout=20), prompts["planner"]) if args.autonomous else llm_decider(model, prompts["supervisor"])

        async def trace_decision(state):
            decision = await decide(state)
            print(
                json.dumps(
                    {
                        "supervisor_calls_in_state": state.get("calls"),
                        "stage": state.get("stage"),
                        "action": decision.action,
                        "patch_fields": list(
                            decision.patch.model_dump(
                                exclude_none=True, exclude={"clear"}
                            )
                        ),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            return decision

        graph = build_graph(
            trace_decision,
            ({r: partial(run, r) for r in runners} if args.autonomous else run),
            InMemorySaver(),
            autonomous=args.autonomous,
            present=llm_presenter(
                create_model(config, client, max_tokens=3000, timeout=20), prompts["response"]
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
                "Хочу из Москвы в Сочи, двое взрослых, бюджет 100000 рублей. Цель — спокойный отдых и прогулки у моря.",
                "С 12 по 16 ноября 2026 года. Подбери разные варианты под мои пожелания.",
                "Сколько стоят согласованные билеты и проживание на человека? Ничего не меняй.",
                "Есть ли бассейн у согласованного отеля? Проверь в интернете, поездку не меняй.",
            ]
        if args.mixed:
            messages = [
                "Мы с девушкой хотим из Москвы в Сочи. Бюджет 100 тысяч рублей на двоих, включая дорогу и проживание. Хотим хороший отель, пару дней провести в горах, остальное время у моря, сходить в рестораны и посмотреть интересные места.",
                "С 12 по 17 ноября 2026 года. Подбери варианты под наши пожелания и программу по дням.",
            ]
        if args.extended:
            messages += [
                "Замени отель на Mirror Residence, билеты оставь прежними.",
                "Сдвинь поездку на 13–17 ноября 2026 года, оставь Mirror Residence.",
            ]
        if args.ski:
            messages = [
                'Хочу с девушкой на горнолыжку на неделю в декарбе',
                'планируем вызжать с Питера',
                'а есть вариант проживания максимально близкий к горнолыжному склону, к подъемникам, желательно с видом на горы, и хотелось бы поехать с 10 числа, подбери лучший вариант',
                'зачем ты мне дал рестораны, если мне необходимо подобрать ближайший отель к горнолыжному курорту с видом на горы, рассматривай даты переезда в диапазоне с 10 по 25 декабря',
            ]
        if args.resume and not args.ski:
            messages = [
                'Сколько стоят билеты и проживание в первом варианте на одного человека? Ничего не меняй.',
                'Есть ли бассейн у отеля из первого варианта? Проверь в интернете, поездку не меняй.',
                'Замени отель на Mirror Residence, билеты оставь прежними.',
                'Сдвинь поездку на 13–17 ноября 2026 года, оставь Mirror Residence.',
            ]
            if args.changes_only:
                messages = messages[2:]
        if args.resume and args.ski:
            messages = messages[-1:]
        for repetition in range(args.repeat):
            cfg = {
                "configurable": {"thread_id": f"live-smoke-{repetition}"},
                "recursion_limit": 32,
            }
            if args.resume:
                saved = json.loads(Path(args.resume).read_text())['results'][2 if args.ski else 1]
                seed = {k: v for k, v in saved.items() if k in ('constraints', 'revision', 'decision', 'results', 'options', 'answer', 'status', 'stage', 'choices', 'focus', 'cards', 'selected_transport', 'selected_stay') and v is not None}
                seed.update(autonomous=True, repair_decision=False, messages=[HumanMessage(content='Спланируй отдых у моря и в горах'), AIMessage(content=saved['answer'])])
                await graph.aupdate_state(cfg, seed)
            for message in messages:
                before = len(role_results)
                started = time.monotonic()
                result = await graph.ainvoke(
                    {
                        "messages": [HumanMessage(content=message)],
                        "calls": 0,
                        "attempts": [],
                    },
                    cfg,
                )
                transitions = []
                for _ in range(8):
                    if (
                        args.autonomous
                        or result.get("stage")
                        not in ("scenarios", "transport", "stays", "itinerary")
                        or not result.get("choices")
                        or result.get("pending_check_in")
                    ):
                        break
                    choice = next(
                        (c for c in result["choices"] if c.get("selectable")),
                        result["choices"][0],
                    )
                    transitions.append(
                        {
                            "stage": result["stage"],
                            "choice_id": choice["id"],
                            "revision": result["revision"],
                        }
                    )
                    result = await graph.ainvoke(
                        {"requested_choice": choice["id"], "calls": 0}, cfg
                    )
                record = {
                    k: result.get(k)
                    for k in [
                        "constraints",
                        "focus",
                        "cards",
                        "revision",
                        "decision",
                        "results",
                        "options",
                        "answer",
                        "status",
                        "stage",
                        "choices",
                        "feedback",
                        "selected",
                        "selected_transport",
                        "selected_stay",
                    ]
                }
                record.update(
                    seconds=round(time.monotonic() - started, 2),
                    repetition=repetition,
                    message=message,
                    transitions=transitions,
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
            if args.ski and args.resume:
                last = turns[-1]
                checks.append({'repetition': repetition, 'focus_stays': last.get('focus') == 'stays',
                    'only_hotel_search': set(last['delegated']) <= {'stays'},
                    'window': last['constraints']['date_from'] == '2026-12-10' and last['constraints']['date_to'] == '2026-12-25',
                    'preferences': set(last['constraints']['stay_preferences']) == {'near_lift', 'mountain_view'},
                    'real_hotel_cards': bool(last.get('cards'))})
                continue
            if args.ski:
                last = turns[-1]
                checks.append({
                    'repetition': repetition,
                    'clarify_origin_without_search': not turns[0]['delegated'],
                    'ski_intent_persisted': all(r['constraints']['holiday_type'] == 'ski' for r in turns),
                    'hotel_focus': all(r.get('focus') == 'stays' for r in turns[2:]),
                    'no_restaurant_search_for_hotel': all(set(r['delegated']) <= {'stays'} for r in turns[2:]),
                    'move_keeps_end': turns[2]['constraints']['start'] == '2026-12-10' and bool(turns[2]['constraints']['end']),
                    'range_keeps_week': last['constraints']['date_from'] == '2026-12-10' and last['constraints']['date_to'] == '2026-12-25' and bool(last['constraints']['nights'] or last['constraints']['duration_days']),
                    'preferences_persisted': set(last['constraints']['stay_preferences']) == {'near_lift', 'mountain_view'},
                    'hotel_offers': bool(last.get('cards')),
                })
                continue
            if args.resume:
                hotel, dates = turns[-2:]
                selected_hotel = next((o for o in hotel['options'] if o['id'] == hotel.get('selected') or o['stay']['id'] == hotel.get('selected_stay')), None)
                matches = 'mirror' in selected_hotel['stay']['name'].casefold() if selected_hotel else bool(hotel['options']) and all('mirror' in o['stay']['name'].casefold() for o in hotel['options'])
                checks.append({
                    'repetition': repetition,
                    'answer_without_search': args.changes_only or not turns[0]['delegated'] and turns[0]['decision']['action'] == 'answer',
                    'research_without_replanning': args.changes_only or not turns[1]['delegated'] and turns[1]['decision']['action'] == 'research' and turns[1]['options'] == turns[0]['options'],
                    'hotel_preserves_transport': 'transport' not in hotel['delegated'] and hotel['results']['transport'] == (seed['results']['transport'] if args.changes_only else turns[0]['results']['transport']),
                    'hotel_matches': matches,
                    'dates_refresh': set(dates['delegated']) == {'transport', 'stays', 'experience'} and bool(dates['options']),
                })
                continue
            checks.append(
                {
                    "repetition": repetition,
                    "clarified_without_search": not turns[0]["delegated"]
                    and turns[0]["status"] == "needs_input",
                    "full_plan": bool(turns[1]["options"])
                    and all(o["stay"] and o["transport"] for o in turns[1]["options"]),
                }
            )
            if args.mixed:
                areas = {
                    c.get("area")
                    for option in turns[1]["options"] or []
                    for day in option["days"]
                    for c in day["candidates"]
                }
                checks[-1]["scheduled_coast_and_mountains"] = (
                    "Красная Поляна" in areas
                    and bool(areas & {"Сочи", "Адлер", "Сириус"})
                )
            if args.dialogue:
                checks[-1].update(
                    scenario_chosen_before_search=args.autonomous or bool(turns[0]["transitions"])
                    and (args.autonomous or turns[0]["transitions"][0]["stage"] == "scenarios"),
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
                    and (any(option['stay'] and option['stay']['id'] == hotel_turn.get('selected_stay') and 'mirror' in option['stay']['name'].casefold() for option in hotel_turn['options'])
                         or all(option['stay'] and 'mirror' in option['stay']['name'].casefold() for option in hotel_turn['options'])),
                    dates_refresh=set(dates_turn["delegated"])
                    == {"transport", "stays", "experience"},
                    dates_match=dates_turn["constraints"]["start"] == "2026-11-13"
                    and dates_turn["constraints"]["end"] == "2026-11-17",
                    changed_plan=bool(dates_turn["options"])
                    and all(
                        o["stay"] and o["transport"] for o in dates_turn["options"]
                    ),
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
