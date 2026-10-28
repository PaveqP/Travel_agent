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
            **{role: {k: value for k, value in (o.get(role) or {}).items() if k in ('id', 'name', 'area', 'price', 'start', 'end', 'departure_at', 'arrival_at', 'arrival_city', 'return_departure_at', 'return_arrival_at', 'transport_mode', 'stars', 'rating', 'baggage_included', 'conditions', 'variant_id', 'source', 'duration_minutes', 'transfers')} for role in ('transport', 'stay')},
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
    comments = {o.option_id: o for o in response.options} if response else {}
    lines = [response.text if response else "Вот доступные варианты поездки:"]
    trip = state.get("constraints", {})
    start = (
        date.fromisoformat(trip["start"]).strftime("%d.%m.%Y")
        if trip.get("start")
        else "дата не указана"
    )
    end = (
        date.fromisoformat(trip["end"]).strftime("%d.%m.%Y")
        if trip.get("end")
        else "дата не указана"
    )
    if not trip.get('start') or not trip.get('end'):
        if trip.get('travel_month'):
            start, end = 'поиск в месяце ' + trip['travel_month'], 'даты каждого варианта ниже'
    lines.append(
        f"{trip.get('origin', '')} → {trip.get('destination', 'Россия')}, {start} — {end}; взрослых: {trip.get('adults', '')}."
    )
    if state.get("diagnostics", {}).get("reasons"):
        lines.append(state.get("answer", ""))
    if trip.get("budget"):
        from travel_agent.schemas import TripConstraints

        constraints = TripConstraints.model_validate(trip)
        basis = "на человека" if constraints.budget_basis == "person" else "на группу"
        lines.append(f"Бюджет: {constraints.budget} ₽ {basis}; предел группы {constraints.party_budget} ₽.")
    for index, option in enumerate(state.get("options", []), 1):
        stay, flight = option.get("stay"), option.get("transport")
        lines.append(
            f"\n{index}. {stay['name'] if stay else 'Проживание пока не найдено'}"
            + (f" — {stay.get('area') or 'район не определён'}" if stay else "")
        )
        if stay:
            lines.append('Проживание: ' + stay['start'] + ' — ' + stay['end'] + '.')
        if flight:
            lines.append('Поездка: ' + flight['start'] + ' — ' + flight['end'] + '.')
            arrival = datetime.fromisoformat(flight["arrival_at"]).strftime(
                "%d.%m в %H:%M"
            )
            departure = datetime.fromisoformat(flight["return_departure_at"]).strftime(
                "%d.%m в %H:%M"
            )
            label = 'Поезд' if flight.get('transport_mode') == 'rail' else 'Перелёт'
            lines.append(f"{label}: {flight['name']}; прибытие {arrival}, отправление обратно {departure} (местное время).")
            if flight.get('arrival_city'):
                lines.append('Транспорт прибывает: ' + flight['arrival_city'] + '. Местный трансфер не включён.')
            conditions = flight.get('conditions') or {}
            if conditions.get('fare_family'):
                lines.append('Тариф: ' + conditions['fare_family'] + '.')
            baggage = conditions.get('baggage') or {}
            if baggage.get('kg') is not None:
                lines.append(f"Зарегистрированный багаж: {baggage['kg']} кг.")
            elif flight.get('baggage_included') is True:
                lines.append('Зарегистрированный багаж включён в тариф.')
        amount = (
            f"{Decimal(option['budget']['known_subtotal']):,.2f}".rstrip("0")
            .rstrip(".")
            .replace(",", " ")
            .replace(".", ",")
        )
        lines.append(
            f"Билеты и проживание: известная сумма {amount} ₽ на всю группу и весь период."
        )
        if not flight or not stay:
            lines.append("Сумма неполная: транспорт или проживание ещё не найдены.")
        if option["id"] in comments:
            comment = comments[option["id"]]
            lines.append(f"Подойдёт: {comment.benefit}\nКомпромисс: {comment.tradeoff}")
        lines.extend(w for w in option['warnings'] if any(term in w for term in ('багаж', 'снаряжения', 'Горных дней')))
        if any("превышает бюджет" in w for w in option["warnings"]):
            lines.append("Известная сумма уже превышает ваш бюджет.")
    if state.get('options'):
        mountain_days = sum(d.get('mountain', False) for d in state['options'][0].get('days', []))
        lines.append(f'\nПрограмма первого варианта (горных дней: {mountain_days}):')
        for day in state['options'][0].get('days', []):
            lines.append(day['date'] + ': ' + (', '.join(c['name'] for c in day['candidates']) or 'дорога / свободное время') + '.')
    if len(state.get("options", [])) < 5:
        lines.append(
            "\nПоказываю столько различных вариантов, сколько удалось проверить; до пяти."
        )
    lines.append(
        "Питание, местные переезды, активности и дополнительные сборы не включены. Полная стоимость неизвестна; наличие и бронирование не подтверждены."
    )
    lines.append(
        "Какой вариант обсудим? Можно спросить об отеле или районе, изменить пожелания или выбрать номер варианта."
    )
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
                  and (trip.holiday_type != 'ski' or c.area == 'Красная Поляна')]
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
    cards = stay_cards(state)
    if not cards:
        return (response.text + '\n\n' if response else '') + 'Не удалось подтвердить тариф подходящего отеля на выбранные даты. Можно расширить диапазон или повторить поиск отелей.'
    comments = {o.option_id: o for o in response.options} if response else {}
    lines = [response.text if response else 'Вот найденные варианты проживания по вашим условиям:']
    for index, card in enumerate(cards, 1):
        lines.append('\n' + render_card(card, index))
        comment = comments.get(card['id'])
        if comment:
            lines.append('Подойдёт: ' + comment.benefit + '\nЧто проверить: ' + comment.tradeoff)
    lines.append('Поисковый тариф не подтверждает резерв. Близость к подъёмнику и вид из конкретного номера считаются подтверждёнными только при наличии сведений источника; цена с видом может отличаться.')
    return '\n'.join(lines)


