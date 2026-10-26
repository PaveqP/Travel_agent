import sys,asyncio,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from integrations.core import START,END,RESULTS,save
from integrations.mcp.client import call

def unpack(d):
 if not isinstance(d,dict):return {}
 if d.get('structuredContent'):return d['structuredContent']
 for c in d.get('content',[]):
  if c.get('type')=='text':
   try:return json.loads(c['text'])
   except ValueError:pass
 return {}
async def main():
 for name in ['get_avia_instructions','get_hotels_instructions','get_etrain_instructions']:
  await call('tutu',name,{})
 await call('tutu','search_avia',{'origin':'Москва','destination':'AER','departure_date':str(START),'return_date':str(END),'adults':2,'page_size':10},'flights_roundtrip')
 for area,city in [('sochi','Сочи'),('adler','Адлер'),('sirius','Сириус'),('polyana','Красная Поляна')]:
  d=await call('tutu','search_hotels',{'city_name':city,'check_in':str(START),'check_out':str(END),'adults':2,'page_size':10},'hotels_'+area)
  o=unpack(d);hotels=o.get('hotels',[])
  if area=='polyana' and hotels:
   ident=hotels[0].get('hotel_id') or hotels[0].get('hotel_geo_id')
   if ident:await call('tutu','get_offer_details',{'product_type':'hotels','hotel_id':str(ident),'check_in':str(START),'check_out':str(END),'adults':2,'view':'rules'},'hotel_detail_polyana')
 await call('tutu','search_etrain',{'origin':'Адлер','destination':'Роза Хутор','departure_date':str(START),'page_size':10},'etrain_adler_rosa')
 save('tutu_results.json',RESULTS)
if __name__=='__main__':asyncio.run(main())
