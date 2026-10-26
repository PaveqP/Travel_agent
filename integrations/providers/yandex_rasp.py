import httpx
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

async def schedule(client: httpx.AsyncClient, key: str, origin: str, destination: str, day: str) -> httpx.Response:
 return await client.get('https://api.rasp.yandex-net.ru/v3.0/search/', params={
  'from':origin, 'to':destination, 'date':day, 'transport_types':'suburban',
  'limit':20, 'transfers':'true', 'result_timezone':'Europe/Moscow'}, headers={'Authorization':key})
