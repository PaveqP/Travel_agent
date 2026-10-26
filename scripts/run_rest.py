import sys,asyncio,importlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from integrations.core import HTTP,RESULTS,save,SCENARIO,record
MODULES=['geoapify','ors','opentripmap','openmeteo','travelpayouts','yandex_rasp','kudago','timepad','osm','cbr','liteapi']
async def main():
 h=HTTP();sem=asyncio.Semaphore(4)
 async def one(name):
  async with sem:
   try:await importlib.import_module('integrations.providers.'+name).run(h)
   except Exception as e:record(name,'adapter','adapter_error',exception_type=type(e).__name__)
 try:await asyncio.gather(*(one(m) for m in MODULES))
 finally:
  await h.close();save('rest_results.json',{'scenario':SCENARIO,'results':RESULTS})
asyncio.run(main())
