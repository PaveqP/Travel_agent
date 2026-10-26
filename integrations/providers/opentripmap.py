import httpx
async def run(h):
 from integrations.core import ENV
 for case,lon,lat in [('attractions_sochi',39.723,43.585),('attractions_polyana',40.2,43.68)]:
  d=await h.get('opentripmap',case,'https://api.opentripmap.com/0.1/ru/places/radius',params={'apikey':ENV.get('OPENTRIPMAP_API_KEY',''),'radius':5000,'lon':lon,'lat':lat,'limit':10,'format':'json'},required_key='OPENTRIPMAP_API_KEY',expected=lambda d:isinstance(d,list))
  if isinstance(d,list) and d and d[0].get('xid'):
   await h.get('opentripmap',case+'_details','https://api.opentripmap.com/0.1/ru/places/xid/'+d[0]['xid'],params={'apikey':ENV.get('OPENTRIPMAP_API_KEY','')},required_key='OPENTRIPMAP_API_KEY',expected=lambda d:'xid' in d)

async def places(client: httpx.AsyncClient, key: str, lat: float, lon: float) -> httpx.Response:
 return await client.get('https://api.opentripmap.com/0.1/ru/places/radius', params={
  'apikey':key, 'radius':5000, 'lon':lon, 'lat':lat, 'limit':10, 'format':'json'})
