import json
import logging
from datetime import datetime
from functools import partial

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from openai import APIError
from pydantic import ValidationError

from travel_agent.engine import offer_card, apply_delta, compose_packages, search_dates, simulate_purchase, usable
from travel_agent.schemas import AgentTask, BookingRequest, Candidate, ResearchResult, SpecialistResult, TripConstraints, TurnPlan
from travel_agent.state import TripState

LABELS = {'transport': 'Сравниваю способы добраться', 'stays': 'Подбираю проживание', 'experience': 'Составляю программу по дням'}


def progress(label: str, **fields) -> None:
    get_stream_writer()({'label': label, **fields})


async def prepare(state: TripState, decide) -> dict:
    progress('Разбираю пожелания и планирую поиск')
    if state.get('requested_choice'):
        decision = TurnPlan(action='select', option_id=state['requested_choice'])
    else:
        try:
            decision = TurnPlan.model_validate(await decide(state))
        except (ValidationError, OutputParserException, APIError, TimeoutError) as exc:
            logging.getLogger(__name__).warning('planner outcome=%s fields=%s', type(exc).__name__, [(e['loc'], e['type']) for e in exc.errors(include_input=False, include_url=False)] if isinstance(exc, ValidationError) else [])
            return {'route': 'finish', 'status': 'error', 'answer': 'Не удалось обработать сообщение. Сохранённая поездка не изменена; повторите запрос.'}
    if state.get('repair_decision'):
        tasks = [t for t in decision.tasks if not state.get('focus') or t.role == state['focus']]
        if not tasks and any(f['role'] == 'experience' for f in state.get('feedback', [])):
            tasks = [AgentTask(role='experience', goal='Исправь программу по замечаниям, используя сохранённые факты и только необходимый дополнительный поиск: ' + '; '.join(f['detail'] for f in state['feedback'] if f['role'] == 'experience')[:1000])]
        return {'tasks': [t.model_dump() for t in tasks], 'search_round': 1, 'repair_decision': False,
                'route': 'delegate' if tasks else 'respond'}
    if decision.action == 'select':
        chosen = next((o for o in state.get('options', []) if o['id'] == decision.option_id), {})
        patch = decision.patch
        hotel_matches = not patch.hotel or patch.hotel.casefold() in (chosen.get('stay') or {}).get('name', '').casefold()
        dates_match = all(value is None or str(value) == (chosen.get('transport') or {}).get(name) for name, value in (('start', patch.start), ('end', patch.end)))
        other_changes = any(name not in ('hotel', 'start', 'end') and value != state.get('constraints', {}).get(name) for name, value in patch.model_dump(mode='json', exclude_none=True, exclude={'clear'}).items())
        if not hotel_matches or not dates_match or other_changes or patch.clear:
            decision.action = 'plan'
            decision.tasks = []
    if decision.action == 'chat':
        return {'route': 'finish', 'answer': decision.reply or 'Я помогу спланировать поездку по Большому Сочи. Расскажите, какой отдых вам хочется.', 'requested_choice': None}
    if decision.action == 'unsupported':
        return {'route': 'finish', 'status': 'unsupported', 'answer': decision.reply or 'Планирую поездки только по Большому Сочи для взрослых.'}
    if decision.action == 'remember':
        return {'route': 'finish', 'profile_update': decision.profile_interests, 'answer': 'Предпочтения сохранены для следующих поездок.'}
    if decision.action in ('answer', 'research'):
        return {'route': decision.action, 'decision': {**decision.model_dump(mode='json'), 'task': decision.reply}, 'requested_choice': None}
    if decision.action == 'select' and state.get('focus') == 'stays':
        candidate = next((c for c in state.get('results', {}).get('stays', {}).get('candidates', []) if c['id'] == decision.option_id), None)
        if candidate is not None:
            from travel_agent.agents.supervisor.response import stay_cards
            if candidate['id'] not in {c['id'] for c in stay_cards(state)}:
                return {'route': 'finish', 'answer': 'Этот тариф устарел или не соответствует условиям. Обновите поиск отеля.'}
            from travel_agent.schemas import TripDelta
            trip, _ = apply_delta(TripConstraints.model_validate(state['constraints']), TripDelta(hotel=candidate['name'], start=candidate['start'], end=candidate['end']))
            return {'route': 'finish', 'constraints': trip.model_dump(mode='json'), 'selected_stay': candidate['id'], 'selected': None, 'requested_choice': None,
                    'answer': 'Отель выбран: ' + candidate['name'] + '. Чтобы собрать поездку и имитировать покупку, попросите подобрать транспорт и программу с этим отелем.'}
    if decision.action == 'select':
        option = next((o for o in state.get('options', []) if o['id'] == decision.option_id), None)
        if option is None:
            return {'route': 'finish', 'answer': 'Какой вариант из текущего списка выбираете?', 'requested_choice': None}
        trip = TripConstraints.model_validate(state['constraints'])
        journey, stay = option.get('transport'), option.get('stay')
        if not journey or not stay:
            return {'route': 'finish', 'answer': 'Этот вариант пока неполный. Сначала обновим недостающий компонент.'}
        from travel_agent.schemas import TripDelta
        trip, _ = apply_delta(trip, TripDelta(start=journey['start'], end=journey['end'], check_in=stay['start'], check_out=stay['end'], hotel=decision.patch.hotel))
        return {'route': 'finish', 'constraints': trip.model_dump(mode='json'), 'selected': option['id'],
                'selected_transport': journey['id'], 'selected_stay': stay['id'], 'requested_choice': None,
                'answer': 'Вариант выбран. Можно обсудить детали или явно подтвердить имитацию покупки.', 'stage': 'review'}
    if decision.action == 'checkout':
        if not decision.confirmed:
            return {'route': 'finish', 'answer': 'Подтвердите именно имитацию покупки; реальные места не резервируются.'}
        try:
            request = BookingRequest(option_id=state.get('selected') or '', revision=state['revision'], confirm=True,
                                     idempotency_key=f"chat-{state['revision']}-{state.get('selected', '')}")
            booking = simulate_purchase(state, request)
        except (ValueError, ValidationError) as exc:
            return {'route': 'finish', 'answer': 'Для оформления нужен выбранный свежий вариант, удовлетворяющий требованиям. Обновите или уточните поездку.'}
        return {'route': 'finish', 'bookings': {**state.get('bookings', {}), request.idempotency_key: booking}, 'receipt': booking,
                'stage': 'booked', 'status': 'booked', 'answer': booking['message'], 'choices': []}
    current = TripConstraints.model_validate(state.get('constraints', {}))
    try:
        revised, affected = apply_delta(current, decision.patch)
    except ValidationError:
        return {'route': 'finish', 'status': 'needs_input', 'answer': 'Даты или состав поездки противоречат друг другу. Уточните изменяемые параметры.'}
    tasks = list(decision.tasks)
    focus = None if decision.focus == 'trip' or state.get('options') else decision.focus or state.get('focus')
    affected.update(role for role in ('transport', 'stays', 'experience') if role not in state.get('results', {}))
    required = {dep for task in tasks for dep in task.depends_on if dep not in state.get('results', {})}
    affected.update(required - {t.role for t in tasks})
    for role in sorted(affected - {t.role for t in tasks}):
        tasks.append(AgentTask(role=role, goal='Обнови зависимый компонент по актуальным ограничениям и цели поездки; сравни подходящие варианты.'))
    affected.update(t.role for t in tasks)
    if focus:
        tasks = [t.model_copy(update={'depends_on': []}) for t in tasks if t.role == focus]
    elif any(t.role == 'transport' for t in tasks) and (not revised.start or not revised.end):
        tasks = [t.model_copy(update={'depends_on': list(dict.fromkeys([*t.depends_on, 'transport'])) if t.role != 'transport' else []}) for t in tasks]
    results = dict(state.get('results', {}))
    baseline = next((o for o in state.get('options', []) if o['id'] == (decision.option_id or state.get('selected'))), {})
    if baseline.get('days') and 'experience' in results and not results['experience'].get('days'):
        results['experience'] = {**results['experience'], 'days': [
            {'date': day['date'], 'source_ids': [c['id'] for c in day.get('candidates', [])]}
            for day in baseline['days']
        ]}
    changed = revised != current or bool(tasks)
    update = {'autonomous': True, 'focus': focus, 'constraints': revised.model_dump(mode='json'), 'revision': state.get('revision', 0) + int(changed),
              'tasks': [t.model_dump() for t in tasks], 'search_round': 0, 'repair_decision': False, 'feedback': [],
              'results': results, 'requested_choice': None, 'selected': None if changed else state.get('selected'),
              'decision': {'action': 'compose'}, 'stage': 'review', 'route': 'delegate' if tasks else 'evaluate',
              'selected_transport': (baseline.get('transport') or {}).get('id') or (None if 'transport' in affected else state.get('selected_transport')),
              'selected_stay': (baseline.get('stay') or {}).get('id') or (None if 'stays' in affected else state.get('selected_stay'))}
    missing = revised.missing()
    if search_dates(revised):
        missing = [name for name in missing if name not in ('start', 'end')]
    if changed:
        update.update(options=[], choices=[], cards=[], plan_answer='', research={})
    if missing:
        questions = {'origin': 'Из какого города поедете?', 'start': 'Когда хотите поехать?', 'end': 'До какого числа?', 'adults': 'Сколько взрослых поедет?'}
        return {**update, 'route': 'finish', 'status': 'needs_input', 'answer': questions[missing[0]], 'tasks': []}
    if revised.start and revised.start < datetime.now().date():
        return {**update, 'route': 'finish', 'status': 'needs_input', 'answer': 'Нужны будущие даты поездки.', 'tasks': []}
    return update


