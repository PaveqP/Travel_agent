import unittest,json
from decimal import Decimal
from unittest.mock import patch
from pydantic import ValidationError
from integrations.core import clean
from integrations.outcomes import outcome
from integrations.schemas.models import Money,BudgetLine,Coordinates,calculate_budget
from integrations.mcp.client import call

class ResearchTests(unittest.TestCase):
 def test_decimal_budget(self):
  b=calculate_budget([BudgetLine(name='x',unit_price=Money(amount='0.1',currency='RUB'),quantity=3,confirmed=True,evidence='live')])
  self.assertEqual(b.confirmed_total,Decimal('0.3'))
 def test_missing_not_zero(self):
  b=calculate_budget([BudgetLine(name='hotel')]);self.assertIsNone(b.confirmed_total);self.assertEqual(b.missing,['hotel'])
 def test_cached_cannot_confirm(self):
  b=calculate_budget([BudgetLine(name='flight',unit_price=Money(amount=3194,currency='RUB',basis='person'),quantity=2,confirmed=True,evidence='cached')]);self.assertEqual(b.known_subtotal,6388);self.assertIsNone(b.confirmed_total)
 def test_currency_requires_conversion(self):
  with self.assertRaises(ValueError):calculate_budget([BudgetLine(name='x',unit_price=Money(amount=10,currency='USD'))])
 def test_sandbox_production_guard(self):
  from scripts.run_sandbox import require_sandbox
  with self.assertRaises(ValueError):require_sandbox("production-test-placeholder")
 def test_party_total_not_multiplied(self):
  b=calculate_budget([BudgetLine(name="roundtrip",unit_price=Money(amount=14018,currency="RUB",basis="party"),quantity=1,evidence="live")]);self.assertEqual(b.known_subtotal,Decimal("14018"))
 def test_coordinates(self):
  with self.assertRaises(ValidationError):Coordinates(lat=100,lon=40)
 def test_secret_nested_mcp(self):
  with patch('integrations.core.SECRETS',['example-secret-only-for-test']):
   d=clean({'content':[{'text':json.dumps({'apiKey':'example-secret-only-for-test','email':'guest@example.invalid'})}]})
   self.assertNotIn('example-secret-only-for-test',json.dumps(d));self.assertNotIn('guest@',json.dumps(d))
 def test_schema_preserved(self):
  self.assertEqual(clean({'properties':{'email':{'type':'string'},'token':{'type':'string'}}})['properties']['email'],{'type':'string'})
 def test_semantic_no_availability(self):
  for d in [{'error':{'code':2001}}, {'isError':False,'content':[{'type':'text','text':'{"error":{"code":2001}}'}]}]:self.assertEqual(outcome({'status':'ok','data':d}),'no_availability')
 def test_forbidden_empty_missing_distinct(self):
  self.assertEqual(outcome({'status':'forbidden'}),'forbidden');self.assertEqual(outcome({'status':'ok','data':{'stations':[]}}),'empty');self.assertEqual(outcome({'status':'missing_key'}),'missing_key')
class SafetyTests(unittest.IsolatedAsyncioTestCase):
 async def test_booking_blocked_before_network(self):
  with patch('integrations.mcp.client.record',side_effect=lambda p,c,s,**kw:{'status':s}),patch('integrations.mcp.client.connection') as conn:
   r=await call('liteapi','post_rates_book',{});self.assertEqual(r['status'],'blocked_tool');conn.assert_not_called()
if __name__=='__main__':unittest.main()
