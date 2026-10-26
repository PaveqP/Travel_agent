from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from itertools import product
from uuid import uuid4
from urllib.parse import urlparse

from integrations.schemas.models import BudgetLine, Coordinates, calculate_budget
from travel_agent.schemas import BookingRequest, Candidate, ItineraryDay, OfferCard, OfferDates, PlanDiagnostics, TripConstraints, TripDelta, TripOption

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
    if patch.keys() & {'start', 'end', 'adults', 'travel_month', 'date_from', 'date_to', 'date_flexibility', 'direct_only'}:
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


def search_dates(trip: TripConstraints, today: date | None = None) -> list[tuple[date, date]]:
    today = today or date.today()
    duration = trip.nights or (trip.duration_days - 1 if trip.duration_days and trip.duration_days > 1 else None) or ((trip.end - trip.start).days if trip.start and trip.end else 7)
    lower, upper = trip.date_from, trip.date_to
    if lower and not upper:
        upper = lower + timedelta(days=31)
    elif upper and not lower:
        lower = max(today, trip.start or upper - timedelta(days=31))
    if not lower and not upper and trip.travel_month and not trip.start:
        year, month = map(int, trip.travel_month.split('-'))
        lower, upper = date(year, month, 1), date(year, month, monthrange(year, month)[1])
    if lower and upper:
        starts = [lower + timedelta(days=i) for i in range(max((upper - lower).days - duration + 1, 0))]
        if trip.start:
            starts.sort(key=lambda start: (abs((start - trip.start).days), start))
    elif trip.start:
        starts = [trip.start]
        starts += [trip.start + timedelta(days=shift) for offset in range(1, trip.date_flexibility + 1) for shift in (-offset, offset)]
    else:
        return []
    return [(start, start + timedelta(days=duration)) for start in starts if start >= today]


def transport_matches(c: Candidate, trip: TripConstraints, now: datetime) -> bool:
    if c.role != 'transport' or c.source.evidence != 'live' or c.source.expires_at is None or c.source.expires_at <= now:
        return False
    if c.origin != trip.origin or c.destination != 'AER' or c.adults != trip.adults or c.price is None or c.price.currency != 'RUB' or c.price.basis not in ('party', 'person', 'ticket'):
        return False
    if (c.start, c.end) not in search_dates(trip):
        return False
    if trip.direct_only and c.transfers != 0:
        return False
    return flight_fits(c, trip.model_copy(update={'start': c.start, 'end': c.end}))


def offer_card(c: Candidate, trip: TripConstraints, now: datetime | None = None) -> OfferCard:
    now = now or datetime.now(timezone.utc)
    expired = c.source.expires_at is not None and c.source.expires_at <= now
    labels = {'tutu': 'Туту', 'travelpayouts': 'Aviasales / Travelpayouts', '2gis': '2ГИС', 'geoapify': 'Geoapify', 'opentripmap': 'OpenTripMap', 'timepad': 'Timepad'}
    url = c.url or c.source.source_url
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        url = c.source.source_url
    warnings = []
    if expired:
        warnings.append('expired_quote')
    if c.source.evidence != 'live':
        warnings.append('unverified_availability')
    if c.price is None:
        warnings.append('unknown_price')
    if c.adults is not None and c.adults != trip.adults:
        warnings.append('different_party')
    if c.role == 'transport' and (c.start, c.end) != (trip.start, trip.end):
        warnings.append('alternate_dates')
    if c.role == 'transport' and (c.start, c.end) not in search_dates(trip):
        warnings.append('outside_search_window')
    if c.role == 'transport' and trip.direct_only and c.transfers != 0:
        warnings.append('direct_flight_unverified')
    if c.price and trip.party_budget:
        amount = c.price.amount * (trip.adults or 1) if c.price.basis in ('person', 'ticket') else c.price.amount
        if amount > trip.party_budget:
            warnings.append('over_budget')
    if c.role == 'stays' and c.area != trip.destination:
        warnings.append('different_area')
    if c.role == 'stays' and trip.hotel and trip.hotel.casefold() not in c.name.casefold():
        warnings.append('different_hotel')
    details = c.description
    if not details and c.role == 'transport':
        details = f"{c.origin or 'Город не подтверждён'} → {c.destination or 'Сочи'}"
        if c.duration_minutes:
            details += f'; в пути туда {c.duration_minutes} мин'
        if c.transfers is not None:
            details += f'; пересадок туда: {c.transfers}'
    elif not details:
        details = f"{c.name}; район: {c.area or 'не подтверждён'}."
    per_person = None
    if c.price:
        if c.price.basis in ('person', 'ticket'):
            per_person = c.price.model_copy(update={'basis': 'person'})
        elif c.price.basis in ('party', 'room_stay') and c.adults:
            per_person = c.price.model_copy(update={'amount': (c.price.amount / c.adults).quantize(Decimal('0.01')), 'basis': 'person'})
    selectable = transport_matches(c, trip, now) if c.role == 'transport' else stay_matches(c, trip, now) if c.role == 'stays' else False
    return OfferCard(id=c.id, kind=c.role, title=c.name, description=details,
                     aggregator=labels.get(c.source.provider, parsed.hostname or c.source.provider), provider=c.source.provider,
                     url=url, dates=OfferDates(start=c.start, end=c.end, departure_at=c.departure_at, arrival_at=c.arrival_at, return_departure_at=c.return_departure_at),
                     price=c.price, price_per_person=per_person, adults=c.adults, evidence=c.source.evidence,
                     freshness='expired' if expired else 'fresh' if c.source.expires_at else 'unknown', retrieved_at=c.source.retrieved_at,
                     selectable=selectable, action='view' if c.role == 'experience' else 'select' if selectable else 'verify', warnings=warnings)


