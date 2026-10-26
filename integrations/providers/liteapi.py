from integrations.core import ENV,START,END,record
async def run(h):
 key=ENV.get('LITEAPI_API_KEY','')
 if not key:record('liteapi','rest','missing_key');return
 # Only free sandbox credential for this research. Live financial exposure not authorized.
 if not key.startswith('sand_'):record('liteapi','rest','skipped_cost_guard',reason='Only sandbox sand_ key allowed');return
 headers={'X-API-Key':key}
 for case,lat,lon in [('sochi',43.585,39.723),('adler',43.428,39.923),('sirius',43.403,39.969),('polyana',43.68,40.2)]:
  d=await h.get('liteapi','catalog_'+case,'https://api.liteapi.travel/v3.0/data/hotels',headers=headers,params={'countryCode':'RU','latitude':lat,'longitude':lon,'radius':7000,'limit':10},expected=lambda d:isinstance(d.get('data'),list))
  ids=[x['id'] for x in d.get('data',[]) if 'id' in x] if isinstance(d,dict) else []
  body={'occupancies':[{'adults':2,'children':[]}],'currency':'RUB','guestNationality':'RU','checkin':str(START),'checkout':str(END),'timeout':6,'limit':10,'maxRatesPerHotel':2,'includeHotelData':True}
  if ids:body['hotelIds']=ids
  else:body.update(latitude=lat,longitude=lon,radius=7000)
  await h.get('liteapi','rates_'+case,'https://api.liteapi.travel/v3.0/hotels/rates',method='POST',headers=headers,body=body,expected=lambda d:isinstance(d.get('data'),list))
  if case=='sochi' and ids:
   await h.get('liteapi','hotel_details','https://api.liteapi.travel/v3.0/data/hotel',headers=headers,params={'hotelId':ids[0]},expected=lambda d:'data' in d)
