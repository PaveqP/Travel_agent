import argparse
import asyncio
import json
import os

import httpx


async def main() -> None:
    parser = argparse.ArgumentParser(description='Travel Agent CLI; API must be running')
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--trip')
    args = parser.parse_args()
    token = os.environ.get('TRAVEL_API_TOKEN', '')
    async with httpx.AsyncClient(base_url=args.url, headers={'Authorization': 'Bearer '+token}, timeout=450) as client:
        if args.trip:
            trip_id = args.trip
        else:
            response = await client.post('/trips')
            response.raise_for_status()
            trip_id = response.json()['trip_id']
        print('trip_id:', trip_id)
        print('Сообщение; /show; /select ID; /book ID KEY confirm; /quit')
        while True:
            text = await asyncio.to_thread(input, '> ')
            if text == '/quit':
                break
            current = await client.get('/trips/'+trip_id)
            current.raise_for_status()
            revision = current.json()['revision']
            if text == '/show':
                response = current
            elif text.startswith('/select '):
                response = await client.post(f'/trips/{trip_id}/select/{text.split()[1]}', params={'revision': revision})
            elif text.startswith('/book '):
                parts = text.split()
                if len(parts) != 4 or parts[-1] != 'confirm':
                    print('Используйте /book ID KEY confirm')
                    continue
                response = await client.post(f'/trips/{trip_id}/bookings', json={'option_id': parts[1], 'idempotency_key': parts[2], 'revision': revision, 'confirm': True})
            else:
                response = await client.post(f'/trips/{trip_id}/messages', json={'message': text, 'revision': revision})
            print(json.dumps(response.json(), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
