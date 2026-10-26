import httpx
async def run(h):
 from integrations.core import ENV,START,END
 await h.get('timepad','events_sochi','https://api.timepad.ru/v1/events',params={'cities':'Сочи','starts_at_min':str(START)+'T00:00:00+03:00','starts_at_max':str(END)+'T23:59:59+03:00','limit':10,'fields':'location,description_short','sort':'+starts_at'},headers={'Authorization':'Bearer '+ENV.get('TIMEPAD_TOKEN','')},required_key='TIMEPAD_TOKEN',expected=lambda d:isinstance(d.get('values'),list))

async def events(client: httpx.AsyncClient, key: str, start: str, end: str) -> httpx.Response:
 return await client.get('https://api.timepad.ru/v1/events', params={
  'cities':'Сочи', 'starts_at_min':start+'T00:00:00+03:00', 'starts_at_max':end+'T23:59:59+03:00',
  'limit':10, 'fields':'location,description_short', 'sort':'+starts_at'}, headers={'Authorization':'Bearer '+key})
