import sys,asyncio
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from integrations.core import ENV,START,END,RESULTS,save,record
from integrations.mcp.client import call,discover
async def two_gis():
 for case,q,lat,lon in [('restaurants_adler','Рестораны',43.428,39.923),('hotels_adler','Отели',43.428,39.923),('attractions_sochi','Достопримечательности',43.585,39.723),('hotels_polyana','Отели',43.68,40.2)]:
  await call('2gis','search_places',{'query':q,'latitude':lat,'longitude':lon,'radius':7000,'page_size':10,'locale':'ru_RU'},case)
 await call('2gis','build_route',{'points':[{'lat':43.428,'lon':39.923},{'lat':43.68,'lon':40.2}],'transport':'driving'},'route_adler_polyana')
async def geo():
 await call('geoapify','search_places',{'category':'catering.restaurant','lat':43.428,'lon':39.923,'radius_meters':5000,'limit':10,'lang':'ru'},'mcp_restaurants_adler')
 await call('geoapify','calculate_route',{'waypoints':[{'lat':43.428,'lon':39.923},{'lat':43.68,'lon':40.2}],'mode':'drive'},'mcp_route_adler_polyana')
async def lite():
 # Refresh unmodified JSON Schemas after scrubber fix; no booking calls.
 await discover('liteapi')
 if not ENV.get('LITEAPI_API_KEY','').startswith('sand_'):
  record('liteapi','mcp_search','skipped_cost_guard',reason='Only sandbox key allowed');return
 await call('liteapi','get_data_hotels',{'countryCode':'RU','cityName':'Sochi','limit':10},'mcp_catalog_sochi')
 await call('liteapi','post_hotels_rates',{'countryCode':'RU','cityName':'Sochi','occupancies':[{'adults':2}],'currency':'RUB','guestNationality':'RU','checkin':str(START),'checkout':str(END),'limit':10,'timeout':6},'mcp_rates_sochi')
async def main():
 await asyncio.gather(two_gis(),geo(),lite())
 save('mcp_call_results.json',RESULTS)
asyncio.run(main())
