from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from integrations.schemas.models import Budget, Coordinates, Money, Provenance

Role = Literal['transport', 'stays', 'experience']
Area = Literal['Сочи', 'Адлер', 'Сириус', 'Красная Поляна', 'Роза Хутор']


class TripConstraints(BaseModel):
    model_config = ConfigDict(extra='forbid')
    origin: str | None = Field(default=None, min_length=1, max_length=120)
    destination: Area = 'Сочи'
    start: date | None = None
    end: date | None = None
    adults: int | None = Field(default=None, ge=1, le=6)
    budget: Decimal | None = Field(default=None, gt=0)
    hotel: str | None = Field(default=None, max_length=200)
    interests: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode='after')
    def dates(self):
        if self.start and self.end and not 0 < (self.end - self.start).days <= 30:
            raise ValueError('Trip must last 1–30 nights')
        return self

    def missing(self) -> list[str]:
        return [k for k in ('origin', 'start', 'end', 'adults') if getattr(self, k) is None]


class TripDelta(BaseModel):
    model_config = ConfigDict(extra='forbid')
    origin: str | None = Field(default=None, min_length=1, max_length=120)
    destination: Area | None = None
    start: date | None = None
    end: date | None = None
    adults: int | None = Field(default=None, ge=1, le=6)
    budget: Decimal | None = Field(default=None, gt=0)
    hotel: str | None = Field(default=None, max_length=200)
    interests: list[str] | None = Field(default=None, max_length=10)


class SupervisorDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['clarify', 'transport', 'stays', 'experience', 'compose', 'answer', 'unsupported']
    patch: TripDelta = Field(default_factory=TripDelta)
    question: str = Field(default='', max_length=600)
    task: str = Field(default='', max_length=1000)
    source_ids: list[str] = Field(default_factory=list, max_length=20)
    refresh: list[Role] = Field(default_factory=list, max_length=3)


class Candidate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str
    role: Role
    name: str
    source: Provenance
    price: Money | None = None
    coordinates: Coordinates | None = None
    area: str | None = None
    start: date | None = None
    end: date | None = None
    adults: int | None = None
    origin: str | None = None
    destination: str | None = None
    arrival_at: datetime | None = None
    return_departure_at: datetime | None = None
    url: str | None = None


class SpecialistSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_ids: list[str] = Field(default_factory=list, max_length=20)


class SpecialistResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Role
    revision: int = Field(ge=0)
    status: Literal['ok', 'partial', 'empty']
    candidates: list[Candidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    tool_calls: int = 0


class ItineraryDay(BaseModel):
    model_config = ConfigDict(extra='forbid')
    date: date
    candidates: list[Candidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=lambda: ['Время работы и местные переезды не подтверждены'])


class TripOption(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str
    revision: int
    transport: Candidate | None
    stay: Candidate | None
    budget: Budget
    days: list[ItineraryDay]
    warnings: list[str]


class MessageRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    message: str = Field(min_length=1, max_length=4000)
    revision: int = Field(default=0, ge=0)


class BookingRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    option_id: str
    revision: int = Field(ge=0)
    confirm: bool
    idempotency_key: str = Field(min_length=8, max_length=100)
