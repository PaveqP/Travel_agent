import sys,asyncio,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from integrations.core import HTTP,ENV,START,END,RESULTS,save,record
from integrations.mcp.client import call
async def yandex(h):
 stations={};base='https://api.rasp.yandex-net.ru/v3.0/';headers={'Authorization':ENV.get('YANDEX_RASP_API_KEY','')}
 for name,lat,lon,target in [('sochi',43.59,39.728,'сочи'),('adler',43.448,39.907,'адлер'),('rosa',43.678,40.281,'роза хутор')]:
  d=await h.get('yandex_rasp','stations_all_'+name,base+'nearest_stations/',params={'lat':lat,'lng':lon,'distance':5,'limit':50,'transport_types':'train,suburban','lang':'ru_RU'},headers=headers,expected=lambda d:isinstance(d.get('stations'),list))
  for x in d.get('stations',[]) if isinstance(d,dict) else []:
   if target in x.get('title','').lower():stations[name]=x['code'];break
 for case,src,dst in [('sochi_adler','sochi','adler'),('adler_rosa','adler','rosa'),('sochi_rosa','sochi','rosa')]:
  if src in stations and dst in stations:
   await h.get('yandex_rasp',case+'_resolved',base+'search/',params={'from':stations[src],'to':stations[dst],'date':str(START),'limit':30,'transfers':'true','result_timezone':'Europe/Moscow'},headers=headers,expected=lambda d:isinstance(d.get('segments'),list))
  else:record('yandex_rasp',case+'_resolved','dependency_missing',reason='Station ID not resolved')
async def lite(h):
 if not ENV.get('LITEAPI_API_KEY','').startswith('sand_'):return
 for name,city,country,currency in [('sochi_usd','Sochi','RU','USD'),('control_boston','Boston','US','USD')]:
  await h.get('liteapi','rates_'+name,'https://api.liteapi.travel/v3.0/hotels/rates',method='POST',headers={'X-API-Key':ENV['LITEAPI_API_KEY']},body={'countryCode':country,'cityName':city,'occupancies':[{'adults':2}],'currency':currency,'guestNationality':country,'checkin':str(START),'checkout':str(END),'timeout':6,'limit':10,'maxRatesPerHotel':1},expected=lambda d:isinstance(d.get('data'),list))
async def near(h):
 d=json.loads(Path('reports/examples/liteapi__catalog_polyana.json').read_text())
 hotel=d['data'][0];lat,lon=hotel['latitude'],hotel['longitude']
 await h.get('geoapify','restaurants_near_hotel','https://api.geoapify.com/v2/places',params={'apiKey':ENV['GEOAPIFY_API_KEY'],'categories':'catering.restaurant','filter':f'circle:{lon},{lat},1000','limit':10,'lang':'ru'},expected=lambda d:isinstance(d.get('features'),list))
 await call('2gis','search_places',{'query':'Рестораны','latitude':lat,'longitude':lon,'radius':1000,'page_size':10},'restaurants_near_hotel')
async def other(h):
 await h.get('timepad','events_sochi_tickets','https://api.timepad.ru/v1/events',params={'cities':'Сочи','starts_at_min':str(START)+'T00:00:00+03:00','starts_at_max':str(END)+'T23:59:59+03:00','limit':10,'fields':'location,ticket_types','sort':'+starts_at'},headers={'Authorization':'Bearer '+ENV['TIMEPAD_TOKEN']},expected=lambda d:isinstance(d.get('values'),list))
 q='[out:json][timeout:20];nwr["amenity"="restaurant"](around:2000,43.428,39.923);out center tags 10;'
 await h.get('overpass','restaurants_adler_fallback','https://overpass.private.coffee/api/interpreter',params={'data':q},expected=lambda d:isinstance(d.get('elements'),list))
 await h.get('openmeteo_marine','coast_retry','https://marine-api.open-meteo.com/v1/marine',params={'latitude':43.5,'longitude':39.6,'hourly':'wave_height,wave_period,wave_direction','forecast_days':3},expected=lambda d:'hourly' in d)
async def main():
 h=HTTP()
 try:await asyncio.gather(yandex(h),lite(h),near(h),other(h))
 finally:await h.close();save('followup_results.json',RESULTS)
asyncio.run(main())
