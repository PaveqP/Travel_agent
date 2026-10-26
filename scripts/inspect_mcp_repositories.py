"""Read public upstream metadata/manifests only. Does not install or execute code."""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
REPOS = ('stufently/aviasales-mcp', 'airlabs-co/airlabs-mcp', 'mapbox/mcp-server', 'weatherapicom/weatherapi-mcp', 'amadeus4dev/amadeus-python')

async def main():
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        async def inspect(repo):
            out = {'repo': repo, 'checked_at': datetime.now(timezone.utc).isoformat(), 'executed': False, 'security_audit': 'not_performed'}
            try:
                r = await client.get('https://api.github.com/repos/' + repo)
                out['http_status'] = r.status_code
                if r.status_code != 200: return out
                d = r.json()
                out.update({k:d.get(k) for k in ('html_url','pushed_at','archived','default_branch')})
                out['license'] = (d.get('license') or {}).get('spdx_id')
                ref = d['default_branch']
                commit = await client.get(f'https://api.github.com/repos/{repo}/commits/{ref}')
                if commit.status_code == 200:
                    ref = commit.json()['sha']
                    out['commit'] = ref
                for filename in ('pyproject.toml','package.json'):
                    r = await client.get(f'https://raw.githubusercontent.com/{repo}/{ref}/{filename}')
                    if r.status_code == 200: out[filename] = r.text
            except Exception as exc:
                out['error_type'] = type(exc).__name__
            return out
        rows = await asyncio.gather(*(inspect(repo) for repo in REPOS))
    (ROOT/'reports/mcp_repository_inventory.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    for row in rows:
        print(json.dumps({k:v for k,v in row.items() if k not in ('package.json','pyproject.toml')},ensure_ascii=False))

if __name__ == '__main__':
    asyncio.run(main())
