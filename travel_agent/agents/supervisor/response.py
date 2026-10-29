import json
import logging
from datetime import date, datetime, timezone
from decimal import Decimal

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from openai import APIError
from pydantic import ValidationError

from travel_agent.schemas import UserResponse


def render_card(card: dict, index: int | None = None) -> str:
    prefix = f"{index}. " if index is not None else "• "
    lines = [prefix + card['title'], card['description'], f"Агрегатор / источник: {card['aggregator']}", card['url']]
    dates = card['dates']
    if dates.get('start'):
        lines.append(f"Даты: {dates['start']} — {dates.get('end') or 'не указано'}.")
    for field, label in (('departure_at', 'Вылет'), ('arrival_at', 'Прилёт'), ('return_departure_at', 'Обратный вылет')):
        if dates.get(field):
            lines.append(label + ': ' + datetime.fromisoformat(dates[field]).strftime('%d.%m.%Y %H:%M') + '.')
    price = card.get('price')
    if price:
        basis = 'на человека' if price['basis'] in ('person', 'ticket') else 'за всю группу и весь период'
        lines.append(f"Цена: {Decimal(price['amount']):,.2f} {price['currency']} {basis}.".replace(',', ' '))
        if card.get('price_per_person') and price['basis'] not in ('person', 'ticket'):
            lines.append(f"На человека: {Decimal(card['price_per_person']['amount']):,.2f} {price['currency']}.".replace(',', ' '))
    else:
        lines.append('Цена: источник не указал.')
    warnings = {'expired_quote': 'Сохранённая цена устарела; проверю перед выбором.', 'unverified_availability': 'Это кэш/справочная выдача, наличие не подтверждено.',
                'alternate_dates': 'Альтернатива на соседние даты.', 'different_party': 'Цена рассчитана для другого состава; стоимость вашей группы требует проверки.',
                'outside_search_window': 'Даты вне текущего диапазона, показано как сохранённый ориентир.', 'over_budget': 'Цена выше заданного бюджета.',
                'different_area': 'Район отличается от исходного сценария.', 'different_hotel': 'Альтернативный отель: отличается от указанного названия.', 'direct_flight_unverified': 'Прямой перелёт не подтверждён.'}
    lines.extend(warnings[w] for w in card.get('warnings', []) if w in warnings)
    return '\n'.join(lines)


