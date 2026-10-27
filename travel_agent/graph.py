import logging
from datetime import date, datetime, timezone
from functools import partial
from decimal import Decimal

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from openai import APIError
from pydantic import ValidationError

from travel_agent.engine import apply_delta, compose, diagnose, offer_card, simulate_purchase, quote_current
from travel_agent.schemas import BookingRequest, Candidate, ResearchResult, SpecialistResult, SupervisorDecision, TripConstraints, TripDelta, TripScenario, SourceObservation
from travel_agent.state import TripState


def all_candidates(state: TripState) -> list[Candidate]:
    return [Candidate.model_validate(c) for r in state.get('results', {}).values() for c in r.get('candidates', [])]


def selected_candidate(state: TripState, role: str) -> Candidate | None:
    ident = state.get('selected_transport' if role == 'transport' else 'selected_stay')
    return next((c for c in all_candidates(state) if c.role == role and c.id == ident), None)


def stop(answer: str, status: str = 'needs_input') -> dict:
    return {'decision': {'action': 'wait'}, 'answer': answer, 'status': status, 'requested_choice': None}


async def supervise(state: TripState, decide) -> dict:
    try:
        decision = SupervisorDecision(action='choose', choice_id=state['requested_choice']) if state.get('requested_choice') else SupervisorDecision.model_validate(await decide(state))
        if decision.action == 'chat':
            return {**stop(decision.reply or 'Привет! Я помогу спланировать поездку в Большой Сочи.'), 'status': state.get('status', 'needs_input')}
        if decision.action == 'remember':
            if decision.profile_interests is None:
                return stop('Какие предпочтения сохранить для следующих поездок?')
            return {**stop('Предпочтения сохранены для следующих поездок.'), 'profile_update': decision.profile_interests}
        current = TripConstraints.model_validate(state.get('constraints', {}))
        revised, affected = apply_delta(current, decision.patch) if not state.get('calls', 0) and decision.action not in ('answer', 'research') else (current, set())
    except (ValidationError, ValueError, OutputParserException, APIError, TimeoutError) as exc:
        paths = [(e['loc'], e['type']) for e in exc.errors(include_input=False, include_url=False)] if isinstance(exc, ValidationError) else []
        logging.getLogger(__name__).warning('supervisor outcome=%s fields=%s', type(exc).__name__, paths)
        payment_required = isinstance(exc, APIError) and getattr(exc, 'status_code', None) == 402
        if any(r.get('candidates') for r in state.get('results', {}).values()) and state.get('stage'):
            return {'decision': {'action': 'present'}, 'requested_choice': None, 'notice': 'LLM-провайдер отклонил запрос из-за недостаточного баланса. Сохранённые данные и выбор доступны.' if payment_required else 'Новое условие не удалось применить. Показываю сохранённые предложения с датами и актуальностью; прежний выбор сохранён.'}
        return stop('LLM-провайдер отклонил запрос из-за недостаточного баланса. Пополните баланс у провайдера; данные поездки сохранены.' if payment_required else 'Не удалось обработать новое сообщение. Предыдущий план и выбор сохранены; повторите запрос.', 'error')
    if decision.action in ('answer', 'research'):
        update = {'decision': decision.model_dump(mode='json'), 'requested_choice': None}
        if decision.selected_option_id in {o['id'] for o in state.get('options', [])}:
            update['selected'] = decision.selected_option_id
        return update
    now = datetime.now(timezone.utc)
    affected.update(decision.refresh)
    changed_fields = {name for name in TripConstraints.model_fields if getattr(current, name) != getattr(revised, name)}
    if decision.action == 'experience' and state.get('selected_stay') and changed_fields <= {'interests'}:
        affected.discard('stays')
        affected.add('experience')
    stage = state.get('stage', 'review' if state.get('options') else 'scenarios')
    changed = current != revised
    work = {**state, 'constraints': revised.model_dump(mode='json'), 'stage': stage, 'requested_choice': None,
            'revision': state.get('revision', 0) + int(changed or bool(affected)), 'calls': state.get('calls', 0) + 1,
            'decision': decision.model_dump(mode='json'), 'notice': ''}
    work.setdefault('options', [])
    if not state.get('stage') and state.get('options'):
        old = next((o for o in state['options'] if o['id'] == state.get('selected')), state['options'][0])
        work.update(selected_transport=old['transport']['id'] if old.get('transport') else None,
                    selected_stay=old['stay']['id'] if old.get('stay') else None)
    if 'stays' in affected:
        affected.add('experience')
    if changed or affected:
        work.update(options=[], selected=None, plan_answer='', diagnostics={}, choices=[])
        results = dict(state.get('results', {}))
        work['results'] = results
        if 'transport' in affected:
            work.update(stage='transport', selected_transport=None, selected_stay=None, pending_check_in=None)
        elif 'stays' in affected or 'experience' in affected and current.hotel != revised.hotel:
            work.update(stage='stays', selected_stay=None, pending_check_in=None)
        elif 'experience' in affected:
            work['stage'] = 'itinerary' if work.get('selected_stay') else 'stays'
    if decision.action == 'unsupported':
        return {**work, **stop('Планирование поддерживает отдых в Большом Сочи.', 'unsupported')}
    if decision.bypass_scenarios or decision.action in ('transport', 'stays', 'experience'):
        if not work.get('selected_scenario'):
            work['selected_scenario'] = 'direct'
        if work['stage'] == 'scenarios':
            work['stage'] = 'itinerary' if decision.action == 'experience' else decision.action if decision.action in ('transport', 'stays') else 'transport'
    if decision.action == 'scenarios' or not work.get('selected_scenario') and work['stage'] != 'review':
        proposals = decision.scenarios or [TripScenario.model_validate(s) for s in work.get('scenarios', [])]
        if not proposals:
            if not revised.purpose and not revised.interests:
                return {**work, **stop(decision.question or 'Какой отдых вам хочется: море и прогулки, горы, спокойный или активный?')}
            proposals = [TripScenario(id='personal', title='Поездка по вашим пожеланиям', destination=revised.destination,
                                      purpose=revised.purpose or ', '.join(revised.interests), interests=revised.interests,
                                      tradeoff='Цены, наличие и детали проверим после выбора сценария.')]
        if len({s.id for s in proposals}) != len(proposals):
            return {**work, **stop('Не удалось разделить сценарии. Уточните желаемый формат отдыха.', 'error')}
        if not work.get('scenarios') or decision.action == 'scenarios':
            work.update(stage='scenarios', scenarios=[s.model_dump(mode='json') for s in proposals], selected_scenario=None,
                        revision=work['revision'] + 1, options=[], selected=None)
    if decision.action == 'choose':
        choice = decision.choice_id
        stage = work['stage']
        if stage == 'scenarios':
            scenario = next((s for s in work.get('scenarios', []) if s['id'] == choice), None)
            if scenario is None:
                return {**work, **stop('Выберите сценарий из текущего списка.')}
            revised, invalid = apply_delta(revised, TripDelta(destination=scenario['destination'], purpose=revised.purpose or scenario['purpose'], interests=list(dict.fromkeys([*revised.interests, *scenario['interests']]))))
            affected.update(invalid)
            work.update(constraints=revised.model_dump(mode='json'), selected_scenario=choice, stage='transport', choices=[], selected=None, selected_stay=None, options=[])
            if work.get('selected_transport') and selected_candidate(work, 'transport') and quote_current(selected_candidate(work, 'transport'), now):
                work['stage'] = 'stays'
        elif stage in ('transport', 'stays'):
            if work.get('pending_check_in') and choice in {c.id for c in all_candidates(work) if c.role == 'transport'}:
                stage = 'transport'
            role = 'transport' if stage == 'transport' else 'stays'
            candidate = next((c for c in all_candidates(work) if c.id == choice and c.role == role), None)
            if candidate is None:
                return {**work, **stop('Выберите предложение из текущего списка.')}
            if role == 'transport' and not quote_current(candidate, now):
                if candidate.start and candidate.end:
                    revised, _ = apply_delta(revised, TripDelta(start=candidate.start, end=candidate.end))
                work.update(stage='transport', constraints=revised.model_dump(mode='json'), selected_transport=None, selected_stay=None,
                            options=[], selected=None, revision=work['revision'] + 1, notice='Проверяю выбранное предложение у агрегатора; сохранённая цена не считается подтверждённой.')
                return {**work, 'decision': {'action': 'transport', 'task': decision.task}}
            if role == 'stays' and not quote_current(candidate, now):
                return {**work, 'notice': 'Обновляю проживание для выбранных билетов. Сохранённые варианты остаются видимыми.', 'decision': {'action': 'stays', 'task': decision.task}}
            transport = selected_candidate(work, 'transport') if role == 'stays' else None
            subtotal = (candidate.price.amount if candidate.price else 0) + (transport.price.amount if transport and transport.price else 0)
            if revised.party_budget and subtotal > revised.party_budget:
                work['notice'] = 'Известная сумма выбранных компонентов выше бюджета. Показываю её как альтернативу; перед покупкой бюджет нужно согласовать.'
            if role == 'transport' and (not candidate.arrival_at or not candidate.return_departure_at):
                return {**work, **stop('Для выбранного транспорта нужно уточнить оба направления и время прибытия. Предложение сохранено.')}
            if role == 'transport':
                revised, _ = apply_delta(revised, TripDelta(start=candidate.start, end=candidate.end,
                    check_in=candidate.arrival_at.date(), check_out=candidate.return_departure_at.date(),
                    clear=['nights'] if revised.nights and revised.nights != (candidate.return_departure_at.date() - candidate.arrival_at.date()).days else []))
                affected.update(('stays', 'experience'))
                work.update(constraints=revised.model_dump(mode='json'), selected_transport=choice, selected_stay=None, stage='stays', options=[], selected=None, pending_check_in=None)
                work['notice'] = f'Билеты выбраны на {candidate.start:%d.%m}–{candidate.end:%d.%m}. Проживание подбираю под фактическое прибытие: {revised.stay_start:%d.%m}–{revised.stay_end:%d.%m}.'
            else:
                affected.add('experience')
                work.update(selected_stay=choice, stage='itinerary', options=[], selected=None)
        elif stage == 'itinerary' and choice in {o['id'] for o in work.get('options', [])}:
            work.update(stage='review', selected=choice)
        elif stage == 'review' and choice in {o['id'] for o in work.get('options', [])}:
            work['selected'] = choice
        else:
            return {**work, **stop('Выберите вариант из списка текущего этапа.')}
        work['revision'] += 1
    if decision.action == 'approve' and decision.confirmed:
        if work.get('pending_check_in'):
            revised, _ = apply_delta(revised, TripDelta(check_in=work['pending_check_in'], check_out=revised.end, clear=['nights'] if revised.nights else []))
            work.update(constraints=revised.model_dump(mode='json'), pending_check_in=None)
            work['revision'] += 1
        elif work['stage'] == 'itinerary' and work.get('options'):
            work.update(stage='review', selected=work['options'][0]['id'], revision=work['revision'] + 1)
    if work.get('pending_check_in') and revised.check_in == date.fromisoformat(work['pending_check_in']):
        work['pending_check_in'] = None
    if work['stage'] == 'scenarios':
        return {**work, 'decision': {'action': 'present'}}
    missing = revised.missing()
    if decision.action == 'stays':
        missing = [field for field in missing if field != 'origin']
    elif decision.action == 'experience':
        missing = []
    elif decision.action == 'transport':
        missing = [field for field in missing if field != 'end']
    if revised.travel_month or revised.date_from or revised.date_to:
        missing = [field for field in missing if field not in ('start', 'end')]
        if not revised.start or not revised.end:
            work['notice'] = 'Подбираю варианты в указанном периоде; конкретные даты и длительность согласуем по результатам поиска.'
    if missing:
        questions = {'origin': 'Из какого города вы планируете ехать?', 'start': 'Когда хотите поехать и на сколько дней?', 'end': 'До какого числа планируете остаться?', 'adults': 'Сколько взрослых поедет?'}
        return {**work, **stop(decision.question or questions[missing[0]])}
    if revised.start and revised.start < date.today() and not (revised.travel_month or revised.date_from or revised.date_to):
        return {**work, **stop('Укажите будущие даты поездки.')}
    duration = (revised.end - revised.start).days if revised.start and revised.end else None
    stay_nights = (revised.stay_end - revised.stay_start).days if revised.stay_start and revised.stay_end else None
    if not (revised.date_from and revised.date_to) and duration is not None and (revised.duration_days and duration + 1 != revised.duration_days or revised.nights and stay_nights != revised.nights):
        return {**work, **stop(f'На выбранные даты получается {stay_nights} ночей и {duration + 1} календарных дней. Сохраняем даты или ранее указанную длительность?')}
    if decision.action == 'clarify' and work['stage'] not in ('transport', 'stays'):
        return {**work, **stop(decision.question or 'Уточните пожелания к текущему этапу.')}
    for role in ('transport', 'stays'):
        candidate = selected_candidate(work, role)
        if candidate is not None and not quote_current(candidate, now):
            work.update(stage='transport' if role == 'transport' else 'stays', selected_stay=None, options=[], selected=None)
            if role == 'transport':
                work['selected_transport'] = None
            work['revision'] += 1
            break
    if work.get('pending_check_in'):
        nights = (revised.end - date.fromisoformat(work['pending_check_in'])).days
        answer = f"Транспорт выбран. Прибытие {work['pending_check_in']}; прежняя дата проживания с ним не совпадает. Заселение с прибытия даст {nights} ночей проживания. Согласуем эти даты? Подтвердите или выберите другой транспорт."
        return {**work, **stop(answer), 'plan_answer': answer}
    if decision.action == 'checkout':
        if work['stage'] == 'booked' and work.get('receipt'):
            return {**work, **stop(work['receipt']['message'], 'booked')}
        if not decision.confirmed or work['stage'] != 'review' or changed or affected:
            return {**work, **stop('Сначала согласуйте все компоненты и программу, затем явно подтвердите имитацию покупки.')}
        return {**work, 'decision': {'action': 'checkout'}}
    role = decision.action if decision.action in ('transport', 'stays', 'experience') else next((r for r in ('transport', 'stays', 'experience') if r in affected), None) or {'transport': 'transport', 'stays': 'stays', 'itinerary': 'experience'}.get(work['stage'])
    if role in ('transport', 'stays'):
        work['stage'] = role
    if role == 'stays' and not work.get('selected_transport') and decision.action != 'stays':
        work.update(stage='transport')
        role = 'transport'
    if role == 'experience' and not work.get('selected_stay') and decision.action != 'experience':
        work.update(stage='stays')
        role = 'stays'
    cached = [c for c in all_candidates(work) if c.role == role]
    fresh = any(quote_current(c, now) for c in cached)
    refresh = role and (decision.action == role or role in affected or role not in work.get('results', {}) or role in ('transport', 'stays') and not fresh)
    if refresh and cached:
        work['notice'] = 'Обновляю предложения по текущим условиям; сохранённые цены показываю с пометками актуальности.'
    work['decision'] = {'action': role if refresh else 'present', 'task': decision.task}
    return work