def completed(state: TripState, role: str) -> bool:
    slot = state.get('task_results', {}).get(role, {})
    return slot.get('revision') == state['revision'] and slot.get('round') == state.get('search_round', 0)


def dispatch(state: TripState):
    tasks = [AgentTask.model_validate(t) for t in state.get('tasks', [])]
    scheduled = {t.role for t in tasks}
    ready = [t for t in tasks if not completed(state, t.role) and all(completed(state, role) if role in scheduled else role in state.get('results', {}) for role in t.depends_on)]
    return [Send(t.role, {**state, 'active_task': t.model_dump()}) for t in ready] or 'evaluate'


async def worker(state: dict, run, role: str) -> dict:
    task = AgentTask.model_validate(state['active_task'])
    trip = TripConstraints.model_validate(state['constraints'])
    progress(LABELS[role], role=role, status='running')
    if not trip.start or not trip.end:
        transports = [Candidate.model_validate(c) for c in state.get('results', {}).get('transport', {}).get('candidates', [])]
        chosen = next((c for c in transports if c.arrival_at and c.return_departure_at), None)
        if chosen:
            trip = TripConstraints.model_validate({**trip.model_dump(), 'start': chosen.start, 'end': chosen.end,
                                                  'check_in': chosen.arrival_at.date(), 'check_out': chosen.return_departure_at.date()})
    if role != 'transport' and (not trip.start or not trip.end):
        pairs = search_dates(trip)
        if pairs:
            start, end = pairs[0]
            trip = TripConstraints.model_validate({**trip.model_dump(), 'start': start, 'end': end, 'date_from': trip.date_from or min(p[0] for p in pairs), 'date_to': trip.date_to or max(p[1] for p in pairs)})
    if role != 'transport' and (not trip.start or not trip.end):
        result = SpecialistResult(role=role, revision=state['revision'], status='partial', warnings=['missing_dates'])
        return {'task_results': {role: {'revision': state['revision'], 'round': state.get('search_round', 0), 'result': result.model_dump(mode='json')}}}
    previous = [Candidate.model_validate(c) for c in state.get('results', {}).get('stays', {}).get('candidates', [])]
    known = [Candidate.model_validate(c) for c in state.get('results', {}).get(role, {}).get('candidates', [])]
    latest = next((m.content for m in reversed(state.get('messages', [])) if isinstance(m, HumanMessage)), '')
    context = {'user_request': latest, 'selected_transport': state.get('selected_transport'),
               'selected_stay': state.get('selected_stay')}
    context['current_transport'] = next((c for c in state.get('results', {}).get('transport', {}).get('candidates', [])
                                         if c['id'] == state.get('selected_transport')), None)
    if context['current_transport']:
        context['current_transport'] = {k: v for k, v in context['current_transport'].items() if k != 'provider_details'}
    if role == 'experience':
        option = next((o for o in state.get('options', []) if o['id'] == state.get('selected')), {})
        context['current_days'] = state.get('results', {}).get(role, {}).get('days') or [
            {'date': day['date'], 'source_ids': [c['id'] for c in day.get('candidates', [])]}
            for day in option.get('days', [])
        ]
    goal = task.goal + '\n' + json.dumps(context, ensure_ascii=False)
    result = SpecialistResult.model_validate(await run(trip, state['revision'], goal, [*known, *(previous if role == 'experience' else [])]))
    if result.revision != state['revision'] or result.role != role or any(c.role != role for c in result.candidates):
        result = SpecialistResult(role=role, revision=state['revision'], status='partial', warnings=['stale_or_invalid_result'])
    progress({'transport': 'Предложения транспорта получены', 'stays': 'Варианты проживания получены', 'experience': 'Программа подготовлена'}[role],
             role=role, status=result.status, candidates=len(result.candidates),
             preview=[offer_card(c, trip).model_dump(mode='json') for c in result.candidates[:3]])
    return {'task_results': {role: {'revision': state['revision'], 'round': state.get('search_round', 0), 'result': result.model_dump(mode='json')}}}


