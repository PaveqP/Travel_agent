import asyncio
from integrations.core import record
async def run(h):
 # Bounded OSM extraction via Overpass, not the editing API.
 q='[out:json][timeout:20];nwr["amenity"="restaurant"](around:2000,43.428,39.923);out center tags 10;'
 await h.get('overpass','restaurants_adler','https://overpass-api.de/api/interpreter',params={'data':q},expected=lambda d:isinstance(d.get('elements'),list))
 for name in ['Адлер, Сочи','Красная Поляна, Сочи']:
  await h.get('nominatim','geocode_'+('adler' if name.startswith('Адлер') else 'polyana'),'https://nominatim.openstreetmap.org/search',params={'q':name,'format':'jsonv2','limit':2,'countrycodes':'ru'},expected=lambda d:isinstance(d,list))
  await asyncio.sleep(1.1)
 await h.get('osrm','route_adler_polyana','https://router.project-osrm.org/route/v1/driving/39.923,43.428;40.2,43.68',params={'overview':'false','steps':'false'},expected=lambda d:d.get('code')=='Ok' and bool(d.get('routes')))
 q='SELECT ?item ?itemLabel ?coord WHERE { SERVICE wikibase:around { ?item wdt:P625 ?coord . bd:serviceParam wikibase:center "Point(39.723 43.585)"^^geo:wktLiteral ; wikibase:radius "5" . } SERVICE wikibase:label { bd:serviceParam wikibase:language "ru,en" . } } LIMIT 10'
 await h.get('wikidata','places_sochi','https://query.wikidata.org/sparql',params={'query':q,'format':'json'},expected=lambda d:isinstance(d.get('results',{}).get('bindings'),list))
 record('osm','dataset_access','covered_via_overpass',reason='No bulk planet download or editing API calls needed; bounded real OSM POI query above')
