import httpx
async def run(h):
 coords={'latitude':'43.585,43.68','longitude':'39.723,40.2','timezone':'Europe/Moscow'}
 await h.get('openmeteo_forecast','coast_mountains','https://api.open-meteo.com/v1/forecast',params={**coords,'daily':'temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max','forecast_days':7},expected=lambda d:isinstance(d,list) and all('daily' in x for x in d))
 await h.get('openmeteo_marine','coast','https://marine-api.open-meteo.com/v1/marine',params={'latitude':43.5,'longitude':39.6,'hourly':'wave_height,wave_period,wave_direction','forecast_days':3,'timezone':'Europe/Moscow'},expected=lambda d:'hourly' in d)
 await h.get('openmeteo_air','coast_mountains','https://air-quality-api.open-meteo.com/v1/air-quality',params={**coords,'hourly':'pm10,pm2_5,european_aqi','forecast_days':3},expected=lambda d:isinstance(d,list) and all('hourly' in x for x in d))
 await h.get('openmeteo_elevation','coast_mountains','https://api.open-meteo.com/v1/elevation',params={k:v for k,v in coords.items() if k!='timezone'},expected=lambda d:isinstance(d.get('elevation'),list))

async def forecast(client: httpx.AsyncClient, lat: float, lon: float) -> httpx.Response:
 return await client.get('https://api.open-meteo.com/v1/forecast', params={
  'latitude':lat, 'longitude':lon, 'timezone':'Europe/Moscow',
  'daily':'temperature_2m_max,temperature_2m_min,precipitation_sum', 'forecast_days':16})