def evaluate(state: TripState) -> dict:
    results = dict(state.get('results', {}))
    for role, slot in state.get('task_results', {}).items():
        if slot.get('revision') == state['revision'] and slot.get('round') == state.get('search_round', 0):
            row = dict(slot['result'])
            row['candidates'] = list({c['id']: c for c in row['candidates']}.values())[-100:]
            results[role] = row
    pending = any(not completed(state, t['role']) for t in state.get('tasks', []))
    if pending:
        return {'results': results, 'route': 'delegate'}
    progress('Проверяю совместимость, бюджет и программу')
    trip = TripConstraints.model_validate(state['constraints'])
    if state.get('focus') == 'stays':
        from travel_agent.agents.supervisor.response import stay_cards
        cards = stay_cards({**state, 'results': results})
        return {'results': results, 'options': [], 'choices': [{'id': c['id'], 'title': c['title'], 'details': c['description']} for c in cards], 'cards': cards, 'feedback': [], 'status': 'ready' if cards else 'partial', 'route': 'respond', 'repair_decision': False, 'decision': {'action': 'compose'}}
    package_results = dict(results)
    scheduled = {task['role'] for task in state.get('tasks', [])}
    for role, key in (('transport', 'selected_transport'), ('stays', 'selected_stay')):
        if role not in scheduled and state.get(key) and role in results:
            saved = [c for c in results[role].get('candidates', []) if c['id'] == state[key]]
            if saved:
                package_results[role] = {**results[role], 'candidates': saved}
    options, feedback = compose_packages(trip, package_results, state['revision'])
    chosen = next((o for o in options if o.transport.id == state.get('selected_transport') and o.stay.id == state.get('selected_stay')), options[0] if options else None)
    return {'results': results, 'options': [o.model_dump(mode='json') for o in options],
            'feedback': [f.model_dump() for f in feedback], 'stage': 'review',
            'selected': chosen.id if chosen else None,
            'selected_transport': chosen.transport.id if chosen else state.get('selected_transport'),
            'selected_stay': chosen.stay.id if chosen else state.get('selected_stay'),
            'constraints': trip.model_copy(update={
                'start': chosen.transport.start, 'end': chosen.transport.end,
                'check_in': chosen.stay.start, 'check_out': chosen.stay.end,
            }).model_dump(mode='json') if chosen else state['constraints'],
            'choices': [{'id': o.id, 'title': f"{o.transport.name} + {o.stay.name}", 'details': f"Известная сумма {o.budget.known_subtotal} ₽ за группу"} for o in options],
            'status': 'ready' if options and not feedback else 'partial', 'decision': {'action': 'compose'},
            'route': 'repair' if feedback and state.get('search_round', 0) == 0 else 'respond', 'repair_decision': bool(feedback) and state.get('search_round', 0) == 0}


