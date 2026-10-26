"""Safe stage-1 inventory. A single LLM call requires explicit --llm-smoke."""
from __future__ import annotations
import argparse
import importlib.metadata
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--llm-smoke', action='store_true', help='One potentially billable 16-output-token request; no retries')
    args = parser.parse_args()
    env = dotenv_values(ROOT / '.env', interpolate=False)
    result = {
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'stage': 1, 'python': platform.python_version(),
        'executable': sys.executable, 'virtualenv': sys.prefix != sys.base_prefix,
        'dependencies': {},
        'env_presence': {k: bool(v) for k, v in env.items()},
        'travel_api_tests': 'not_started_awaiting_user_confirmation',
    }
    for name in ('httpx', 'python-dotenv', 'pydantic', 'mcp'):
        try: result['dependencies'][name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: result['dependencies'][name] = None
    base = (env.get('BASE_URL') or '').rstrip('/')
    url = urlsplit(base)
    # Restrict credentials to the existing provider, HTTPS, no redirects or URL credentials.
    if url.scheme != 'https' or url.hostname != 'openrouter.ai' or url.path != '/api/v1' or url.username or url.password or url.query or url.fragment:
        result['llm'] = {'status': 'skipped_unexpected_base_url'}
    else:
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            try:
                start = time.perf_counter()
                r = client.get(base + '/models')
                result['internet'] = {'host': url.hostname, 'http_status': r.status_code, 'latency_ms': round((time.perf_counter()-start)*1000)}
                model = next((m for m in r.json().get('data', []) if m.get('id') == env.get('MODEL')), None) if r.status_code == 200 else None
                result['model_metadata'] = {'found': model is not None, 'pricing_usd_per_token': model.get('pricing') if model else None, 'supported_parameters': model.get('supported_parameters') if model else None}
                if args.llm_smoke and all(env.get(k) for k in ('MODEL','TOKEN','BASE_URL')):
                    start = time.perf_counter()
                    r = client.post(base + '/chat/completions', headers={'Authorization': 'Bearer ' + env['TOKEN']}, json={'model': env['MODEL'], 'messages':[{'role':'user','content':'Reply with exactly OK.'}], 'max_tokens':16})
                    data = r.json()
                    choices = data.get('choices') or []
                    content = (choices[0].get('message', {}).get('content') or '') if choices else ''
                    usage = data.get('usage') or {}
                    result['llm'] = {'protocol':'chat_completions', 'http_status':r.status_code, 'latency_ms':round((time.perf_counter()-start)*1000), 'valid_choices':bool(choices), 'nonempty_content':bool(content.strip()), 'reply_is_ok': content.strip() == 'OK', 'finish_reason':choices[0].get('finish_reason') if choices else None, 'usage':{k:usage[k] for k in ('prompt_tokens','completion_tokens','total_tokens','cost') if k in usage}, 'responses_api':'documented_by_provider_not_tested', 'tool_calling':'not_tested'}
                else:
                    result['llm'] = {'status':'not_requested', 'responses_api':'not_tested'}
            except Exception as exc:
                # Never serialize exception text, response bodies, headers, URLs or prompts.
                result['error_type'] = type(exc).__name__
    path = ROOT / 'reports' / ('environment_smoke.json' if args.llm_smoke else 'environment_inventory.json')
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get('error_type') or (args.llm_smoke and not result.get('llm', {}).get('nonempty_content')) else 0

if __name__ == '__main__':
    raise SystemExit(main())