def stay_matches(c: Candidate, trip: TripConstraints, now: datetime) -> bool:
    area = area_of(c.coordinates)
    if area is None:
        return False
    return usable(c, trip.model_copy(update={'destination': area, 'hotel': None}), now)


def usable(c: Candidate, trip: TripConstraints, now: datetime) -> bool:
    if c.source.expires_at is None or c.source.expires_at <= now:
        return False
    if c.role in ('transport', 'stays'):
        if c.source.evidence != 'live':
            return False
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
    if c.role == 'stays' and trip.destination != 'Сочи' and area != expected:
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
        rejected={reason: sum(reason in offer_card(c, trip, now).warnings for c in candidates) for reason in ('expired_quote', 'alternate_dates', 'different_party', 'outside_search_window', 'direct_flight_unverified')},
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
        available = sorted(activities, key=lambda c: stay is not None and area_of(c.coordinates) != area_of(stay.coordinates))
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


def simulate_purchase(state: dict, request: BookingRequest) -> dict:
    previous = state.get('bookings', {}).get(request.idempotency_key)
    if previous:
        if (previous['option_id'], previous['revision']) != (request.option_id, request.revision):
            raise ValueError('Idempotency key already used')
        return previous
    if not request.confirm:
        raise ValueError('Explicit confirmation is required for simulation')
    if state.get('stage') not in (None, 'review'):
        raise ValueError('Approve the itinerary before checkout')
    if request.revision != state.get('revision', 0) or state.get('selected') != request.option_id:
        raise ValueError('Select a current option first')
    option = next((TripOption.model_validate(o) for o in state.get('options', []) if o['id'] == request.option_id), None)
    if option is None or not option.transport or not option.stay:
        raise ValueError('Incomplete trip')
    trip = TripConstraints.model_validate(state['constraints'])
    if not all(usable(c, trip, datetime.now(timezone.utc)) for c in (option.transport, option.stay)):
        raise ValueError('Quotes expired; refresh search')
    if not flight_fits(option.transport, trip) or (option.transport.arrival_at.date(), option.transport.return_departure_at.date()) != (option.stay.start, option.stay.end):
        raise ValueError('Transport and stay dates are incompatible')
    if trip.party_budget and option.budget.known_subtotal > trip.party_budget:
        raise ValueError('Known subtotal exceeds the party budget')
    return {'id': str(uuid4()), 'option_id': request.option_id, 'revision': request.revision,
            'simulated': True, 'status': 'simulated', 'paid': False, 'reserved': False,
            'items': [{'kind': c.role, 'source_id': c.id, 'name': c.name, 'price': c.price.model_dump(mode='json'), 'url': offer_card(c, trip).url, 'provider': c.source.provider, 'aggregator': offer_card(c, trip).aggregator, 'details': c.model_dump(mode='json', exclude={'source', 'price', 'url'})} for c in (option.transport, option.stay)],
            'payment': {'simulated': True, 'status': 'succeeded', 'currency': 'RUB', 'amount': str(option.budget.known_subtotal), 'scope': 'transport_and_stay'},
            'missing_costs': option.budget.missing, 'itinerary': [d.model_dump(mode='json') for d in option.days],
            'message': 'Имитация покупки оформлена: билеты, проживание и маршрут сохранены в заказе. Реальные места не зарезервированы, оплата не выполнялась. Питание, трансферы, активности и сборы не оплачены.'}