def llm_presenter(model, prompt: str):
    structured = model.with_structured_output(UserResponse, method="function_calling")

    async def present(state: dict) -> str:
        planning = state.get("decision", {}).get("action") == "compose"
        stays_only = planning and state.get("focus") == "stays"
        research = {"sources": state.get("results", {}).get("stays", {}).get("sources", [])} if stays_only else state.get("research", {}) if state.get("decision", {}).get("action") == "research" else {}
        sources = research.get("sources", [])
        context = {
            "phase": "compare_stays" if stays_only else "present_options" if planning else "answer_question",
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
        if stays_only:
            fallback = render_stays(state)
        elif planning:
            fallback = render_options(state) if state.get('options') else state.get('answer', '')
        else:
            fallback = 'Не удалось подготовить ответ на этот вопрос. Поездка сохранена; уточните вопрос или повторите сообщение.' if state.get('autonomous') else state.get('answer', '')
        if planning and not stays_only and (not state.get("options") or state.get("diagnostics", {}).get("reasons")):
            return fallback
        if (
            not planning
            and state.get("decision", {}).get("action") == "research"
            and not sources
        ):
            return "Сейчас не удалось получить веб-источники по этому вопросу. Не могу подтвердить детали отеля или района. Сохранённые варианты поездки остаются доступны; можно обсудить их цены или изменить пожелания."
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
            allowed = {c["id"] for c in stay_cards(state)} if stays_only else {o["id"] for o in state.get("options", [])}
            if any(o.option_id not in allowed for o in result.options):
                return fallback
            if planning and {o.option_id for o in result.options} != allowed:
                return fallback
            urls = {s["url"] for s in sources}
            if any(url not in urls for url in result.source_urls):
                return fallback
            if sources and not result.source_urls:
                return fallback
            answer = (
                render_stays(state, result) if stays_only else render_options(state, result) if planning and allowed else result.text
            )
            if result.source_urls:
                answer += "\n\nИсточники:\n" + "\n".join(result.source_urls)
            return answer
        except (APIError, TimeoutError, ValidationError, OutputParserException) as exc:
            logging.getLogger(__name__).warning('presenter outcome=%s', type(exc).__name__)
            return fallback

    return present
