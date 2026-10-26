import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from travel_agent.agents import create_model, read_prompts, run_specialist
from travel_agent.config import environment, settings
from travel_agent.graph import build_graph, llm_decider


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--budget-usd', required=True, type=Decimal)
    parser.add_argument('--output', default='/tmp/travel-live.json')
    parser.add_argument('--extended', action='store_true')
    args = parser.parse_args()
    if not 0 < args.budget_usd <= 1:
        raise ValueError('Authorized budget is at most $1')
    reserved = Decimal(0)
    spent = Decimal(0)
    calls = 0
    role_results = []
    pending = Decimal(0)

    def save_budget():
        Path(args.output+'.budget.json').write_text(json.dumps({'calls': calls, 'reserved_usd': str(reserved), 'reported_cost_usd': str(spent), 'role_results': role_results}, ensure_ascii=False))

    async def guard(request: httpx.Request):
        nonlocal reserved, calls, pending
        if request.url.path.endswith('/chat/completions'):
            body = json.loads(request.content)
            reserve = Decimal(len(request.content)+body.get('max_tokens', body.get('max_completion_tokens', 1800)))*Decimal('0.000002')
            if spent+pending+reserve > args.budget_usd:
                raise RuntimeError('Live cost guard reached')
            reserved += reserve
            pending += reserve
            request.extensions['cost_reserve'] = reserve
            calls += 1
            save_budget()

    async def usage(response: httpx.Response):
        nonlocal spent, pending
        if response.request.url.path.endswith('/chat/completions'):
            await response.aread()
            reserve = response.request.extensions.get('cost_reserve', Decimal(0))
            pending -= reserve
            if response.status_code == 200:
                spent += Decimal(str(response.json().get('usage', {}).get('cost', reserve)))
            else:
                spent += reserve
            save_budget()

    env = environment()
    config = settings(env)
    results = []
    async with httpx.AsyncClient(timeout=45, follow_redirects=False, event_hooks={'request': [guard], 'response': [usage]}) as client:
        model = create_model(config, client)
        prompts = read_prompts()
        specialist = partial(run_specialist, model=model, client=client, env=env, prompts=prompts)

        async def run(role, trip, revision, task, previous):
            result = await specialist(role, trip, revision, task, previous=previous)
            role_results.append(result.model_dump(mode='json'))
            save_budget()
            print(json.dumps({'role': role, 'status': result.status, 'tools': result.tool_calls, 'candidates': len(result.candidates), 'warnings': result.warnings}, ensure_ascii=False), flush=True)
            return result

        graph = build_graph(llm_decider(model, prompts['supervisor']), run, InMemorySaver())
        cfg = {'configurable': {'thread_id': 'live-smoke'}, 'recursion_limit': 32}
        messages = ['Хочу из Москвы в Сочи, двое взрослых, бюджет 100000 рублей, интересуют море и прогулки.',
                        'С 12 по 16 ноября 2026 года. Подбери варианты перелёта, отеля и прогулок.']
        if args.extended:
            messages += ['Замени отель на Mirror Residence, билеты оставь прежними.',
                         'Сдвинь поездку на 13–17 ноября 2026 года, оставь Mirror Residence.']
        for message in messages:
            result = await graph.ainvoke({'messages': [HumanMessage(content=message)], 'calls': 0, 'attempts': []}, cfg)
            results.append({k: result.get(k) for k in ['constraints', 'revision', 'decision', 'results', 'options', 'answer']})
            Path(args.output).write_text(json.dumps({'created_at': datetime.now(timezone.utc).isoformat(), 'results': results,
                                                    'calls': calls, 'reserved_usd': str(reserved), 'reported_cost_usd': str(spent)}, ensure_ascii=False, indent=2))
            print(json.dumps({'answer': result.get('answer'), 'options': len(result.get('options', [])), 'calls': calls,
                              'reserved_usd': str(reserved), 'reported_cost_usd': str(spent)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