async def respond(state: TripState, present) -> dict:
    from travel_agent.agents.supervisor.response import render_options, render_card, render_stays

    progress('Сравниваю варианты и готовлю рекомендацию')
    fallback = render_options(state) if state.get('options') else 'Не удалось собрать проверенную поездку. Полученные данные сохранены; можно изменить условия или повторить поиск.'
    if not state.get('options') and not state.get('focus'):
        trip = TripConstraints.model_validate(state['constraints'])
        cards = [offer_card(Candidate.model_validate(c), trip).model_dump(mode='json') for row in state.get('results', {}).values() for c in row.get('candidates', [])[:2]]
        fallback += '\n\n' + '\n\n'.join(render_card(c) for c in cards)
    if state.get('focus') == 'stays':
        fallback = render_stays(state)
    answer = await present({**state, 'answer': fallback}) if present else fallback
    if state.get('feedback'):
        labels = {'no_transport': 'Не удалось подтвердить билеты на подходящие даты.', 'no_stays': 'Не удалось подтвердить проживание на выбранные даты.', 'no_day_plan': 'Программа по дням пока не подтверждена.', 'mountain_days_mismatch': 'Не удалось подтвердить требуемое число горных дней.', 'arrival_stay_mismatch': 'Даты проживания пока не согласованы с прибытием транспорта.', 'ski_program_mismatch': 'Программа пока не соответствует горнолыжной цели.'}
        answer += '\n\nЧто пока не удалось подтвердить:\n' + '\n'.join('• ' + labels.get(f['code'], 'Часть программы не прошла проверку фактов и совместимости.') for f in state['feedback'])
    return {'answer': answer, 'plan_answer': answer}


