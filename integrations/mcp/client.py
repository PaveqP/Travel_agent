import asyncio,time
from contextlib import asynccontextmanager
from datetime import timedelta
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from integrations.core import ENV,save,record,error_info

SERVERS={
 'geoapify':('https://api.geoapify.com/v1/mcp','GEOAPIFY_API_KEY'),
 'openweather_mcp':('https://mcp.openweathermap.org/mcp',None),
 'tutu':('https://mcp.tutu.ru/mcp',None),
 '2gis':('https://mcp-2gis.api.2gis.com/mcp','TWOGIS_API_KEY'),
 'liteapi':('https://mcp.liteapi.travel/api/mcp','LITEAPI_API_KEY'),
}
@asynccontextmanager
async def connection(provider):
 url,key=SERVERS[provider];headers={}
 if key and not ENV.get(key):raise ValueError('missing_key')
 if provider=='geoapify':headers={'x-api-key':ENV[key]}
 if provider=='2gis':headers={'Authorization':'Bearer '+ENV[key]}
 if provider=='liteapi':url+='?apiKey='+ENV[key]
 async with httpx.AsyncClient(timeout=60,headers=headers,follow_redirects=False) as client:
  async with streamable_http_client(url,http_client=client) as (read,write,_):
   async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=65)) as s:
    init=await s.initialize()
    yield s,init

async def discover(provider):
 t=time.perf_counter()
 try:
  async with asyncio.timeout(85):
   async with connection(provider) as (s,init):
    listing=await s.list_tools(); tools=listing.model_dump(mode='json');cursor=listing.nextCursor
    while cursor:
     listing=await s.list_tools(cursor=cursor);tools['tools']+=listing.model_dump(mode='json')['tools'];cursor=listing.nextCursor
    save(f'{provider}_mcp_schema.json',{'initialize':init.model_dump(mode='json'),'tools':tools['tools']})
    return record(provider,'mcp_discovery','ok',latency_ms=round((time.perf_counter()-t)*1000),tool_count=len(tools['tools']),tools=[x['name'] for x in tools['tools']])
 except Exception as e:return record(provider,'mcp_discovery','connection_error',latency_ms=round((time.perf_counter()-t)*1000),**error_info(e))

ALLOWED={
 '2gis':{'search_places','build_route','geocode_address','calculate_distance_matrix','server_info'},
 'geoapify':{'search_places','calculate_route','geocode_address','list_place_categories'},
 'liteapi':{'get_data_hotels','get_data_hotel','post_hotels_rates'},
 'tutu':{'search_avia','search_hotels','search_etrain','search_rail','get_offer_details','get_avia_instructions','get_hotels_instructions','get_etrain_instructions'}, 'openweather_mcp':set(),
}
async def call(provider,name,args,case=None):
 import jsonschema
 t=time.perf_counter();case=case or name
 if name not in ALLOWED.get(provider,set()):return record(provider,case,'blocked_tool',tool=name,reason='Not on read-only allowlist')
 try:
  async with asyncio.timeout(100):
   async with connection(provider) as (s,_):
    tools=await s.list_tools();tool=next(x for x in tools.tools if x.name==name)
    jsonschema.validate(args,tool.inputSchema)
    result=await s.call_tool(name,args)
    data=result.model_dump(mode='json')
    save(f'examples/{provider}__{case}.json',data)
    record(provider,case,'tool_error' if result.isError else 'ok',tool=name,request=args,latency_ms=round((time.perf_counter()-t)*1000),data=data,example=f'examples/{provider}__{case}.json')
    return data
 except Exception as e:return record(provider,case,'call_error',tool=name,request=args,latency_ms=round((time.perf_counter()-t)*1000),**error_info(e))
