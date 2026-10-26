from __future__ import annotations
from datetime import datetime,date
from decimal import Decimal
from typing import Any,Literal
from pydantic import BaseModel,Field,ConfigDict,model_validator

class Coordinates(BaseModel):
 lat:float=Field(ge=-90,le=90)
 lon:float=Field(ge=-180,le=180)
class Money(BaseModel):
 amount:Decimal=Field(ge=0)
 currency:str=Field(pattern=r'^[A-Z]{3}$')
 basis:Literal['person','room_stay','party','ticket','unknown']='unknown'
 taxes_included:bool|None=None
class Provenance(BaseModel):
 provider:str
 source_url:str
 retrieved_at:datetime
 evidence:Literal['live','cached','catalog','sandbox','derived','simulated']
 source_updated_at:datetime|None=None
 expires_at:datetime|None=None
class Place(BaseModel):
 id:str
 name:str
 coordinates:Coordinates|None=None
 address:str|None=None
 category:str
 source:Provenance
 rating:float|None=None
 rating_scale:float|None=None
 photos:list[str]=Field(default_factory=list)
class Stay(Place):
 availability:Literal['unknown','available','unavailable']='unknown'
 price:Money|None=None
 cancellation_policy:str|None=None
 facilities:list[str]=Field(default_factory=list)
class Flight(BaseModel):
 origin:str
 destination:str
 departure_at:datetime
 airline:str|None=None
 flight_number:str|None=None
 price:Money
 source:Provenance
 transfers:int|None=None
 baggage:str|None=None
 availability_verified:bool=False
class Route(BaseModel):
 origin:Coordinates
 destination:Coordinates
 distance_m:float=Field(ge=0)
 duration_s:float=Field(ge=0)
 mode:str
 source:Provenance
class Activity(BaseModel):
 id:str
 name:str
 starts_at:datetime|None=None
 price:Money|None=None
 purchase_url:str|None=None
 availability_verified:bool=False
 source:Provenance
class SourceResult(BaseModel):
 model_config=ConfigDict(extra='forbid')
 status:Literal['ok','empty','no_availability','unauthorized','forbidden','rate_limited','network_error','schema_error','missing_key','partner_access_required','cost_guard','partial']
 source:Provenance
 items:list[dict[str,Any]]=Field(default_factory=list)
 warnings:list[str]=Field(default_factory=list)
 error_code:str|None=None
 latency_ms:int|None=None
class BudgetLine(BaseModel):
 name:str
 unit_price:Money|None=None
 quantity:int=Field(default=1,ge=1)
 confirmed:bool=False
 evidence:Literal['live','cached','catalog','sandbox','derived','unknown']='unknown'
class Budget(BaseModel):
 currency:str
 known_subtotal:Decimal
 confirmed_total:Decimal|None
 complete:bool
 missing:list[str]
 warnings:list[str]

def calculate_budget(lines:list[BudgetLine],currency='RUB')->Budget:
 subtotal=Decimal(0);missing=[];warnings=[]
 for line in lines:
  if line.unit_price is None:missing.append(line.name);continue
  if line.unit_price.currency!=currency:raise ValueError('Currency conversion requires dated external rate')
  subtotal+=line.unit_price.amount*line.quantity
  if not line.confirmed or line.evidence in ('cached','sandbox','catalog','unknown'):warnings.append(line.name+': not a confirmed live quote')
 complete=not missing and not warnings
 return Budget(currency=currency,known_subtotal=subtotal,confirmed_total=subtotal if complete else None,complete=complete,missing=missing,warnings=warnings)
