import logging
from datetime import date, datetime, timezone
from functools import partial

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from openai import APIError
from pydantic import ValidationError

from travel_agent.engine import apply_delta, compose, diagnose, flight_fits, usable
from travel_agent.schemas import Candidate, ResearchResult, SpecialistResult, SupervisorDecision, TripConstraints, TripDelta, TripScenario
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
        current = TripConstraints.model_validate(state.get('constraints', {}))
        revised, affected = apply_delta(current, decision.patch) if not state.get('calls', 0) and decision.action not in ('answer', 'research') else (current, set())
    except (ValidationError, ValueError, OutputParserException, APIError, TimeoutError) as exc:
        logging.getLogger(__name__).warning('supervisor outcome=%s', type(exc).__name__)
        return stop('Не удалось обработать новое сообщение. Предыдущий план и выбор сохранены; повторите запрос.', 'error')
    if decision.action in ('answer', 'research'):
        update = {'decision': decision.model_dump(mode='json'), 'requested_choice': None}
        if decision.selected_option_id in {o['id'] for o in state.get('options', [])}:
            update['selected'] = decision.selected_option_id
        return update
    now = datetime.now(timezone.utc)
    affected.update(decision.refresh)
    stage = state.get('stage', 'review' if state.get('options') else 'scenarios')
    changed = current != revised
    work = {**state, 'constraints': revised.model_dump(mode='json'), 'stage': stage, 'requested_choice': None,
            'revision': state.get('revision', 0) + int(changed or bool(affected)), 'calls': state.get('calls', 0) + 1,
            'decision': decision.model_dump(mode='json')}
    work.setdefault('options', [])
    if not state.get('stage') and state.get('options'):
        old = next((o for o in state['options'] if o['id'] == state.get('selected')), state['options'][0])
        work.update(selected_transport=old['transport']['id'] if old.get('transport') else None,
                    selected_stay=old['stay']['id'] if old.get('stay') else None)
    if 'stays' in affected:
        affected.add('experience')
    if changed or affected:
        work.update(options=[], selected=None, plan_answer='', research={}, diagnostics={}, choices=[])
        results = dict(state.get('results', {}))
        if 'stays' in affected and revised.hotel and any(c.role == 'stays' and usable(c, revised, now) for c in all_candidates(state)) and 'stays' not in decision.refresh:
            affected.discard('stays')
        for role in affected:
            results.pop(role, None)
        work['results'] = results
        if 'transport' in affected:
            work.update(stage='transport', selected_transport=None, selected_stay=None, pending_check_in=None)
        elif 'stays' in affected or 'experience' in affected and current.hotel != revised.hotel:
            work.update(stage='stays', selected_stay=None, pending_check_in=None)
        elif 'experience' in affected:
            work['stage'] = 'itinerary' if work.get('selected_stay') else 'stays'
    if decision.action == 'unsupported':
        return {**work, **stop('Полное планирование поддерживает Большой Сочи и поездки взрослых.', 'unsupported')}
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
            work.update(stage='scenarios', scenarios=[s.model_dump(mode='json') for s in proposals], selected_scenario=None)
    if decision.action == 'choose':
        choice = decision.choice_id
        stage = work['stage']
        if stage == 'scenarios':
            scenario = next((s for s in work.get('scenarios', []) if s['id'] == choice), None)
            if scenario is None:
                return {**work, **stop('Выберите сценарий из текущего списка.')}
            revised, invalid = apply_delta(revised, TripDelta(destination=scenario['destination'], purpose=revised.purpose or scenario['purpose'], interests=list(dict.fromkeys([*revised.interests, *scenario['interests']]))[:10]))
            work.update(constraints=revised.model_dump(mode='json'), selected_scenario=choice, stage='transport', choices=[], selected=None, selected_stay=None, options=[])
            work['results'] = {k: v for k, v in work.get('results', {}).items() if k not in invalid}
            if work.get('selected_transport') and selected_candidate(work, 'transport') and usable(selected_candidate(work, 'transport'), revised, now):
                work['stage'] = 'stays'
        elif stage in ('transport', 'stays'):
            if work.get('pending_check_in') and choice in {c.id for c in all_candidates(work) if c.role == 'transport'}:
                stage = 'transport'
            role = 'transport' if stage == 'transport' else 'stays'
            candidate = next((c for c in all_candidates(work) if c.id == choice and c.role == role and usable(c, revised, now)), None)
            if candidate is None or role == 'transport' and not flight_fits(candidate, revised):
                return {**work, **stop('Предложение устарело или не относится к текущему этапу. Обновите поиск.')}
            transport = selected_candidate(work, 'transport') if role == 'stays' else None
            subtotal = candidate.price.amount + (transport.price.amount if transport else 0)
            if revised.party_budget and subtotal > revised.party_budget:
                return {**work, **stop('Известная сумма выбранных компонентов уже превышает бюджет всей группы. Выберите другой вариант или измените бюджет.')}
            if role == 'transport':
                work.update(selected_transport=choice, selected_stay=None, stage='stays', options=[], selected=None)
                if candidate.arrival_at.date() != revised.stay_start or candidate.return_departure_at.date() != revised.stay_end:
                    work['pending_check_in'] = candidate.arrival_at.date().isoformat()
            else:
                work.update(selected_stay=choice, stage='itinerary', options=[], selected=None)
                work['results'] = {k: v for k, v in work.get('results', {}).items() if k != 'experience'}
        elif stage == 'itinerary' and choice in {o['id'] for o in work.get('options', [])}:
            work.update(stage='review', selected=choice)
        elif stage == 'review' and choice in {o['id'] for o in work.get('options', [])}:
            work['selected'] = choice
        else:
            return {**work, **stop('Выберите вариант из списка текущего этапа.')}
        work['revision'] += 1
    if decision.action == 'approve' and decision.confirmed:
        if work.get('pending_check_in'):
            revised, _ = apply_delta(revised, TripDelta(check_in=work['pending_check_in'], check_out=revised.end))
            work.update(constraints=revised.model_dump(mode='json'), pending_check_in=None)
            work['results'] = {k: v for k, v in work.get('results', {}).items() if k not in ('stays', 'experience')}
            work['revision'] += 1
        elif work['stage'] == 'itinerary' and work.get('options'):
            work.update(stage='review', selected=work['options'][0]['id'], revision=work['revision'] + 1)
    if work.get('pending_check_in') and revised.check_in == date.fromisoformat(work['pending_check_in']):
        work['pending_check_in'] = None
    if work['stage'] == 'scenarios':
        return {**work, 'decision': {'action': 'present'}}
    if revised.missing():
        questions = {'origin': 'Из какого города вы планируете ехать?', 'start': 'Когда хотите поехать и на сколько дней?', 'end': 'До какого числа планируете остаться?', 'adults': 'Сколько взрослых поедет?'}
        return {**work, **stop(decision.question or questions[revised.missing()[0]])}
    if revised.start < date.today():
        return {**work, **stop('Укажите будущие даты поездки.')}
    if decision.action == 'clarify':
        return {**work, **stop(decision.question or 'Уточните пожелания к текущему этапу.')}
    for role in ('transport', 'stays'):
        candidate = selected_candidate(work, role)
        if candidate is not None and not usable(candidate, revised, now):
            work.update(stage='transport' if role == 'transport' else 'stays', selected_stay=None, options=[], selected=None)
            if role == 'transport':
                work['selected_transport'] = None
            work['results'] = {k: v for k, v in work.get('results', {}).items() if k not in (('transport', 'stays', 'experience') if role == 'transport' else ('stays', 'experience'))}
            work['revision'] += 1
            break
    if work.get('pending_check_in'):
        return {**work, **stop(f"Перелёт выбран. Прилёт {work['pending_check_in']}; прежняя дата проживания с ним не совпадает. Согласуем заселение с даты прилёта? Подтвердите или выберите другой перелёт.")}
    role = {'transport': 'transport', 'stays': 'stays', 'itinerary': 'experience'}.get(work['stage'])
    if role == 'stays' and not work.get('selected_transport'):
        work.update(stage='transport')
        role = 'transport'
    if role == 'experience' and not work.get('selected_stay'):
        work.update(stage='stays')
        role = 'stays'
    work['decision'] = {'action': role if role and role not in work.get('results', {}) else 'present', 'task': decision.task}
    return work


