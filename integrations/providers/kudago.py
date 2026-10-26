from datetime import datetime,time,timezone
from integrations.core import START,END
async def run(h):
 await h.get('kudago','locations','https://kudago.com/public-api/v1.4/locations/',params={'lang':'ru'},expected=lambda d:isinstance(d,list))
 await h.get('kudago','events_sochi','https://kudago.com/public-api/v1.4/events/',params={'location':'sochi','actual_since':int(datetime.combine(START,time.min,tzinfo=timezone.utc).timestamp()),'actual_until':int(datetime.combine(END,time.max,tzinfo=timezone.utc).timestamp()),'page_size':10,'fields':'id,title,dates,place,price,is_free,site_url','expand':'place'},expected=lambda d:isinstance(d.get('results'),list))
 await h.get('kudago','places_sochi','https://kudago.com/public-api/v1.4/places/',params={'location':'sochi','page_size':10,'fields':'id,title,address,coords,site_url'},expected=lambda d:isinstance(d.get('results'),list))
