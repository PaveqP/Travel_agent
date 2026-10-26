from __future__ import annotations
import asyncio,json,logging,re,time
from datetime import datetime,timezone,date,timedelta
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode
import httpx
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[1]
ENV=dotenv_values(ROOT/'.env',interpolate=False)
logging.disable(logging.CRITICAL)
SECRETS=[v for k,v in ENV.items() if v and k not in ('MODEL','BASE_URL','ETG_BASE_URL') and len(v)>=5]
START=date.today()+timedelta(days=18)
END=START+timedelta(days=4)
SCENARIO={'departure':str(START),'return':str(END),'adults':2,'nights':4,'currency':'RUB','origin':'MOW','destination':'AER'}
RESULTS=[]
def clean(obj):
 if isinstance(obj,dict):
  return {str(k):('[REDACTED]' if not isinstance(v,(dict,list)) and re.search(r'^(authorization|api.?key|token|access.?token|secret|password|email|phone|contact_phone|contact_email|contacts|offerId|rateId|prebookId|bookingId)$',str(k),re.I) else clean(v)) for k,v in obj.items()}
 if isinstance(obj,list):return [clean(v) for v in obj]
 if isinstance(obj,str):
  if obj.lstrip().startswith(('{','[')):
   try:return json.dumps(clean(json.loads(obj)),ensure_ascii=False)
   except (ValueError,TypeError):pass
  for s in SECRETS:obj=obj.replace(s,'[REDACTED]')
  obj=re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}','[EMAIL]',obj)
  obj=re.sub(r'(?i)((?:api_?key|apikey|token|access_token|key)=)[^\s&"<>]+',r'\1[REDACTED]',obj)
  return obj
 return obj

def save(name,data):
 p=ROOT/'reports'/name;p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(clean(data),ensure_ascii=False,indent=2,default=str)+'\n')

def record(provider,case,status,**kw):
 r={'provider':provider,'case':case,'status':status,'retrieved_at':datetime.now(timezone.utc).isoformat(),**kw}
 RESULTS.append(clean(r));print(json.dumps(clean({k:v for k,v in r.items() if k not in ('data','schema','request')}),ensure_ascii=False),flush=True)
 save('latest_progress.json',RESULTS)
 return r

def error_info(exc):
 out={'exception_type':type(exc).__name__}
 if isinstance(exc,httpx.HTTPStatusError):out['http_status']=exc.response.status_code
 if isinstance(exc,BaseExceptionGroup):out['causes']=[error_info(e) for e in exc.exceptions]
 return out

class HTTP:
 def __init__(self):
  self.client=httpx.AsyncClient(timeout=httpx.Timeout(35,connect=15),follow_redirects=False,headers={'User-Agent':'FlintersTravelResearch/0.1 (noncommercial bounded integration test)'})
 async def close(self):await self.client.aclose()
 async def get(self,provider,case,url,*,params=None,headers=None,method='GET',body=None,expected=None,required_key=None):
  if required_key and not ENV.get(required_key):return record(provider,case,'missing_key',required_env=required_key)
  start=time.perf_counter();attempts=0
  try:
   while True:
    attempts+=1
    r=await self.client.request(method,url,params=params,headers=headers,json=body)
    # Only safe reads, bounded retries. Never retry monetary/mutating operations.
    if r.status_code in (429,502,503,504) and attempts<2:
     retry=r.headers.get('retry-after','1')
     if retry.isdigit() and int(retry)<=3:await asyncio.sleep(max(1,int(retry)));continue
    break
   try:data=r.json()
   except ValueError:data={'text':r.text[:20000]}
   status='ok' if r.is_success else {401:'unauthorized',403:'forbidden',429:'rate_limited',404:'not_found',402:'payment_required'}.get(r.status_code,'http_error')
   if status=='ok' and expected and not expected(data):status='schema_or_provider_error'
   record(provider,case,status,http_status=r.status_code,latency_ms=round((time.perf_counter()-start)*1000),attempts=attempts,source=url.split('?')[0],request=clean({'params':params,'body':body}),data=data,example=f'examples/{provider}__{case}.json')
   save(f'examples/{provider}__{case}.json',data)
   return data
  except Exception as e:return record(provider,case,'network_error',latency_ms=round((time.perf_counter()-start)*1000),attempts=attempts,**error_info(e))
