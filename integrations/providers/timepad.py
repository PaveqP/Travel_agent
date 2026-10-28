import httpx
async def run(h):
 from integrations.core import ENV,START,END
 await h.get('timepad','events_sochi','https://api.timepad.ru/v1/events',params={'cities':'Сочи','starts_at_min':str(START)+'T00:00:00+03:00','starts_at_max':str(END)+'T23:59:59+03:00','limit':10,'fields':'location,description_short','sort':'+starts_at'},headers={'Authorization':'Bearer '+ENV.get('TIMEPAD_TOKEN','')},required_key='TIMEPAD_TOKEN',expected=lambda d:isinstance(d.get('values'),list))

async def events(client: httpx.AsyncClient, key: str, start: str, end: str, city: str = 'Сочи',
                 timezone_name: str | None = None) -> httpx.Response:
 from datetime import date, datetime, time, timedelta, timezone
 from zoneinfo import ZoneInfo
 if timezone_name:
  zone = ZoneInfo(timezone_name)
  lower = datetime.combine(date.fromisoformat(start), time.min, zone).isoformat()
  upper = datetime.combine(date.fromisoformat(end), time.max, zone).isoformat()
 else:
  lower = datetime.combine(date.fromisoformat(start)-timedelta(days=1), time.min, timezone.utc).isoformat()
  upper = datetime.combine(date.fromisoformat(end)+timedelta(days=1), time.max, timezone.utc).isoformat()
 return await client.get('https://api.timepad.ru/v1/events', params={
  'cities':city, 'starts_at_min':lower, 'starts_at_max':upper,
  'limit':10, 'fields':'location,description_short', 'sort':'+starts_at'}, headers={'Authorization':'Bearer '+key})
