import json
from datetime import date, datetime, timezone
from decimal import Decimal

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage, SystemMessage
from openai import APIError
from pydantic import ValidationError

from travel_agent.schemas import UserResponse


def render_card(card: dict, index: int | None = None) -> str:
    prefix = f"{index}. " if index is not None else "• "
    lines = [prefix + card['title'], card['description'], f"Агрегатор / источник: {card['aggregator']}", card['url']]
    dates = card['dates']
    if dates.get('start'):
        lines.append(f"Даты: {dates['start']} — {dates.get('end') or 'не указано'}.")
    for field, label in (('departure_at', 'Отправление'), ('arrival_at', 'Прибытие'), ('return_departure_at', 'Отправление обратно')):
        if dates.get(field):
            lines.append(label + ': ' + datetime.fromisoformat(dates[field]).strftime('%d.%m.%Y %H:%M') + '.')
    price = card.get('price')
    if price:
        basis = {'person': 'на человека', 'ticket': 'за билет', 'party': 'за всю группу', 'room_stay': 'за проживание', 'unknown': '(основа цены не подтверждена)'}[price['basis']]
        lines.append(f"Цена: {Decimal(price['amount']):,.2f} {price['currency']} {basis}.".replace(',', ' '))
        if card.get('price_per_person') and price['basis'] not in ('person', 'ticket'):
            lines.append(f"В среднем на человека: {Decimal(card['price_per_person']['amount']):,.2f} {price['currency']}.".replace(',', ' '))
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
    if trip.children_ages:
        lines.append('Возраст детей: ' + ', '.join(map(str, trip.children_ages)) + '.')
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
            if role == "transport" and stage == "stays" and trip.party_budget and candidate.get("price", {}).get("currency") == 'RUB':
                remaining = trip.party_budget - Decimal(candidate["price"]["amount"])
                lines.append(f"После билетов от предела группы остаётся {remaining:,.2f} ₽ на остальные расходы.".replace(",", " "))
    explanation = state.get('results', {}).get(stage if stage in ('transport', 'stays') else 'experience', {}).get('explanation', '')
    if explanation:
        lines.append(explanation)
    for index, choice in enumerate(state.get("choices", []), 1):
        if choice.get('aggregator'):
            lines.append('\n' + render_card(choice, index))
            continue
        lines.append(f"\n{index}. {choice['title']}\n{choice['details']}")
        if choice.get("price"):
            amount = Decimal(choice["price"]["amount"])
            per_person = f"; {amount / trip.party_size:,.2f} ₽ на человека" if trip.adults else ""
            lines.append(f"{amount:,.2f} ₽ за всю группу и весь период{per_person}.".replace(",", " "))
    if stage == "scenarios":
        lines.append("Это направления поиска. Цены, наличие и свойства конкретных отелей ещё не проверены. Выберите сценарий по номеру; затем согласуем даты и транспорт.")
    elif stage in ("transport", "stays"):
        result = state.get("results", {}).get(stage, {})
        if not state.get("choices"):
            received = len(result.get("candidates", []))
            warnings = result.get("warnings", [])
            issues = {"timeout": "источник не ответил вовремя", "network_error": "ошибка соединения", "schema_error": "не удалось проверить формат ответа", "missing_key": "не настроен ключ источника", "forbidden": "доступ запрещён", "no_availability": "источник не подтвердил наличие", "llm_error": "не удалось завершить обработку моделью", "agent_limit": "достигнут лимит обработки", "payment_required": "недостаточно средств на стороне провайдера"}
            causes = list(dict.fromkeys(issues[w.split(":")[-1]] for w in warnings if w.split(":")[-1] in issues))
            lines.append(f"Сохранено ответов источников: {len(result.get('observations', []))}; карточек с проверяемыми данными: {received}.")
            if causes:
                lines.append("Причина: " + "; ".join(causes) + ".")
            lines.append("Ограниченный поиск пока не дал предложений. Сохранённые компоненты поездки остаются доступны.")
        else:
            lines.append("Выберите номер предложения: согласую его фактические даты и продолжу подбор. Для сохранённых или справочных цен сначала выполню проверку. Поисковая цена не подтверждает резерв.")
    elif stage in ("itinerary", "review", "booked"):
        if state.get('cards'):
            lines.append('\nНайденные места и активности:' if stage == 'itinerary' else '\nКомпоненты поездки:')
            lines.extend(render_card(card) for card in state['cards'])
        for option in state.get("options", []):
            amount = Decimal(option["budget"]["known_subtotal"])
            lines.append(f"\nБилеты и проживание: {amount:,.2f} ₽ за группу.".replace(",", " "))
            if trip.adults:
                lines.append(f"В среднем на человека: {amount / trip.party_size:,.2f} ₽.".replace(",", " "))
            for day in option.get("days", []):
                places = ", ".join(c["name"] for c in day["candidates"]) or "свободное время / дорога"
                lines.append(f"{day['date']}: {places}.")
            lines.extend(option.get("warnings", []))
        lines.append("Питание, трансферы, входные билеты и сборы не подтверждены и не включены; часы работы и время переездов требуют проверки.")
        if stage != "booked":
            lines.append("Согласуйте программу, чтобы перейти к корзине." if stage == "itinerary" else "Для имитации покупки введите /book confirm или явно попросите оформить имитированную покупку.")
    return "\n".join(lines)