async def specialist(state: TripState, run, config: RunnableConfig) -> dict:
    role = state['decision']['action']
    logging.getLogger(__name__).info('thread=%s role=%s revision=%s', config.get('configurable', {}).get('thread_id'), role, state['revision'])
    hotel = selected_candidate(state, 'stays')
    scenario = next((s for s in state.get('scenarios', []) if s['id'] == state.get('selected_scenario')), {})
    task = f"Сценарий: {scenario.get('title', '')}. Формат: {scenario.get('purpose', '')}. Цель пользователя: {state['constraints'].get('purpose', '')}. Приоритет: {scenario.get('priority', 'balance')}. Задача этапа: {state['decision'].get('task', '')}"
    previous = [Candidate.model_validate(c) for c in state.get('results', {}).get(role, {}).get('candidates', [])]
    observed = [*state.get('results', {}).get(role, {}).get('observations', []), *state.get('research', {}).get('observations', [])]
    observations = list({row['id']: SourceObservation.model_validate(row) for row in observed if row['role'] == role}.values())
    task += '\nИстория пользователя: ' + '\n'.join(str(message.content) for message in state.get('messages', []) if message.type == 'human')
    result = SpecialistResult.model_validate(await run(TripConstraints.model_validate(state['constraints']), state['revision'], task, [*previous, *([hotel] if role == 'experience' and hotel else [])], observations=observations))
    if result.revision != state['revision'] or result.role != role or any(c.role != role for c in result.candidates):
        result = SpecialistResult(role=role, revision=state['revision'], status='partial', warnings=['stale_or_invalid_result'])
    previous = [Candidate.model_validate(c) for c in state.get('results', {}).get(role, {}).get('candidates', [])]
    merged = {c.id: c for c in [*previous, *result.candidates]}
    result.candidates = list(merged.values())
    result.observations = list({row.id: row for row in [*observations, *result.observations]}.values())
    return {'results': {**state.get('results', {}), role: result.model_dump(mode='json')}}