def finish(state: TripState) -> dict:
    return {'messages': [AIMessage(content=state.get('answer', ''))], 'repair_decision': False}


def build_planning_graph(decide, runners, checkpointer, present=None, research=None):
    workflow = StateGraph(TripState)
    workflow.add_node('supervisor', partial(prepare, decide=decide))
    workflow.add_node('repair', partial(prepare, decide=decide))
    for role in ('transport', 'stays', 'experience'):
        workflow.add_node(role, partial(worker, run=runners[role], role=role))
        workflow.add_edge(role, 'evaluate')
    workflow.add_node('delegate', lambda state: {})
    workflow.add_conditional_edges('delegate', dispatch, ['transport', 'stays', 'experience', 'evaluate'])
    workflow.add_node('evaluate', evaluate)
    workflow.add_conditional_edges('evaluate', lambda s: s['route'], {'delegate': 'delegate', 'repair': 'repair', 'respond': 'respond'})
    workflow.add_node('respond', partial(respond, present=present))
    async def answer(state):
        return {'answer': await present(state)} if present else {'answer': 'Сведения о поездке сохранены в вариантах.'}
    async def investigate(state):
        result = ResearchResult.model_validate(await research(state)) if research else ResearchResult(role=state['decision']['research_role'], warnings=['unavailable'])
        return {'research': result.model_dump(mode='json')}
    workflow.add_node('answer', answer)
    workflow.add_node('research', investigate)
    workflow.add_edge('research', 'answer')
    workflow.add_node('finish', finish)
    workflow.add_edge(START, 'supervisor')
    routes = {'delegate': 'delegate', 'evaluate': 'evaluate', 'respond': 'respond', 'answer': 'answer', 'research': 'research', 'finish': 'finish'}
    workflow.add_conditional_edges('supervisor', lambda s: s['route'], routes)
    workflow.add_conditional_edges('repair', lambda s: s['route'], routes)
    for node in ('respond', 'answer'):
        workflow.add_edge(node, 'finish')
    workflow.add_edge('finish', END)
    return workflow.compile(checkpointer=checkpointer)
