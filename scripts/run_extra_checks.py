import sys,asyncio,json
from pathlib import Path
from urllib.parse import urlencode,urlparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from integrations.core import HTTP,RESULTS,save,record
from integrations.mcp.client import discover
async def main():
 h=HTTP()
 async def reads():
  q='[out:json][timeout:20];nwr["amenity"="restaurant"](around:2000,43.428,39.923);out center tags 10;'
  await h.get('overpass','restaurants_adler_vk','https://maps.mail.ru/osm/tools/overpass/api/interpreter',params={'data':q},expected=lambda d:isinstance(d.get('elements'),list))
  await h.get('osrm','route_adler_polyana_retry','https://router.project-osrm.org/route/v1/driving/39.923,43.428;40.2,43.68',params={'overview':'false','steps':'false'},expected=lambda d:d.get('code')=='Ok' and bool(d.get('routes')))
 try:await asyncio.gather(discover('tutu'),reads())
 finally:await h.close()
 params={'start-lat':43.428,'start-lon':39.923,'end-lat':43.68,'end-lon':40.2,'appmetrica_tracking_id':'25395763362139037','lang':'ru','ref':'flinters'}
 url='https://3.redirect.appmetrica.yandex.com/route?'+urlencode(params)
 record('yandex_go','deeplink','local_only',data={'url':url,'price':None,'availability':None},reason='Constructed from documented template; no order or purchase, application handoff not tested')
 save('extra_results.json',RESULTS)
asyncio.run(main())