def planning(state: TripState) -> dict:
    trip = TripConstraints.model_validate(state.get('constraints', {}))
    chosen = [c for role in ('transport', 'stays') if (c := selected_candidate(state, role)) is not None]
    activities = state.get('results', {}).get('experience', {})
    selected = set(activities.get('selected_ids', []))
    chosen += [c for c in all_candidates(state) if c.role == 'experience' and (not selected or c.id in selected)]
    options = compose(trip, chosen, state.get('revision', 0))
    return {'options': [o.model_dump(mode='json') for o in options], 'diagnostics': diagnose(trip, chosen).model_dump(mode='json')}


def present_stage(state: TripState) -> dict:
    from travel_agent.agents.supervisor.response import render_stage

    stage = state.get('stage', 'scenarios')
    choices = []
    cards = []
    update = {}
    if stage == 'scenarios':
        choices = [{'id': s['id'], 'title': s['title'], 'details': f"{s['destination']}. {s['purpose']} Компромисс: {s['tradeoff']}"} for s in state.get('scenarios', [])]
    elif stage in ('transport', 'stays'):
        trip = TripConstraints.model_validate(state['constraints'])
        rows = [c for c in all_candidates(state) if c.role == stage]
        preferred = set(state.get('results', {}).get(stage, {}).get('selected_ids', []))
        cards = [offer_card(c, trip).model_dump(mode='json') for c in rows]
        cards.sort(key=lambda c: c['id'] not in preferred)
        choices = [{**c, 'details': c['description']} for c in cards]
        update['diagnostics'] = diagnose(trip, all_candidates(state)).model_dump(mode='json')
    elif stage == 'itinerary':
        update.update(planning(state))
        trip = TripConstraints.model_validate(state['constraints'])
        cards = [offer_card(c, trip).model_copy(update={'selectable': False}).model_dump(mode='json') for c in all_candidates(state) if c.role == 'experience']
        choices = [{'id': o['id'], 'title': 'Согласовать программу и перейти к корзине', 'details': 'Проверенные места и свободное время; стоимость дополнительных услуг отдельно.'} for o in update['options'] if o.get('transport') and o.get('stay')]
    elif stage == 'review':
        update.update(planning(state))
        trip = TripConstraints.model_validate(state['constraints'])
        cards = [offer_card(c, trip).model_dump(mode='json') for role in ('transport', 'stays') if (c := selected_candidate(state, role)) is not None]
        choices = [{'id': o['id'], 'title': 'Корзина поездки', 'details': 'Билеты, проживание и предложенная программа.'} for o in update['options'] if o.get('transport') and o.get('stay')]
        update['selected'] = choices[0]['id'] if choices else None
    status = 'booked' if stage == 'booked' else 'ready' if stage == 'review' and choices else 'needs_choice' if choices else 'partial'
    work = {**state, **update, 'choices': choices, 'cards': cards, 'status': status}
    answer = render_stage(work)
    return {**update, 'choices': choices, 'cards': cards, 'status': status, 'answer': answer, 'plan_answer': answer}


