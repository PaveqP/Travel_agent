from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from integrations.schemas.models import Budget, Coordinates, Money, Provenance

Role = Literal["transport", "stays", "experience"]
Area = Literal["Сочи", "Адлер", "Сириус", "Красная Поляна", "Роза Хутор"]


class TripConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")
    origin: str | None = Field(default=None, min_length=1, max_length=120)
    destination: Area = "Сочи"
    start: date | None = None
    end: date | None = None
    check_in: date | None = None
    check_out: date | None = None
    adults: int | None = Field(default=None, ge=1, le=6)
    budget: Decimal | None = Field(default=None, gt=0)
    budget_basis: Literal["party", "person"] = "party"
    purpose: str | None = Field(default=None, min_length=1, max_length=500)
    hotel: str | None = Field(default=None, max_length=200)
    interests: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def dates(self):
        if self.start and self.end and not 0 < (self.end - self.start).days <= 30:
            raise ValueError("Trip must last 1–30 nights")
        if self.stay_start and self.stay_end and self.stay_start >= self.stay_end:
            raise ValueError("Check-out must follow check-in")
        if self.check_in and self.start and self.check_in < self.start:
            raise ValueError("Check-in precedes the trip")
        if self.check_out and self.end and self.check_out > self.end:
            raise ValueError("Check-out follows the trip")
        return self

    @property
    def stay_start(self) -> date | None:
        return self.check_in or self.start

    @property
    def stay_end(self) -> date | None:
        return self.check_out or self.end

    @property
    def party_budget(self) -> Decimal | None:
        if self.budget is None or self.budget_basis == "person" and self.adults is None:
            return None
        return self.budget * self.adults if self.budget_basis == "person" else self.budget

    def missing(self) -> list[str]:
        return [
            k for k in ("origin", "start", "end", "adults") if getattr(self, k) is None
        ]


class TripDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    origin: str | None = Field(default=None, min_length=1, max_length=120)
    destination: Area | None = None
    start: date | None = None
    end: date | None = None
    check_in: date | None = None
    check_out: date | None = None
    adults: int | None = Field(default=None, ge=1, le=6)
    budget: Decimal | None = Field(default=None, gt=0)
    budget_basis: Literal["party", "person"] | None = None
    purpose: str | None = Field(default=None, min_length=1, max_length=500)
    hotel: str | None = Field(default=None, max_length=200)
    interests: list[str] | None = Field(default=None, max_length=10)
    clear: list[Literal["hotel", "budget", "purpose", "check_in", "check_out"]] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def distinct_changes(self):
        if any(getattr(self, name) is not None for name in self.clear):
            raise ValueError("Cannot set and clear the same constraint")
        return self


class SupervisorDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal[
        "chat",
        "clarify",
        "transport",
        "stays",
        "experience",
        "compose",
        "answer",
        "research",
        "unsupported",
    ]
    reply: str = Field(default="", max_length=1200)
    research_role: Role = "experience"
    selected_option_id: str | None = None
    patch: TripDelta = Field(default_factory=TripDelta)
    question: str = Field(default="", max_length=600)
    task: str = Field(default="", max_length=1000)
    source_ids: list[str] = Field(default_factory=list, max_length=20)
    refresh: list[Role] = Field(default_factory=list, max_length=3)


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
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
    model_config = ConfigDict(extra="forbid")
    source_ids: list[str] = Field(default_factory=list, max_length=20)


class SpecialistResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Role
    revision: int = Field(ge=0)
    status: Literal["ok", "partial", "empty"]
    candidates: list[Candidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    tool_calls: int = 0
    selected_ids: list[str] = Field(default_factory=list, max_length=20)


class ItineraryDay(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: date
    candidates: list[Candidate] = Field(default_factory=list)
    warnings: list[str] = Field(
        default_factory=lambda: ["Время работы и местные переезды не подтверждены"]
    )


class TripOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    revision: int
    transport: Candidate | None
    stay: Candidate | None
    budget: Budget
    days: list[ItineraryDay]
    warnings: list[str]


class PlanDiagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid")
    received: dict[Role, int]
    eligible: dict[Role, int]
    reasons: list[str] = Field(default_factory=list)
    suggested_check_in: date | None = None


class MessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=4000)
    revision: int = Field(default=0, ge=0)


class BookingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    option_id: str
    revision: int = Field(ge=0)
    confirm: bool
    idempotency_key: str = Field(min_length=8, max_length=100)


class WebEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str
    title: str = Field(max_length=200)
    text: str = Field(max_length=2000)
    retrieved_at: datetime


class ResearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Role
    sources: list[WebEvidence] = Field(default_factory=list, max_length=20)
    warnings: list[str] = Field(default_factory=list)


class OptionExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    option_id: str
    benefit: str = Field(max_length=500)
    tradeoff: str = Field(max_length=500)


class UserResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=2000)
    options: list[OptionExplanation] = Field(default_factory=list, max_length=5)
    source_urls: list[str] = Field(default_factory=list, max_length=10)
