from integrations.core import ENV
async def run(h):
 await h.get('ors','route_adler_polyana','https://api.openrouteservice.org/v2/directions/driving-car',params={'start':'39.923,43.428','end':'40.2,43.68'},headers={'Authorization':ENV.get('ORS_API_KEY','')},required_key='ORS_API_KEY',expected=lambda d:bool(d.get('features')))
