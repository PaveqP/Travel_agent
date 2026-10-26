import sys,asyncio,time,json,os
from pathlib import Path
from datetime import timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
import jsonschema
from integrations.core import ENV,ROOT,START,RESULTS,save,record,error_info
async def main():
 exe=ROOT/'.mcp-venv/bin/python'
 if not exe.exists():record('aviasales_community','mcp','not_installed',reason='Run scripts/setup_community_mcp.py');save('community_mcp_results.json',RESULTS);return
 params=StdioServerParameters(command=str(exe),args=['-m','aviasales_mcp.server'],cwd='/tmp',env={'PATH':str(exe.parent)+':/usr/bin:/bin','AVIASALES_API_TOKEN':ENV['TRAVELPAYOUTS_TOKEN'],'AVIASALES_PARTNER_ID':ENV.get('TRAVELPAYOUTS_MARKER',''),'AVIASALES_MARKET':'ru','LOG_LEVEL':'CRITICAL','FASTMCP_SHOW_CLI_BANNER':'false'})
 start=time.perf_counter()
 try:
  with open(os.devnull,'w') as err:
   async with asyncio.timeout(70):
    async with stdio_client(params,errlog=err) as (read,write):
     async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=40)) as s:
      init=await s.initialize();listing=await s.list_tools()
      save('aviasales_community_mcp_schema.json',{'initialize':init.model_dump(mode='json'),'tools':[t.model_dump(mode='json') for t in listing.tools]})
      record('aviasales_community','mcp_discovery','ok',tool_count=len(listing.tools),latency_ms=round((time.perf_counter()-start)*1000))
      args={'origin':'MOW','destination':'AER','departure_at':str(START),'one_way':True,'adults':2,'limit':3,'currency':'rub','market':'ru'}
      tool=next(t for t in listing.tools if t.name=='search_flights');jsonschema.validate(args,tool.inputSchema)
      start=time.perf_counter();res=await s.call_tool('search_flights',args);data=res.model_dump(mode='json')
      save('examples/aviasales_community__search_flights.json',data)
      record('aviasales_community','search_flights','tool_error' if res.isError else 'ok',tool='search_flights',request=args,latency_ms=round((time.perf_counter()-start)*1000),data=data)
 except Exception as e:record('aviasales_community','mcp','connection_error',**error_info(e))
 save('community_mcp_results.json',RESULTS)
asyncio.run(main())