def finish(state: TripState) -> dict:
    return {'messages': [AIMessage(content=state.get('answer', ''))]}


def checkout(state: TripState) -> dict:
    request = BookingRequest(option_id=state.get('selected') or '', revision=state['revision'], confirm=True,
                             idempotency_key=f"chat-{state['revision']}-{state.get('selected', '')}")
    try:
        booking = simulate_purchase(state, request)
    except ValueError as exc:
        messages = {'Known subtotal exceeds the party budget': 'Известная сумма превышает бюджет группы. Пересоберите корзину или измените бюджет.',
                    'Quotes expired; refresh search': 'Котировки устарели. Обновите поиск перед оформлением.',
                    'Passenger composition requires verification': 'Стоимость для текущего состава пассажиров требует проверки. Предложения сохранены.',
                    'Currency conversion requires a dated rate': 'Исходные цены сохранены; перед оформлением нужен подтверждённый курс валюты.'}
        return stop(messages.get(str(exc), 'Корзина ещё не готова. Согласуйте транспорт, проживание и программу.'), 'partial')
    return {'bookings': {**state.get('bookings', {}), request.idempotency_key: booking}, 'receipt': booking,
            'stage': 'booked', 'status': 'booked', 'choices': [], 'answer': booking['message'], 'plan_answer': booking['message']}


