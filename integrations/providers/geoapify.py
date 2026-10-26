import httpx
async def run(h):
 from integrations.core import ENV
 key=ENV.get('GEOAPIFY_API_KEY','')
 for case,cat,lon,lat in [('restaurants_adler','catering.restaurant',39.923,43.428),('hotels_adler','accommodation.hotel',39.923,43.428),('attractions_sochi','tourism.sights',39.723,43.585),('attractions_polyana','tourism.sights',40.2,43.68)]:
  await h.get('geoapify',case,'https://api.geoapify.com/v2/places',params={'apiKey':key,'categories':cat,'filter':f'circle:{lon},{lat},7000','limit':10,'lang':'ru'},required_key='GEOAPIFY_API_KEY',expected=lambda d:isinstance(d.get('features'),list))
 await h.get('geoapify','route_adler_polyana','https://api.geoapify.com/v1/routing',params={'apiKey':key,'waypoints':'43.428,39.923|43.68,40.2','mode':'drive','lang':'ru'},required_key='GEOAPIFY_API_KEY',expected=lambda d:bool(d.get('features')))

async def places(client: httpx.AsyncClient, key: str, lat: float, lon: float) -> httpx.Response:
 return await client.get('https://api.geoapify.com/v2/places', params={
  'apiKey':key, 'categories':'tourism.sights', 'filter':f'circle:{lon},{lat},7000', 'limit':10, 'lang':'ru'})
