"""Separate transport success from provider/business outcomes."""
import json

def payload(d):
 if not isinstance(d,dict):return d
 if isinstance(d.get('structuredContent'),dict):return d['structuredContent']
 for c in d.get('content',[]):
  if c.get('type')=='text':
   try:return json.loads(c['text'])
   except (ValueError,TypeError):pass
 return d

def outcome(r):
 status=r.get('status','unknown')
 d=payload(r.get('data',{}))
 if isinstance(d,dict) and d.get('error'):
  error=d['error'];code=error.get('code') if isinstance(error,dict) else None
  if str(code)=='2001':return 'no_availability'
  return 'provider_error'
 if status=='covered_via_overpass':return 'indirect_data_only'
 if status not in ('ok','schema_or_provider_error'):return status
 if isinstance(d,dict):
  for k in ['stations','features','hotels','offers','segments','values','elements','data']:
   if k in d and isinstance(d[k],list) and not d[k]:return 'empty'
 if isinstance(d,list) and not d:return 'empty'
 return status