async def specialist(state: TripState, run, config: RunnableConfig) -> dict:
    role = state['decision']['action']
    logging.getLogger(__name__).info('thread=%s role=%s revision=%s', config.get('configurable', {}).get('thread_id'), role, state['revision'])
    hotel = selected_candidate(state, 'stays')
    scenario = next((s for s in state.get('scenarios', []) if s['id'] == state.get('selected_scenario')), {})
    task = state['decision'].get('task', '') or f"Сценарий: {scenario.get('title', '')}. Цель: {state['constraints'].get('purpose', '')}. Приоритет: {scenario.get('priority', 'balance')}."
    result = SpecialistResult.model_validate(await run(TripConstraints.model_validate(state['constraints']), state['revision'], task, [hotel] if role == 'experience' and hotel else []))
    if result.revision != state['revision'] or result.role != role or any(c.role != role for c in result.candidates):
        result = SpecialistResult(role=role, revision=state['revision'], status='partial', warnings=['stale_or_invalid_result'])
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
    update = {}
    if stage == 'scenarios':
        choices = [{'id': s['id'], 'title': s['title'], 'details': f"{s['destination']}. {s['purpose']} Компромисс: {s['tradeoff']}"} for s in state.get('scenarios', [])]
    elif stage in ('transport', 'stays'):
        trip = TripConstraints.model_validate(state['constraints'])
        rows = [c for c in all_candidates(state) if c.role == stage and usable(c, trip, datetime.now(timezone.utc)) and (stage != 'transport' or flight_fits(c, trip))]
        preferred = set(state.get('results', {}).get(stage, {}).get('selected_ids', []))
        rows.sort(key=lambda c: (c.id not in preferred, c.price.amount))
        for row in rows[:5]:
            details = f"Прилёт {row.arrival_at:%d.%m.%Y %H:%M}, обратный вылет {row.return_departure_at:%d.%m.%Y %H:%M}." if stage == 'transport' else f"{row.area}; проживание {row.start:%d.%m.%Y} — {row.end:%d.%m.%Y}."
            choices.append({'id': row.id, 'title': row.name, 'details': details, 'price': row.price.model_dump(mode='json')})
        update['diagnostics'] = diagnose(trip, all_candidates(state)).model_dump(mode='json')
    elif stage == 'itinerary':
        update.update(planning(state))
        choices = [{'id': o['id'], 'title': 'Согласовать программу и перейти к корзине', 'details': 'Проверенные места и свободное время; стоимость дополнительных услуг отдельно.'} for o in update['options'] if o.get('transport') and o.get('stay')]
    elif stage == 'review':
        update.update(planning(state))
        choices = [{'id': o['id'], 'title': 'Корзина поездки', 'details': 'Билеты, проживание и предложенная программа.'} for o in update['options'] if o.get('transport') and o.get('stay')]
        update['selected'] = choices[0]['id'] if choices else None
    status = 'ready' if stage == 'review' and choices else 'needs_choice' if choices else 'partial'
    work = {**state, **update, 'choices': choices, 'status': status}
    answer = render_stage(work)
    return {**update, 'choices': choices, 'status': status, 'answer': answer, 'plan_answer': answer}


def finish(state: TripState) -> dict:
    return {'messages': [AIMessage(content=state.get('answer', ''))]}


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
    workflow.add_conditional_edges('supervisor', lambda s: s['decision']['action'], {'wait': 'finish', 'present': 'present', 'answer': 'explain', 'research': 'research', 'transport': 'transport', 'stays': 'stays', 'experience': 'experience'})
    workflow.add_edge('present', 'finish')
    workflow.add_edge('research', 'explain')
    workflow.add_edge('explain', 'finish')
    workflow.add_edge('finish', END)
    return workflow.compile(checkpointer=checkpointer)