def render_stage(state: dict) -> str:
    from travel_agent.schemas import TripConstraints

    stage = state.get("stage", "scenarios")
    trip = TripConstraints.model_validate(state.get("constraints", {}))
    titles = {"scenarios": "Выберем сценарий поездки", "transport": "Сначала согласуем транспорт", "stays": "Теперь выберем проживание", "itinerary": "Программа для выбранного проживания", "review": "Поездка собрана — проверьте корзину", "booked": "Имитированная покупка оформлена"}
    lines = [titles[stage] + "."]
    if state.get('notice'):
        lines.append(state['notice'])
    if trip.origin or trip.adults:
        lines.append(f"Из {trip.origin or 'города, который нужно указать'}; взрослых: {trip.adults or 'не указано'}.")
    if trip.date_from and trip.date_to:
        lines.append(f"Диапазон поиска: {trip.date_from:%d.%m.%Y} — {trip.date_to:%d.%m.%Y}.")
    if stage == "booked" and state.get("receipt"):
        lines.append(state["receipt"]["message"])
        lines.append("Номер имитированного заказа: " + state["receipt"]["id"])
    if trip.budget:
        basis = "на человека" if trip.budget_basis == "person" else "на группу"
        total = f"; предел группы {trip.party_budget:,.0f} ₽" if trip.party_budget else ""
        lines.append(f"Бюджет {trip.budget:,.0f} ₽ {basis}{total}.".replace(",", " "))
    for role, label in (("transport", "Транспорт согласован"), ("stays", "Проживание согласовано")):
        ident = state.get("selected_transport" if role == "transport" else "selected_stay")
        candidate = next((c for r in state.get("results", {}).values() for c in r.get("candidates", []) if c["id"] == ident), None)
        if candidate:
            lines.append(f"{label}: {candidate['name']}.")
            if role == "transport" and stage == "stays" and trip.party_budget:
                remaining = trip.party_budget - Decimal(candidate["price"]["amount"])
                lines.append(f"После билетов от предела группы остаётся {remaining:,.2f} ₽ на остальные расходы.".replace(",", " "))
    for index, choice in enumerate(state.get("choices", []), 1):
        if choice.get('aggregator'):
            lines.append('\n' + render_card(choice, index))
            continue
        lines.append(f"\n{index}. {choice['title']}\n{choice['details']}")
        if choice.get("price"):
            amount = Decimal(choice["price"]["amount"])
            per_person = f"; {amount / trip.adults:,.2f} ₽ на человека" if trip.adults else ""
            lines.append(f"{amount:,.2f} ₽ за всю группу и весь период{per_person}.".replace(",", " "))
    if stage == "scenarios":
        lines.append("Это направления поиска. Цены, наличие и свойства конкретных отелей ещё не проверены. Выберите сценарий по номеру; затем согласуем даты и транспорт.")
    elif stage in ("transport", "stays"):
        result = state.get("results", {}).get(stage, {})
        if not state.get("choices"):
            received = len(result.get("candidates", []))
            warnings = result.get("warnings", [])
            issues = {"timeout": "источник не ответил вовремя", "network_error": "ошибка соединения", "schema_error": "не удалось проверить формат ответа", "missing_key": "не настроен ключ источника", "forbidden": "доступ запрещён", "no_availability": "источник не подтвердил наличие", "llm_error": "не удалось завершить обработку моделью", "agent_limit": "достигнут лимит обработки"}
            causes = list(dict.fromkeys(issues[w.split(":")[-1]] for w in warnings if w.split(":")[-1] in issues))
            lines.append(f"Источник вернул {received} кандидатов; карточек с проверяемыми данными пока нет.")
            if causes:
                lines.append("Причина: " + "; ".join(causes) + ".")
            lines.append("Ограниченный поиск пока не дал предложений. Сохранённые компоненты поездки остаются доступны.")
        else:
            lines.append("Выберите номер предложения: согласую его фактические даты и продолжу подбор. Для сохранённых или справочных цен сначала выполню проверку. Поисковая цена не подтверждает резерв.")
    elif stage in ("itinerary", "review", "booked"):
        experience = state.get('results', {}).get('experience', {})
        if experience.get('status') == 'partial':
            lines.append('Программа получена частично. Ошибки источников или лимит обработки помешали завершить проверку; найденные места доступны как кандидаты.')
            if not experience.get('selected_ids'):
                lines.append('Места пока не отобраны для программы. Можно попросить повторить поиск активностей; билеты и отель сохранены.')
        if state.get('cards'):
            lines.append('\nНайденные места и активности:' if stage == 'itinerary' else '\nКомпоненты поездки:')
            lines.extend(render_card(card) for card in state['cards'])
        for option in state.get("options", []):
            amount = Decimal(option["budget"]["known_subtotal"])
            lines.append(f"\nБилеты и проживание: {amount:,.2f} ₽ за группу.".replace(",", " "))
            if trip.adults:
                lines.append(f"На человека: {amount / trip.adults:,.2f} ₽.".replace(",", " "))
            for day in option.get("days", []):
                places = ", ".join(c["name"] for c in day["candidates"]) or "свободное время / дорога"
                lines.append(f"{day['date']}: {places}.")
            lines.extend(option.get("warnings", []))
        lines.append("Питание, трансферы, входные билеты и сборы не подтверждены и не включены; часы работы и время переездов требуют проверки.")
        if stage != "booked":
            lines.append("Согласуйте программу, чтобы перейти к корзине." if stage == "itinerary" else "Для имитации покупки введите /book confirm или явно попросите оформить имитированную покупку.")
    return "\n".join(lines)


