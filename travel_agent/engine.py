from datetime import datetime, timedelta, timezone
from hashlib import sha256
from itertools import product

from integrations.schemas.models import BudgetLine, Coordinates, calculate_budget
from travel_agent.schemas import Candidate, ItineraryDay, PlanDiagnostics, TripConstraints, TripDelta, TripOption

CENTERS = {'Сочи': (43.585, 39.723), 'Адлер': (43.448, 39.907),
           'Сириус': (43.405, 39.96), 'Красная Поляна': (43.68, 40.2), 'Роза Хутор': (43.67, 40.29)}


def area_of(point: Coordinates | None) -> str | None:
    if point is None:
        return None
    lat, lon = point.lat, point.lon
    if 43.60 <= lat <= 43.76 and 40.10 <= lon <= 40.39:
        return 'Красная Поляна'
    if 43.38 <= lat <= 43.43 and 39.92 <= lon <= 40.02:
        return 'Сириус'
    if 43.42 <= lat <= 43.51 and 39.86 <= lon <= 40.02:
        return 'Адлер'
    if 43.50 <= lat <= 44.02 and 39.20 <= lon <= 39.86:
        return 'Сочи'
    return None


def apply_delta(current: TripConstraints, delta: TripDelta) -> tuple[TripConstraints, set[str]]:
    patch = {k: v for k, v in delta.model_dump(exclude_none=True, exclude={'clear'}).items() if v != getattr(current, k)}
    patch.update({k: None for k in delta.clear if getattr(current, k) is not None})
    if patch.keys() & {'start', 'end'}:
        for name in ('check_in', 'check_out'):
            if name not in patch:
                patch[name] = None
    revised = TripConstraints.model_validate({**current.model_dump(), **patch})
    affected: set[str] = set()
    if patch.keys() & {'start', 'end', 'adults'}:
        affected.update(('transport', 'stays', 'experience'))
    if 'origin' in patch:
        affected.add('transport')
    if patch.keys() & {'destination', 'hotel'}:
        affected.update(('stays', 'experience'))
    if patch.keys() & {'check_in', 'check_out'}:
        affected.update(('stays', 'experience'))
    if patch.keys() & {'purpose', 'interests'}:
        affected.update(('stays', 'experience'))
    return revised, affected


def usable(c: Candidate, trip: TripConstraints, now: datetime) -> bool:
    if c.source.expires_at is None or c.source.expires_at <= now:
        return False
    if c.role in ('transport', 'stays'):
        dates = (trip.start, trip.end) if c.role == 'transport' else (trip.stay_start, trip.stay_end)
        if (c.start, c.end, c.adults) != (*dates, trip.adults):
            return False
        if c.price is None or c.price.currency != 'RUB' or c.price.basis == 'unknown':
            return False
    if c.role == 'transport':
        return c.origin == trip.origin and c.destination == 'AER' and c.arrival_at is not None and c.return_departure_at is not None
    area = area_of(c.coordinates)
    if area is None:
        return False
    expected = 'Красная Поляна' if trip.destination == 'Роза Хутор' else trip.destination
    if trip.destination != 'Сочи' and area != expected:
        return False
    if c.role == 'stays' and trip.hotel and trip.hotel.casefold() not in c.name.casefold():
        return False
    return True


def flight_fits(c: Candidate, trip: TripConstraints) -> bool:
    return bool(c.arrival_at and c.return_departure_at and trip.start and trip.end
                and trip.start <= c.arrival_at.date() < trip.end
                and c.return_departure_at.date() == trip.end
                and c.return_departure_at > c.arrival_at)


def diagnose(trip: TripConstraints, candidates: list[Candidate], now: datetime | None = None) -> PlanDiagnostics:
    now = now or datetime.now(timezone.utc)
    roles = ('transport', 'stays', 'experience')
    eligible = [c for c in candidates if usable(c, trip, now)]
    flights = [c for c in eligible if c.role == 'transport' and flight_fits(c, trip)]
    stays = [c for c in eligible if c.role == 'stays']
    reasons = []
    if not flights:
        reasons.append('no_eligible_transport')
    if not stays:
        reasons.append('no_eligible_stays')
    mismatch = flights and stays and not any(
        (f.arrival_at.date(), f.return_departure_at.date()) == (s.start, s.end)
        for f in flights for s in stays
    )
    if mismatch:
        reasons.append('arrival_stay_mismatch')
    return PlanDiagnostics(
        received={r: sum(c.role == r for c in candidates) for r in roles},
        eligible={r: sum(c.role == r for c in eligible) for r in roles},
        reasons=reasons,
        suggested_check_in=min(f.arrival_at.date() for f in flights) if mismatch else None,
    )


def compose(trip: TripConstraints, candidates: list[Candidate], revision: int, now: datetime | None = None, preferred_stays: list[str] | None = None) -> list[TripOption]:
    now = now or datetime.now(timezone.utc)
    if trip.missing():
        return []
    valid = [c for c in candidates if usable(c, trip, now)]
    flights = [c for c in valid if c.role == 'transport' and flight_fits(c, trip)]
    stays = [c for c in valid if c.role == 'stays']
    activities = [c for c in valid if c.role == 'experience']
    options = []
    pairs = [(f, s) for f, s in product(flights or [None], stays or [None])
             if f is None or s is None or (f.arrival_at.date(), f.return_departure_at.date()) == (s.start, s.end)]
    if not pairs:
        pairs = [(None, s) for s in stays] or [(f, None) for f in flights]
    for flight, stay in pairs:
        if flight is None and stay is None:
            continue
        lines = []
        for name, item in [('transport', flight), ('stay', stay)]:
            money = item.price if item else None
            quantity = trip.adults if money and money.basis in ('person', 'ticket') else 1
            lines.append(BudgetLine(name=name, unit_price=money, quantity=quantity,
                                    evidence=item.source.evidence if item else 'unknown'))
        lines += [BudgetLine(name=k) for k in ('meals', 'local_transport', 'activities', 'extra_fees')]
        budget = calculate_budget(lines)
        days = []
        available = [c for c in activities if stay is None or area_of(c.coordinates) == area_of(stay.coordinates)]
        for index in range((trip.end - trip.start).days + 1):
            day = trip.start + timedelta(days=index)
            selected = []
            arrival = flight.arrival_at.date() if flight else trip.stay_start
            if arrival < day < trip.end:
                for activity in list(available):
                    if activity.start and activity.start != day:
                        continue
                    if selected and area_of(activity.coordinates) != area_of(selected[0].coordinates):
                        continue
                    selected.append(activity)
                    available.remove(activity)
                    if len(selected) == 2:
                        break
            days.append(ItineraryDay(date=day, candidates=selected))
        ident = sha256(f'{revision}:{flight.id if flight else ""}:{stay.id if stay else ""}'.encode()).hexdigest()[:16]
        warnings = ['Поисковые тарифы; наличие не гарантировано. Полная стоимость неизвестна.']
        if trip.party_budget and budget.known_subtotal > trip.party_budget:
            warnings.append('Известная часть расходов превышает бюджет')
        options.append(TripOption(id=ident, revision=revision, transport=flight, stay=stay, budget=budget, days=days, warnings=warnings))
    preferred = set(preferred_stays or [])
    ordered = sorted(options, key=lambda o: (bool(preferred) and (o.stay is None or o.stay.id not in preferred), o.budget.known_subtotal))
    diversified: list[TripOption] = []
    seen: set[str] = set()
    for option in ordered:
        key = option.stay.id if option.stay else option.transport.id
        if key not in seen:
            diversified.append(option)
            seen.add(key)
        if len(diversified) == 5:
            break
    return diversified
