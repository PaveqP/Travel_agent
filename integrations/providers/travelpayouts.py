from datetime import timedelta
from integrations.core import ENV,START,END
async def run(h):
 for case,start,end,origin,dest in [('outbound',START,END,'MOW','AER'),('inbound',END,None,'AER','MOW'),('changed_dates',START+timedelta(days=1),END+timedelta(days=1),'MOW','AER')]:
  params={'origin':origin,'destination':dest,'departure_at':str(start),'currency':'rub','sorting':'price','direct':'false','limit':10,'one_way':'true'}
  await h.get('travelpayouts_data',case,'https://api.travelpayouts.com/aviasales/v3/prices_for_dates',params=params,headers={'X-Access-Token':ENV.get('TRAVELPAYOUTS_TOKEN','')},required_key='TRAVELPAYOUTS_TOKEN',expected=lambda d:d.get('success') is True and isinstance(d.get('data'),list))
