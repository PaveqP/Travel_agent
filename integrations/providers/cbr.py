from xml.etree import ElementTree
from integrations.core import record
async def run(h):
 d=await h.get('cbr','daily_rates','https://www.cbr.ru/scripts/XML_daily.asp')
 if isinstance(d,dict) and 'text' in d:
  try:
   tree=ElementTree.fromstring(d['text']); rates=[{'currency':x.findtext('CharCode'),'nominal':x.findtext('Nominal'),'value':x.findtext('Value')} for x in tree.findall('Valute') if x.findtext('CharCode') in ('USD','EUR')]
   record('cbr','parse_xml','ok' if rates else 'empty',effective_date=tree.get('Date'),data=rates)
  except Exception as e:record('cbr','parse_xml','schema_error',exception_type=type(e).__name__)
