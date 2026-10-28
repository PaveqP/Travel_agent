import httpx

_STATIONS: dict[str, str] = {}
async def run(h):
 from integrations.core import ENV,START,record
 base='https://api.rasp.yandex-net.ru/v3.0/'
 headers={'Authorization':ENV.get('YANDEX_RASP_API_KEY','')}
 stations={}
 for name,lat,lon in [('sochi',43.59,39.728),('adler',43.448,39.907),('rosa',43.678,40.281)]:
  d=await h.get('yandex_rasp','stations_'+name,base+'nearest_stations/',params={'lat':lat,'lng':lon,'distance':7,'transport_types':'suburban','limit':10,'lang':'ru_RU'},headers=headers,required_key='YANDEX_RASP_API_KEY',expected=lambda d:isinstance(d.get('stations'),list))
  if isinstance(d,dict) and d.get('stations'):
   candidates=d['stations']; target={'sochi':'сочи','adler':'адлер','rosa':'роза хутор'}[name]
   match=next((x for x in candidates if target in x.get('title','').lower()),None)
   if match:stations[name]=match['code']
 for case,src,dst in [('sochi_adler','sochi','adler'),('adler_rosa','adler','rosa'),('sochi_rosa','sochi','rosa')]:
  if src in stations and dst in stations:
   await h.get('yandex_rasp',case,base+'search/',params={'from':stations[src],'to':stations[dst],'date':str(START),'transport_types':'suburban','limit':20,'transfers':'true','result_timezone':'Europe/Moscow'},headers=headers,required_key='YANDEX_RASP_API_KEY',expected=lambda d:isinstance(d.get('segments'),list))
  else:record('yandex_rasp',case,'dependency_missing',reason='Station ID not resolved; no fabricated station codes')

async def schedule(client: httpx.AsyncClient, key: str, origin: str, destination: str, day: str,
                   transport_type: str = 'suburban', result_timezone: str | None = None) -> httpx.Response:
 params = {'from':origin, 'to':destination, 'date':day, 'transport_types':transport_type,
           'limit':20, 'transfers':'true'}
 if result_timezone:
  params['result_timezone'] = result_timezone
 async def station(value: str) -> str:
  if len(value) > 1 and value[0] in ('s', 'c') and value[1:].isdigit():
   return value
  if _STATIONS:
   return _STATIONS.get(value.casefold(), value)
  response = await client.get('https://api.rasp.yandex-net.ru/v3.0/stations_list/',
   params={'lang':'ru_RU','format':'json'}, headers={'Authorization':key})
  response.raise_for_status()
  for country in response.json().get('countries', []):
   for region in country.get('regions', []):
    for settlement in region.get('settlements', []):
     code = settlement.get('codes', {}).get('yandex_code')
     if code:
      _STATIONS.setdefault(settlement.get('title', '').casefold(), code)
  return _STATIONS.get(value.casefold(), value)
 params['from'], params['to'] = await station(origin), await station(destination)
 return await client.get('https://api.rasp.yandex-net.ru/v3.0/search/', params=params, headers={'Authorization':key})