def option_context(state: dict) -> list[dict]:
    return [
        {
            **{k: o[k] for k in ("id", "budget", "warnings")},
            **{role: {k: value for k, value in (o.get(role) or {}).items() if k in ('id', 'name', 'area', 'price', 'start', 'end', 'departure_at', 'arrival_at', 'arrival_city', 'return_departure_at', 'return_arrival_at', 'transport_mode', 'stars', 'rating', 'baggage_included', 'conditions', 'variant_id', 'source', 'duration_minutes', 'transfers', 'coordinates', 'address', 'description', 'amenities')} for role in ('transport', 'stay')},
            "days": [
                {
                    "date": d["date"],
                    "places": [
                        {"name": c["name"], "area": c.get("area")}
                        for c in d["candidates"]
                    ],
                }
                for d in o.get("days", [])
            ],
        }
        for o in state.get("options", [])
    ]


def render_options(state: dict, response: UserResponse | None = None) -> str:
    options = state.get("options", [])
    if not options:
        return render_components(state)
    trip = state.get("constraints", {})
    lines = [f"**{trip.get('origin', '')} → {trip.get('destination', 'Россия')}**", ""]
    complete = [o for o in options if o.get('transport') and o.get('stay')]
    if not complete:
        return render_components(state)
    cheapest = min(Decimal(o['budget']['known_subtotal']) for o in complete)
    durations = [o['transport']['duration_minutes'] for o in complete if o['transport'].get('duration_minutes')]
    fastest = min(durations) if durations else None
    ratings = [Decimal(str(o['stay']['rating'])) for o in complete if o['stay'].get('rating') is not None]
    highest_rating = max(ratings) if ratings else None
    for index, option in enumerate(options[:5], 1):
        journey, stay = option.get("transport"), option.get("stay")
        if not journey or not stay:
            continue
        start = date.fromisoformat(journey["start"]).strftime("%d.%m")
        end = date.fromisoformat(journey["end"]).strftime("%d.%m.%Y")
        amount = f"{Decimal(option['budget']['known_subtotal']):,.0f}".replace(",", " ")
        name = stay["name"] if len(stay["name"]) <= 70 else stay["name"][:67] + "…"
        subtotal = Decimal(option['budget']['known_subtotal'])
        benefits, tradeoffs = [], []
        if subtotal == cheapest:
            benefits.append('минимальная цена среди этих туров')
        else:
            extra = f"{subtotal - cheapest:,.0f}".replace(',', ' ')
            tradeoffs.append(f'на {extra} ₽ дороже самого дешёвого')
        duration = journey.get('duration_minutes')
        if duration and fastest:
            if duration == fastest:
                benefits.append('самая короткая дорога туда среди этих туров')
            else:
                tradeoffs.append(f'дорога туда на {duration - fastest} мин дольше самой быстрой')
        rating = stay.get('rating')
        if rating is not None:
            label = f"оценка жилья {rating}/10"
            if Decimal(str(rating)) == highest_rating:
                benefits.append(label)
            else:
                tradeoffs.append(label + f', у альтернатив до {highest_rating}/10')
        if journey.get('baggage_included') is True:
            benefits.append('багаж включён')
        if trip.get('budget') and subtotal > Decimal(str(trip['budget'])) * (trip.get('adults', 1) if trip.get('budget_basis') == 'person' else 1):
            tradeoffs.append('билеты и жильё уже превышают бюджет')
        benefits = benefits or ['совместимые даты дороги и проживания']
        tradeoffs = tradeoffs or ['питание, местные переезды и активности оплачиваются отдельно']
        lines.append(f"- **Вариант {index}: {name}** · {start}–{end} · {journey['name']} · билеты и проживание **{amount} ₽ за группу**.\n  **Плюсы:** {'; '.join(benefits[:2])}. **Минусы:** {'; '.join(tradeoffs[:2])}.")
    eligible = [o for o in complete if trip.get('baggage') != 'required' or o['transport'].get('baggage_included') is True]
    recommended = min(eligible or complete, key=lambda o: Decimal(o['budget']['known_subtotal']))
    index = options.index(recommended) + 1
    criterion = 'С требуемым багажом' if trip.get('baggage') == 'required' and eligible else 'По цене'
    lines.append(f"\n**{criterion} рекомендую вариант {index}**: у него минимальная известная стоимость по этому критерию. Питание, местные переезды и платные активности в указанную сумму не входят.")
    selected = next((o for o in options if o["id"] == state.get("selected")), options[0])
    journey = selected.get("transport") or {}
    baggage = (journey.get("conditions") or {}).get("baggage") or {}
    if baggage.get("kg") is not None:
        lines.append(f"\nБагаж выбранного перелёта: **{baggage['kg']} кг**.")
    places = list(dict.fromkeys(c["name"] for d in selected.get("days", []) for c in d.get("candidates", [])))
    if places:
        lines.append("\n**В программе:** " + ", ".join(name if len(name) <= 50 else name[:47] + "…" for name in places[:3]) + ".")
    lines.append("\nСравните варианты в **«Туры под ключ»** и выберите тур. Пожелания можно изменить в чате.")
    return "\n".join(lines)


