import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from travel_agent.config import environment
from travel_agent.schemas import TripConstraints
from travel_agent.tools import build_tools


async def main() -> None:
    parser = argparse.ArgumentParser(description='Explicit read-only provider smoke, no LLM calls')
    parser.add_argument('--read-only', action='store_true', required=True)
    parser.add_argument('--output', default='/tmp/travel-sources.json')
    args = parser.parse_args()
    env = environment()
    trip = TripConstraints(origin='Москва', start='2026-11-12', end='2026-11-16', adults=2)
    results = []
    async with httpx.AsyncClient(timeout=35, follow_redirects=False) as client:
        cases = [('stays', 'search_hotels', {}, trip.model_copy(update={'destination': 'Адлер'})),
                 ('stays', 'search_hotels', {}, trip.model_copy(update={'destination': 'Красная Поляна'})),
                 ('transport', 'search_flights', {}, TripConstraints(origin='Москва', start='2026-11-13', end='2026-11-17', adults=2)),
                 ('transport', 'yandex_schedule', {'origin': 'Адлер', 'destination': 'Роза Хутор'}, trip),
                 ('transport', 'cached_flights', {'origin_iata': 'MOW'}, trip)]
        cases += [('experience', name, {}, trip) for name in ('search_places', 'geoapify_places', 'weather', 'events', 'attractions')]
        cases += [('stays', 'tavily_search', {'query': 'Сочи'}, trip)]
        for role, name, arguments, constraints in cases:
            evidence = {}; warnings = []; counts = {'tools': 0}
            tools = build_tools(role, constraints, 1, client, env, evidence, warnings, counts)
            result = await next(t for t in tools if t.name == name).ainvoke(arguments)
            record = {'role': role, 'tool': name, 'destination': constraints.destination, 'start': str(constraints.start),
                      'status': result['status'], 'candidates': len(evidence), 'warnings': warnings,
                      'evidence': [c.model_dump(mode='json') for c in evidence.values()]}
            results.append(record)
            Path(args.output).write_text(json.dumps({'created_at': datetime.now(timezone.utc).isoformat(), 'results': results}, ensure_ascii=False, indent=2))
            print(json.dumps({k: v for k, v in record.items() if k != 'evidence'}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
