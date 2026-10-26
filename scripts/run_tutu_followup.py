import sys,asyncio,json
from datetime import timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from integrations.core import START,END,RESULTS,save,ROOT
from integrations.outcomes import payload
from integrations.mcp.client import call
async def main():
 p=ROOT/'reports/examples/tutu__hotels_polyana.json'
 if p.exists():
  hotels=payload(json.loads(p.read_text())).get('hotels',[])
  if hotels:await call('tutu','get_offer_details',{'product_type':'hotels','hotel_id':str(hotels[0]['hotel_id']),'check_in':str(START),'check_out':str(END),'adults':2,'view':'rules'},'hotel_detail_polyana_retry')
 await call('tutu','search_avia',{'origin':'Москва','destination':'AER','departure_date':str(START+timedelta(days=1)),'return_date':str(END+timedelta(days=1)),'adults':2,'page_size':3},'flights_changed_dates')
 save('tutu_followup_results.json',RESULTS)
if __name__=='__main__':asyncio.run(main())
