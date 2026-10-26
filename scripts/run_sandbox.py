"""LiteAPI documented sandbox control in Boston, never production or Sochi evidence."""
import sys,asyncio,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from integrations.core import ENV,START,END,RESULTS,save,record

def require_sandbox(key):
 if not key.startswith('sand_'):raise ValueError('Sandbox key required; production forbidden')
async def main():
 key=ENV.get('LITEAPI_API_KEY','')
 try:require_sandbox(key)
 except ValueError:
  record('liteapi','sandbox_booking','skipped_cost_guard',reason='Sandbox key required');save('sandbox_results.json',RESULTS);return
 async with httpx.AsyncClient(timeout=45,follow_redirects=False,headers={'X-API-Key':key}) as client:
  async def post(case,url,body):
   require_sandbox(key);t=time.perf_counter()
   try:
    r=await client.post(url,json=body);d=r.json()
    # Booking responses may contain guest/contact/payment details. Persist only minimal outcome.
    data=d if case=='sandbox_rates_boston' else {'error':d.get('error'),'data':{k:v for k,v in (d.get('data') or {}).items() if k in ['status','currency','price','hotelId','sandbox']}}
    record('liteapi',case,'ok' if r.is_success and not d.get('error') else 'provider_error',http_status=r.status_code,latency_ms=round((time.perf_counter()-t)*1000),sandbox=True,data=data,source=url)
    save('examples/liteapi__'+case+'.json',data);save('sandbox_results.json',RESULTS)
    return d
   except Exception as e:record('liteapi',case,'network_error',exception_type=type(e).__name__);return {}
  d=await post('sandbox_rates_boston','https://api.liteapi.travel/v3.0/hotels/rates',{'countryCode':'US','cityName':'Boston','checkin':str(START),'checkout':str(END),'occupancies':[{'adults':2}],'currency':'USD','guestNationality':'US','limit':1,'timeout':6})
  offers=[o for h in d.get('data',[]) for o in h.get('roomTypes',[]) if o.get('offerId')]
  if offers:
   pre=await post('sandbox_prebook_boston','https://book.liteapi.travel/v3.0/rates/prebook',{'offerId':offers[0]['offerId'],'usePaymentSdk':False})
   pid=(pre.get('data') or {}).get('prebookId')
   if pid:
    await post('sandbox_book_boston','https://book.liteapi.travel/v3.0/rates/book',{'prebookId':pid,'holder':{'firstName':'Sandbox','lastName':'Research','email':'sandbox@example.invalid','phone':''},'guests':[{'occupancyNumber':1,'firstName':'Sandbox','lastName':'Research','email':'sandbox@example.invalid'}],'payment':{'method':'ACC_CREDIT_CARD'}})
  else:record('liteapi','sandbox_prebook_boston','dependency_missing',reason='No sandbox offer')
 save('sandbox_results.json',RESULTS)
if __name__=='__main__':asyncio.run(main())
