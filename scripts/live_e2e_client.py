import argparse
import asyncio
import json
import re
import secrets
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path('/tmp/flinters-live-e2e')


def save_event(case: str, session: str, event: str, **fields) -> None:
    row = {'timestamp': datetime.now(timezone.utc).isoformat(), 'case_id': case,
           'session_id': session, 'event': event, **fields}
    with (PRIVATE / 'client_events.jsonl').open('a') as f:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', required=True, choices=['01', '02', '03', '04', '05'])
    parser.add_argument('--initial', action='store_true')
    parser.add_argument('--message')
    parser.add_argument('--select', action='store_true')
    parser.add_argument('--book', action='store_true')
    args = parser.parse_args()
    case = 'case_' + args.case
    path = PRIVATE / (case + '.json')
    session = json.loads(path.read_text()) if path.exists() else {}
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000', timeout=390,
                                headers={'X-E2E-Case': case}, cookies=session.get('cookies', {}),
                                follow_redirects=False) as client:
        if not session:
            response = await client.post('/api/auth/register', json={'name': 'QA ' + args.case,
                'email': 'qa-' + secrets.token_hex(6) + '@example.invalid', 'password': secrets.token_urlsafe(24)})
            response.raise_for_status()
            response = await client.post('/trips')
            response.raise_for_status()
            session = {'trip_id': response.json()['trip_id'], 'revision': 0, 'cookies': dict(client.cookies), 'turns': []}
            path.write_text(json.dumps(session))
        trip = session['trip_id']
        current = await client.get('/trips/' + trip)
        current.raise_for_status()
        state = current.json()
        message = args.message
        if args.initial:
            sections = re.split(r'\n## \d\d\.', (ROOT / 'test MVP/USE_CASES.md').read_text())
            message = re.search(r'Первое сообщение: «(.*?)»', sections[int(args.case)], re.S).group(1)
        if args.select or args.book:
            options = state.get('options', [])
            if not options:
                print('NO_OPTIONS: cannot select/book')
                return
            option = next((x for x in options if x['id'] == state.get('selected')), options[0])
            endpoint = f'/trips/{trip}/select/{option["id"]}?revision={state["revision"]}' if args.select else f'/trips/{trip}/bookings'
            payload = None if args.select else {'option_id': option['id'], 'revision': state['revision'],
                'confirm': True, 'idempotency_key': 'qa-' + args.case + '-' + secrets.token_hex(8), 'payment_method': 'card'}
            started_at = datetime.now(timezone.utc).isoformat()
            started = time.monotonic()
            response = await client.post(endpoint, json=payload) if payload else await client.post(endpoint)
            save_event(case, trip, 'user_action', action='select' if args.select else 'simulated_booking',
                timestamp_start=started_at, duration_ms=round((time.monotonic()-started)*1000),
                http_status=response.status_code)
            result = response.json()
            print(json.dumps({'http_status': response.status_code, **{k: result.get(k) for k in ['answer', 'detail', 'stage', 'status', 'selected', 'simulated', 'paid', 'reserved', 'message', 'payment']}}, ensure_ascii=False))
            session['last_action'] = {'action': 'select' if args.select else 'simulated_booking', 'http_status': response.status_code, 'response': response.json()}
            session.setdefault('actions', []).append({**session['last_action'], 'started_at': started_at, 'finished_at': datetime.now(timezone.utc).isoformat(), 'duration_ms': round((time.monotonic()-started)*1000)})
            if args.book:
                session['booking_action'] = session['last_action']
            path.write_text(json.dumps(session, ensure_ascii=False))
            return
        if not message:
            print(json.dumps(state, ensure_ascii=False)[:18000])
            return
        ledger = json.loads((PRIVATE / 'budget.json').read_text())
        if float(ledger['accounted_usd']) + float(ledger['pending_usd']) >= 4.50:
            raise RuntimeError('Global budget exhausted before user turn')
        number = len(session['turns']) + 1
        save_event(case, trip, 'user_message', number=number, text=message, revision=state.get('revision', 0))
        started_at = datetime.now(timezone.utc).isoformat()
        started = time.monotonic()
        response = await client.post('/trips/' + trip + '/messages', json={'message': message, 'revision': state.get('revision', 0)})
        duration = round((time.monotonic()-started)*1000)
        final = response.json() if response.status_code == 200 else {'error': response.status_code}
        if response.status_code != 200:
            recovered = await client.get('/trips/' + trip)
            if recovered.status_code == 200:
                final['recovered'] = recovered.json()
        turn = {'number': number, 'sent_at': started_at, 'finished_at': datetime.now(timezone.utc).isoformat(),
                'user': message, 'http_status': response.status_code, 'duration_ms': duration, 'response': final}
        session['turns'].append(turn)
        session['revision'] = final.get('revision', state.get('revision', 0))
        path.write_text(json.dumps(session, ensure_ascii=False))
        messages = final.get('messages', [])
        answer = final.get('answer') or next((m.get('text', m.get('content', '')) for m in reversed(messages) if m.get('role') in ('assistant', 'ai')), '')
        save_event(case, trip, 'assistant_response' if response.status_code == 200 else 'validation_error',
                   number=number, text=answer, duration_ms=duration, http_status=response.status_code)
        save_event(case, trip, 'workflow_complete', number=number, duration_ms=duration,
                   http_status=response.status_code, status=final.get('status'))
        print(json.dumps({'case': case, 'turn': number, 'http_status': response.status_code,
            'duration_ms': duration, 'answer': answer, 'status': final.get('status'),
            'constraints': final.get('constraints'), 'options': len(final.get('options', [])),
            'roles': {role: {'status': v.get('status'), 'warnings': v.get('warnings'),
                'candidates': len(v.get('candidates', []))} for role, v in final.get('results', {}).items()},
            'cards': len(final.get('cards', []))}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
