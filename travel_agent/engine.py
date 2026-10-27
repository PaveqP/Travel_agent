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
    if patch.keys() & {'start', 'end', 'adults', 'children_ages', 'transport_mode', 'service_class', 'requirements', 'travel_month', 'date_from', 'date_to', 'date_flexibility', 'direct_only'}:
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


def quote_current(c: Candidate, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    return bool(c.source.evidence == 'live' and c.source.expires_at and c.source.expires_at > now
                and c.price is not None and c.price.basis != 'unknown')


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
    if c.adults is not None and (c.adults != trip.adults or c.children_ages != trip.children_ages):
        warnings.append('different_party')
    if c.role == 'transport' and (c.start, c.end) != (trip.start, trip.end):
        warnings.append('alternate_dates')
    if c.price and c.price.currency == 'RUB' and trip.party_budget:
        amount = c.price.amount * (trip.party_size or 1) if c.price.basis in ('person', 'ticket') else c.price.amount
        if amount > trip.party_budget:
            warnings.append('over_budget')
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
            per_person = c.price.model_copy(update={'amount': (c.price.amount / (c.adults + len(c.children_ages))).quantize(Decimal('0.01')), 'basis': 'person'})
    selectable = quote_current(c, now) and c.role in ('transport', 'stays')
    return OfferCard(id=c.id, kind=c.role, title=c.name, description=details,
                     aggregator=labels.get(c.source.provider, parsed.hostname or c.source.provider), provider=c.source.provider,
                     url=url, dates=OfferDates(start=c.start, end=c.end, departure_at=c.departure_at, arrival_at=c.arrival_at, return_departure_at=c.return_departure_at),
                     price=c.price, price_per_person=per_person, adults=c.adults, children_ages=c.children_ages, evidence=c.source.evidence,
                     freshness='expired' if expired else 'fresh' if c.source.expires_at else 'unknown', retrieved_at=c.source.retrieved_at,
                     selectable=selectable, action='view' if c.role == 'experience' else 'select' if selectable else 'verify', warnings=warnings, facts=c.facts, transport_mode=c.transport_mode)


def diagnose(trip: TripConstraints, candidates: list[Candidate], now: datetime | None = None) -> PlanDiagnostics:
    roles = ('transport', 'stays', 'experience')
    ready = {role: sum(c.role == role and (role == 'experience' or quote_current(c, now)) for c in candidates) for role in roles}
    return PlanDiagnostics(received={role: sum(c.role == role for c in candidates) for role in roles},
        eligible=ready, reasons=['no_eligible_' + role for role in ('transport', 'stays') if not ready[role]],
        rejected={'expired_quote': sum(bool(c.source.expires_at and c.source.expires_at <= (now or datetime.now(timezone.utc))) for c in candidates)})


def compose(trip: TripConstraints, candidates: list[Candidate], revision: int, now: datetime | None = None, preferred_stays: list[str] | None = None) -> list[TripOption]:
    transports = [c for c in candidates if c.role == 'transport']
    stays = [c for c in candidates if c.role == 'stays']
    activities = [c for c in candidates if c.role == 'experience']
    if not transports and not stays:
        return []
    options = []
    for transport, stay in product(transports or [None], stays or [None]):
        lines = []
        warnings = ['Поисковые тарифы; наличие не гарантировано. Полная стоимость неизвестна.']
        for name, item in [('transport', transport), ('stay', stay)]:
            money = item.price if item else None
            if money and money.currency != 'RUB':
                warnings.append(name + ': требуется курс валюты; исходная цена сохранена в карточке')
                money = None
            quantity = (trip.party_size or 1) if money and money.basis in ('person', 'ticket') else 1
            lines.append(BudgetLine(name=name, unit_price=money, quantity=quantity, evidence=item.source.evidence if item else 'unknown'))
            if item and not quote_current(item, now):
                warnings.append(name + ': требуется проверка котировки перед оформлением')
        lines += [BudgetLine(name=name) for name in ('meals', 'local_transport', 'activities', 'extra_fees')]
        budget = calculate_budget(lines)
        if trip.party_budget and budget.known_subtotal > trip.party_budget:
            warnings.append('Известная часть расходов превышает бюджет')
        if transport and stay and transport.arrival_at and transport.return_departure_at and (transport.arrival_at.date(), transport.return_departure_at.date()) != (stay.start, stay.end):
            warnings.append('Даты транспорта и проживания требуют согласования')
        calendar: dict[date, list[Candidate]] = {}
        if trip.start and trip.end:
            for index in range((trip.end - trip.start).days + 1):
                calendar[trip.start + timedelta(days=index)] = []
        for activity in activities:
            day = activity.scheduled_date or activity.start or trip.stay_start
            if day is not None:
                calendar.setdefault(day, []).append(activity)
        days = [ItineraryDay(date=day, candidates=items) for day, items in sorted(calendar.items())]
        ident = sha256(f'{revision}:{transport.id if transport else ""}:{stay.id if stay else ""}'.encode()).hexdigest()[:16]
        options.append(TripOption(id=ident, revision=revision, transport=transport, stay=stay, budget=budget, days=days, warnings=warnings))
    return options


def simulate_purchase(state: dict, request: BookingRequest) -> dict:
    previous = state.get('bookings', {}).get(request.idempotency_key)
    if previous:
        if (previous['option_id'], previous['revision']) != (request.option_id, request.revision):
            raise ValueError('Idempotency key already used')
        if previous.get('payment', {}).get('method', 'card') != request.payment_method:
            raise ValueError('Idempotency key already used for a different payment method')
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
    for candidate in (option.transport, option.stay):
        if candidate.adults != trip.adults or candidate.children_ages != trip.children_ages:
            raise ValueError('Passenger composition requires verification')
        if candidate.price and candidate.price.currency != 'RUB':
            raise ValueError('Currency conversion requires a dated rate')
    if not all(quote_current(c) for c in (option.transport, option.stay)):
        raise ValueError('Quotes expired; refresh search')
    if not option.transport.arrival_at or not option.transport.return_departure_at or (option.transport.arrival_at.date(), option.transport.return_departure_at.date()) != (option.stay.start, option.stay.end):
        raise ValueError('Transport and stay dates are incompatible')
    return {'id': str(uuid4()), 'option_id': request.option_id, 'revision': request.revision,
            'simulated': True, 'status': 'simulated', 'paid': False, 'reserved': False,
            'items': [{'kind': c.role, 'source_id': c.id, 'name': c.name, 'price': c.price.model_dump(mode='json'), 'url': offer_card(c, trip).url, 'provider': c.source.provider, 'aggregator': offer_card(c, trip).aggregator, 'details': c.model_dump(mode='json', exclude={'source', 'price', 'url'})} for c in (option.transport, option.stay)],
            'payment': {'simulated': True, 'status': 'succeeded', 'currency': 'RUB', 'amount': str(option.budget.known_subtotal), 'scope': 'transport_and_stay', 'method': request.payment_method},
            'missing_costs': option.budget.missing, 'itinerary': [d.model_dump(mode='json') for d in option.days],
            'message': 'Имитация покупки оформлена: билеты, проживание и маршрут сохранены в заказе. Реальные места не зарезервированы, оплата не выполнялась. Питание, трансферы, активности и сборы не оплачены.'}