def option_context(state: dict) -> list[dict]:
    return state.get("options", [])


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
    lines.append(
        f"{trip.get('origin', '')} → {trip.get('destination', 'Сочи')}, {start} — {end}; взрослых: {trip.get('adults', '')}."
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
        if flight:
            arrival = datetime.fromisoformat(flight["arrival_at"]).strftime(
                "%d.%m в %H:%M"
            )
            departure = datetime.fromisoformat(flight["return_departure_at"]).strftime(
                "%d.%m в %H:%M"
            )
            lines.append(
                f"Транспорт: {flight['name']}; прибытие {arrival}, отправление обратно {departure} (местное время)."
            )
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
        if any("превышает бюджет" in w for w in option["warnings"]):
            lines.append("Известная сумма уже превышает ваш бюджет.")
    lines.append(
        "Питание, местные переезды, активности и дополнительные сборы не включены. Полная стоимость неизвестна; наличие и бронирование не подтверждены."
    )
    lines.append(
        "Какой вариант обсудим? Можно спросить об отеле или районе, изменить пожелания или выбрать номер варианта."
    )
    return "\n".join(lines)


def llm_presenter(model, prompt: str):
    structured = model.with_structured_output(UserResponse, method="function_calling")

    async def present(state: dict) -> str:
        planning = state.get("decision", {}).get("action") == "compose"
        research = state.get("research", {})
        sources = research.get("sources", [])
        context = {
            "phase": "present_options" if planning else "answer_question",
            "now": datetime.now(timezone.utc).isoformat(),
            "constraints": state.get("constraints", {}),
            "results": state.get("results", {}),
            "options": option_context(state),
            "selected": state.get("selected"),
            "stage": state.get("stage"),
            "choices": state.get("choices", []),
            "receipt": state.get("receipt", {}),
            "research": research,
        }
        fallback = (
            render_options(state)
            if planning and state.get("options")
            else state.get("answer", "")
        )
        if planning and (not state.get("options") or state.get("diagnostics", {}).get("reasons")):
            return fallback
        if (
            not planning
            and state.get("decision", {}).get("action") == "research"
            and not sources and not research.get("observations")
        ):
            return "Сейчас не удалось получить веб-источники по этому вопросу. Не могу подтвердить запрошенные условия. Сохранённые варианты поездки остаются доступны; можно обсудить их цены или изменить пожелания."
        try:
            result = UserResponse.model_validate(
                await structured.ainvoke(
                    [
                        SystemMessage(content=prompt),
                        *state.get("messages", []),
                        HumanMessage(content=json.dumps(context, ensure_ascii=False)),
                    ]
                )
            )
            allowed = {o["id"] for o in state.get("options", [])}
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
                render_options(state, result) if planning and allowed else result.text
            )
            if result.source_urls:
                answer += "\n\nИсточники:\n" + "\n".join(result.source_urls)
            return answer
        except (APIError, TimeoutError, ValidationError, OutputParserException):
            return fallback

    return present