def render_components(state: dict) -> str:
    role = state.get("focus")
    cards = state.get("cards") or (stay_cards(state) if role == "stays" else [])
    title = "Варианты отелей" if role == "stays" else "Варианты проезда" if role == "transport" else "Тур пока не собран"
    lines = [f"**{title}**", ""]
    if not role:
        codes = {item['code'] for item in state.get('feedback', [])}
        if 'no_transport' in codes:
            lines.append('Не найден проверенный тариф на проезд туда-обратно на ваши даты и состав группы. Найденные отели и места сохранены, но готового тура с общей ценой пока нет.\n')
        elif 'no_stays' in codes:
            lines.append('Пока нет подходящего проживания с проверенной ценой на нужные даты и состав гостей. Найденные компоненты сохранены, но готового тура с общей ценой пока нет.\n')
        elif 'arrival_stay_mismatch' in codes:
            lines.append('Даты найденного проживания не совпадают с прибытием и обратным отправлением. Компоненты сохранены, но пока не образуют готовый тур.\n')
        else:
            lines.append('Для готового тура нужны совместимые дорога туда-обратно, проживание и программа. Пока доступны отдельные компоненты.\n')
    candidates = {c['id']: c for row in state.get('results', {}).values() for c in row.get('candidates', [])}
    facts_by_id = {}
    for index, card in enumerate(cards[:5], 1):
        price = card.get("price")
        basis = {'person': 'на человека', 'ticket': 'за билет', 'party': 'за группу', 'room_stay': 'за проживание'}
        cost = f" · {Decimal(price['amount']):,.0f} {price['currency']} {basis.get(price['basis'], '')}".replace(",", " ") if price else ""
        url = card.get("url")
        name = f"[{card['title']}]({url})" if url else card["title"]
        lines.append(f"- **{index}.** {name}{cost}")
        candidate = candidates.get(card['id'], {})
        conditions = candidate.get('conditions') or {}
        facts = []
        service_class = conditions.get('service_class')
        cabin = {'C': 'бизнес-класс', 'BUSINESS': 'бизнес-класс', 'Y': 'экономкласс', 'ECONOMIC': 'экономкласс',
                 'S': 'премиум-эконом', 'PREMIUM_ECONOMY': 'премиум-эконом', 'F': 'первый класс', 'FIRST': 'первый класс'}
        if isinstance(service_class, str) and service_class in cabin:
            facts.append(cabin[service_class])
        if candidate.get('baggage_included') is True:
            baggage = conditions.get('baggage') or {}
            facts.append(f"багаж {baggage['kg']} кг" if isinstance(baggage, dict) and baggage.get('kg') is not None else 'багаж включён')
        elif role == 'transport':
            facts.append('багаж не включён' if candidate.get('baggage_included') is False else 'багаж не подтверждён')
        if candidate.get('transfers') == 0:
            facts.append('прямой рейс')
        if candidate.get('duration_minutes'):
            facts.append(f"дорога туда {candidate['duration_minutes']} мин")
        if candidate.get('departure_at'):
            facts.append('отправление ' + datetime.fromisoformat(candidate['departure_at']).strftime('%d.%m в %H:%M'))
        if candidate.get('arrival_at'):
            facts.append('прибытие ' + datetime.fromisoformat(candidate['arrival_at']).strftime('%d.%m в %H:%M'))
        if role == 'stays' and candidate.get('rating') is not None:
            facts.append(f"оценка {candidate['rating']}/10")
        facts_by_id[card['id']] = facts
        if role and facts:
            lines.append('  ' + '; '.join(facts) + '.')
    if role and cards:
        eligible = [card for card in cards[:5] if card.get('selectable')]
        if eligible:
            preferred = eligible[0]
            price = preferred.get('price')
            comparable = [card for card in eligible if price and card.get('price') and
                          (card['price']['currency'], card['price']['basis']) == (price['currency'], price['basis'])]
            reasons = facts_by_id.get(preferred['id'], [])[:3]
            if comparable and Decimal(price['amount']) == min(Decimal(card['price']['amount']) for card in comparable):
                reasons = ['минимальная цена среди сопоставимых отобранных предложений', *reasons]
            if reasons:
                lines.append(f"\n**Рекомендую начать с варианта {cards.index(preferred) + 1}**: {'; '.join(reasons[:4])}.")
            if comparable:
                cheaper = min(comparable, key=lambda card: Decimal(card['price']['amount']))
                if Decimal(cheaper['price']['amount']) < Decimal(price['amount']):
                    difference = f"{Decimal(price['amount']) - Decimal(cheaper['price']['amount']):,.0f}".replace(',', ' ')
                    lines.append(f"Вариант {cards.index(cheaper) + 1} дешевле на {difference} {price['currency']} при той же основе цены; сопоставьте подтверждённые условия и время отправления перед выбором.")
    if not role:
        next_step = 'Можно проверить другие даты в согласованном окне или обсудить другой город отправления.' if 'no_transport' in codes else 'Можно продолжить подбор проживания на даты прибытия и обратного отправления.'
        lines.append('\n' + next_step + ' После проверки недостающих компонентов соберу варианты туров для сравнения.')
    else:
        lines.append("\nВыберите вариант или напишите, что изменить." if cards else "\nПожелания к поездке сохранены. Можно изменить даты, бюджет или предпочтения.")
    return "\n".join(lines)


