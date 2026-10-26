import sys,json
from pathlib import Path
from datetime import datetime,timezone
from decimal import Decimal
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from integrations.core import ROOT,save,SCENARIO
from integrations.schemas.models import *

def read(name):
 p=ROOT/'reports/examples'/f'{name}.json'
 return json.loads(p.read_text()) if p.exists() else {}
def stamp(provider,source,evidence,case):
 # Use original acquisition timestamp, never regeneration time.
 files=['rest_results.json','followup_results.json','mcp_call_results.json','extra_results.json']
 for file in files:
  p=ROOT/'reports'/file
  if not p.exists():continue
  records=json.loads(p.read_text());records=records.get('results',[]) if isinstance(records,dict) else records
  for r in records:
   if r['provider']==provider and r['case']==case:return Provenance(provider=provider,source_url=source,retrieved_at=r['retrieved_at'],evidence=evidence)
 raise ValueError('Missing provenance for '+provider+'/'+case)
def build():
 flights=[];stays=[];activities=[];places=[];routes=[];budget=[]
 for case in ['outbound','inbound','changed_dates']:
  for x in read('travelpayouts_data__'+case).get('data',[]):
   f=Flight(origin=x['origin'],destination=x['destination'],departure_at=x['departure_at'],airline=x.get('airline'),flight_number=x.get('flight_number'),price=Money(amount=x['price'],currency='RUB',basis='person'),transfers=x.get('transfers'),source=stamp('travelpayouts_data','https://api.travelpayouts.com/aviasales/v3/prices_for_dates','cached',case))
   flights.append({**f.model_dump(mode='json'),'case':case})
  matches=[x for x in flights if x['case']==case]
  if case in ['outbound','inbound']:
   price=min((Decimal(x['price']['amount']) for x in matches),default=None)
   budget.append(BudgetLine(name='flights_'+case,unit_price=Money(amount=price,currency='RUB',basis='person') if price is not None else None,quantity=2,evidence='cached'))
 seen=set()
 for area in ['sochi','adler','sirius','polyana']:
  for x in read('liteapi__catalog_'+area).get('data',[]):
   if x['id'] in seen:continue
   seen.add(x['id'])
   s=Stay(id=x['id'],name=x['name'],coordinates=Coordinates(lat=x['latitude'],lon=x['longitude']),address=x.get('address'),category='hotel',rating=x.get('rating'),rating_scale=10,photos=[x['main_photo']] if x.get('main_photo') else [],facilities=[str(v) for v in x.get('facilityIds',[])],source=stamp('liteapi','https://api.liteapi.travel/v3.0/data/hotels','catalog','catalog_'+area))
   stays.append({**s.model_dump(mode='json'),'area':area,'rate_search_status':'no_availability_in_sandbox'})
 budget.append(BudgetLine(name='hotel_4_nights'))
 for case in ['restaurants_adler','attractions_sochi','attractions_polyana','restaurants_near_hotel']:
  for x in read('geoapify__'+case).get('features',[]):
   p=x['properties'];coords=x['geometry']['coordinates']
   item=Place(id=p.get('place_id',str(p.get('osm_id',''))),name=p.get('name') or p.get('formatted','Unnamed'),coordinates=Coordinates(lon=coords[0],lat=coords[1]),address=p.get('formatted'),category=case,source=stamp('geoapify','https://api.geoapify.com/v2/places','live',case))
   places.append(item.model_dump(mode='json'))
 for x in read('timepad__events_sochi_tickets').get('values',[]):
  tickets=x.get('ticket_types',[]);pr=min((Decimal(str(t['price'])) for t in tickets if t.get('is_active') and t.get('price') is not None),default=None)
  a=Activity(id=str(x['id']),name=x['name'],starts_at=x.get('starts_at'),price=Money(amount=pr,currency='RUB',basis='ticket') if pr is not None else None,purchase_url=x.get('url'),source=stamp('timepad','https://api.timepad.ru/v1/events','live','events_sochi_tickets'))
  activities.append(a.model_dump(mode='json'))
 # A priced excursion, not arbitrary zero-price business event.
 tour=next((a for a in activities if 'Стендап' in a['name']),None)
 budget.append(BudgetLine(name='one_excursion',unit_price=Money(**tour['price']) if tour and tour['price'] else None,quantity=2,evidence='live'))
 budget.extend([BudgetLine(name='restaurants'),BudgetLine(name='all_local_transport'),BudgetLine(name='mountain_lifts'),BudgetLine(name='baggage_and_extra_fees')])
 for provider in ['geoapify','ors']:
  d=read(provider+'__route_adler_polyana');features=d.get('features',[])
  if not features:continue
  p=features[0]['properties'];dist=p.get('distance') if provider=='geoapify' else p['summary']['distance'];dur=p.get('time') if provider=='geoapify' else p['summary']['duration']
  routes.append(Route(origin=Coordinates(lat=43.428,lon=39.923),destination=Coordinates(lat=43.68,lon=40.2),distance_m=dist,duration_s=dur,mode='driving',source=stamp(provider,'https://api.geoapify.com/v1/routing' if provider=='geoapify' else 'https://api.openrouteservice.org/v2/directions/driving-car','live','route_adler_polyana')).model_dump(mode='json'))
 d=read('2gis__route_adler_polyana').get('structuredContent',{}).get('routes',[])
 if d:routes.append(Route(origin=Coordinates(lat=43.428,lon=39.923),destination=Coordinates(lat=43.68,lon=40.2),distance_m=d[0]['distance_meters'],duration_s=d[0]['duration_seconds'],mode='driving',source=stamp('2gis','https://mcp-2gis.api.2gis.com/mcp','live','route_adler_polyana')).model_dump(mode='json'))
 stored_scenario=json.loads((ROOT/'reports/rest_results.json').read_text()).get('scenario',SCENARIO)
 result={'scenario':stored_scenario,'flights':flights,'stays':stays,'places':places,'activities':activities,'routes':routes,'weather':read('openmeteo_forecast__coast_mountains'),'weather_source':stamp('openmeteo_forecast','https://api.open-meteo.com/v1/forecast','live','coast_mountains').model_dump(mode='json'),'budget':calculate_budget(budget).model_dump(mode='json'),'budget_lines':[x.model_dump(mode='json') for x in budget],'warning':'Catalog stays not bookable evidence. Cached single-adult fares multiplied for estimate only. Weather dates differ from trip dates.'}
 save('normalized_results.json',result)
 print(json.dumps({'flights':len(flights),'unique_hotels':len(stays),'places':len(places),'activities':len(activities),'routes':len(routes),'budget':result['budget']},ensure_ascii=False))
 return result
if __name__=='__main__':build()