def build_graph(decide, run, checkpointer, present=None, research=None):
    workflow = StateGraph(TripState)
    workflow.add_node('supervisor', partial(supervise, decide=decide))
    if not isinstance(run, dict):
        original = run
        run = {role: partial(original, role) for role in ('transport', 'stays', 'experience')}
    for role in ('transport', 'stays', 'experience'):
        workflow.add_node(role, partial(specialist, run=run[role]))
        workflow.add_edge(role, 'present')
    workflow.add_node('present', present_stage)
    workflow.add_node('checkout', checkout)

    async def explain(state):
        if present:
            return {'answer': await present(state)}
        from travel_agent.agents.supervisor.response import render_stage

        return {'answer': render_stage(state)}

    async def investigate(state):
        result = ResearchResult.model_validate(await research(state)) if research else ResearchResult(role=state['decision']['research_role'], warnings=['unavailable'])
        return {'research': result.model_dump(mode='json')}

    workflow.add_node('explain', explain)
    workflow.add_node('research', investigate)
    workflow.add_node('finish', finish)
    workflow.add_edge(START, 'supervisor')
    workflow.add_conditional_edges('supervisor', lambda s: s['decision']['action'], {'wait': 'finish', 'present': 'present', 'answer': 'explain', 'research': 'research', 'transport': 'transport', 'stays': 'stays', 'experience': 'experience', 'checkout': 'checkout'})
    workflow.add_edge('present', 'finish')
    workflow.add_edge('checkout', 'finish')
    workflow.add_edge('research', 'explain')
    workflow.add_edge('explain', 'finish')
    workflow.add_edge('finish', END)
    return workflow.compile(checkpointer=checkpointer)