def stay_cards(state: dict) -> list[dict]:
    from travel_agent.schemas import Candidate, TripConstraints
    from travel_agent.engine import offer_card, search_dates, usable

    trip = TripConstraints.model_validate(state.get('constraints', {}))
    now = datetime.now(timezone.utc)
    pairs = search_dates(trip)
    lower, upper = min((p[0] for p in pairs), default=trip.start), max((p[1] for p in pairs), default=trip.end)
    result = state.get('results', {}).get('stays', {})
    preferred = {ident: index for index, ident in enumerate(result.get('selected_ids', []))}
    candidates = [Candidate.model_validate(c) for c in result.get('candidates', [])]
    duration = trip.nights or (trip.duration_days - 1 if trip.duration_days else None)
    candidates = [c for c in candidates if (not duration or c.start and c.end and (c.end - c.start).days == duration) and c.role == 'stays' and c.start and c.end and lower and upper and lower <= c.start < c.end <= upper
                  and usable(c, trip.model_copy(update={'start': c.start, 'end': c.end, 'check_in': c.start, 'check_out': c.end}), now)
]
    candidates.sort(key=lambda c: (preferred.get(c.id, 100), c.price.amount))
    return [offer_card(c, trip).model_dump(mode='json') for c in candidates[:trip.option_limit]]


def component_cards(state: dict, role: str) -> list[dict]:
    if role == 'stays':
        return stay_cards(state)
    from travel_agent.engine import offer_card, transport_matches
    from travel_agent.schemas import Candidate, TripConstraints

    trip = TripConstraints.model_validate(state.get('constraints', {}))
    now = datetime.now(timezone.utc)
    row = state.get('results', {}).get(role, {})
    priority = {ident: i for i, ident in enumerate(row.get('selected_ids', []))}
    candidates = [Candidate.model_validate(c) for c in row.get('candidates', [])]
    candidates = [c for c in candidates if c.role == role and transport_matches(c, trip, now)]
    candidates.sort(key=lambda c: (trip.baggage == 'required' and c.baggage_included is not True, priority.get(c.id, 100), c.price.amount))
    return [offer_card(c, trip).model_dump(mode='json') for c in candidates[:trip.option_limit]]


