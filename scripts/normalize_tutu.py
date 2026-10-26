import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from integrations.core import ROOT,save
from integrations.outcomes import payload
from integrations.schemas.models import Stay,Coordinates,Money,Provenance,BudgetLine,calculate_budget

def build():
 records=[]
 for f in ['tutu_results.json','tutu_followup_results.json']:
  p=ROOT/'reports'/f
  if p.exists():records+=json.loads(p.read_text())
 stays=[];flights=[];counts={}
 for r in records:
  d=payload(r.get('data',{}))
  if not isinstance(d,dict):continue
  src=Provenance(provider='tutu',source_url='https://mcp.tutu.ru/mcp',retrieved_at=r['retrieved_at'],evidence='live')
  if r['case'].startswith('hotels_'):
   hotels=d.get('hotels',[]);counts[r['case']]=len(hotels)
   for h in hotels:
    offer=h.get('best_offer') or {};p=offer.get('price');loc=h.get('location') or {}
    s=Stay(id=h['hotel_id'],name=h['name'],category='hotel',coordinates=Coordinates(lat=loc['lat'],lon=loc['lng']) if loc.get('lat') is not None else None,address=h.get('address'),rating=h.get('rating'),rating_scale=10,photos=h.get('photos',[]),price=Money(amount=p['amount'],currency=p['currency'],basis='room_stay') if p else None,availability='available' if p else 'unknown',source=src)
    stays.append({**s.model_dump(mode='json'),'query_area':r['case'],'resolved_geo':d.get('meta',{}).get('resolved_geo'),'free_cancellation':offer.get('free_cancellation'),'breakfast_included':offer.get('breakfast_included'),'purchase_url':offer.get('checkout_url'),'availability_scope':'search_quote_not_prebook','stay':d.get('stay')})
  if r['case']=='flights_roundtrip':
   for o in d.get('offers',[]):flights.append({'price':Money(amount=o['price']['amount'],currency=o['price']['currency'],basis='party').model_dump(mode='json'),'legs':o.get('legs'),'variants':o.get('variants'),'purchase_url':o.get('search_results_url'),'source':src.model_dump(mode='json'),'adults':2,'round_trip':True,'availability_scope':'search_quote_not_ticketed'})
 alternatives=[]
 if flights:
  f=min(flights,key=lambda x:float(x['price']['amount']))
  for area in counts:
   candidates=[h for h in stays if h['query_area']==area and h['price']]
   if not candidates:continue
   h=min(candidates,key=lambda x:float(x['price']['amount']))
   lines=[BudgetLine(name='roundtrip_two_adults',unit_price=Money(**f['price']),evidence='live'),BudgetLine(name='hotel_four_nights',unit_price=Money(**h['price']),evidence='live')]+[BudgetLine(name=x) for x in ['restaurants','local_transport','activities','lifts','extra_fees']]
   alternatives.append({'query_area':area,'hotel_name':h['name'],'hotel_id':h['id'],'budget':calculate_budget(lines).model_dump(mode='json')})
 result={'stays':stays,'flights':flights,'counts':counts,'unique_hotels':len({h['id'] for h in stays}),'alternatives':alternatives,'warning':'Search quotes only, not prebooked. Totals cover requested party/stay already. Region names may expand beyond locality; validate coordinates. Extra fees and meals not fully priced.'}
 save('tutu_normalized.json',result)
 print(json.dumps({'counts':counts,'unique_hotels':result['unique_hotels'],'flights':len(flights),'alternatives':alternatives},ensure_ascii=False))
if __name__=='__main__':build()