def render_stays(state: dict, response: UserResponse | None = None) -> str:
    return render_components({**state, "focus": "stays", "cards": stay_cards(state)})


def llm_presenter(model, prompt: str):
    structured = model.with_structured_output(UserResponse, method="function_calling")

    async def present(state: dict) -> str:
        planning = state.get("decision", {}).get("action") == "compose"
        cards = state.get('cards') or (component_cards(state, state['focus']) if state.get('focus') in ('transport', 'stays') else [])
        component_comparison = planning and state.get('focus') in ('transport', 'stays') and bool(cards)
        if planning and not component_comparison:
            return render_options(state) if state.get("options") else render_components(state)
        card_ids = {card['id'] for card in cards}
        candidates = {candidate['id']: candidate for row in state.get('results', {}).values() for candidate in row.get('candidates', [])}
        components = [{**{key: value for key, value in candidates.get(card['id'], {}).items() if key in
                       ('id', 'name', 'price', 'start', 'end', 'departure_at', 'arrival_at', 'return_departure_at',
                        'return_arrival_at', 'duration_minutes', 'transfers', 'legs', 'conditions', 'baggage_included',
                        'stars', 'rating', 'area', 'amenities', 'source')}, 'selectable': card.get('selectable', False)}
                      for card in cards[:5]]
        research = state.get("research", {}) if state.get("decision", {}).get("action") == "research" else {}
        sources = research.get("sources", [])
        context = {
            "phase": "compare_components" if component_comparison else "answer_question",
            "focus": state.get('focus'),
            "components": components,
            "stays": stay_cards(state) if state.get("focus") == "stays" else [],
            "now": datetime.now(timezone.utc).isoformat(),
            "constraints": state.get("constraints", {}),
            "results": {
                role: {"status": row["status"], "warnings": row.get("warnings", []), "assumptions": row.get("assumptions", []), "gaps": row.get("gaps", [])}
                for role, row in state.get("results", {}).items()
            },
            "options": option_context(state),
            "selected": state.get("selected"),
            "stage": state.get("stage"),
            "choices": state.get("choices", []),
            "receipt": state.get("receipt", {}),
            "scenarios": state.get("scenarios", []),
            "research": research,
        }
        fallback = render_components(state) if component_comparison else 'Поездка сохранена. Напишите, какие детали хотите обсудить.' if state.get('autonomous') else state.get('answer', '')
        if (
            state.get("decision", {}).get("action") == "research"
            and not sources
        ):
            return "Сохранённые варианты доступны в панели поездки. Можно сравнить их цены и расположение или изменить пожелания."
        try:
            result = UserResponse.model_validate(
                await structured.ainvoke(
                    [
                        SystemMessage(content=prompt),
                        HumanMessage(content=json.dumps(context, ensure_ascii=False)),
                        *[AIMessage(content=m.content[:500]) if isinstance(m, AIMessage) and isinstance(m.content, str) else m for m in state.get("messages", [])[-8:]],
                    ]
                )
            )
            allowed = {o["id"] for o in state.get("options", [])} | card_ids
            if any(o.option_id not in allowed for o in result.options):
                return fallback
            if component_comparison and (not result.options or not any(card['id'] == result.options[0].option_id and card.get('selectable') for card in cards)):
                return fallback
            urls = {s["url"] for s in sources}
            if any(url not in urls for url in result.source_urls):
                return fallback
            if sources and not result.source_urls:
                return fallback
            answer = result.text
            if result.source_urls:
                answer += "\n\nИсточники:\n" + "\n".join(result.source_urls)
            return answer
        except (APIError, TimeoutError, ValidationError, OutputParserException) as exc:
            logging.getLogger(__name__).warning('presenter outcome=%s', type(exc).__name__)
            return fallback

    return present
