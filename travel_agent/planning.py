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

from travel_agent.engine import offer_card, apply_delta, compose_packages, search_dates, search_requirements, simulate_purchase, transport_matches, usable
from travel_agent.schemas import AgentTask, BookingRequest, Candidate, ResearchResult, SpecialistResult, TripConstraints, TripDelta, TurnPlan
from travel_agent.state import TripState

LABELS = {'transport': 'Сравниваю способы добраться', 'stays': 'Подбираю проживание', 'experience': 'Составляю программу по дням'}


def progress(label: str, **fields) -> None:
    get_stream_writer()({'label': label, **fields})


def search_question(missing: list[str]) -> str:
    labels = {'origin': 'город отправления', 'destination': 'направление отдыха',
              'start': 'дату начала', 'end': 'дату окончания', 'adults': 'число взрослых',
              'duration': 'длительность поездки', 'future_dates': 'актуальные даты будущей поездки с годом'}
    if 'future_dates' in missing:
        missing = [key for key in missing if key not in ('start', 'end')]
    return 'Продолжим подбор. Уточните, пожалуйста: ' + ', '.join(labels[key] for key in missing) + '.'


async def prepare(state: TripState, decide, *, reviewed: bool = False) -> dict:
    progress('Разбираю пожелания и планирую поиск')
    if state.get('requested_choice'):
        decision = TurnPlan(action='select', option_id=state['requested_choice'])
    else:
        try:
            decision = TurnPlan.model_validate(await decide(state))
        except (ValidationError, OutputParserException, APIError, TimeoutError) as exc:
            logging.getLogger(__name__).warning('planner outcome=%s fields=%s', type(exc).__name__, [(e['loc'], e['type']) for e in exc.errors(include_input=False, include_url=False)] if isinstance(exc, ValidationError) else [])
            if state.get('repair_decision'):
                decision = TurnPlan(action='plan')
            elif reviewed:
                return {'route': 'finish', 'status': 'needs_input', 'tasks': [], 'requested_choice': None,
                        'answer': search_question(state['plan_review']['unresolved_fields'])}
            else:
                return {'route': 'finish', 'status': 'error', 'answer': 'Продолжим планировать поездку. Напишите, что хотите подобрать или изменить.'}
    if reviewed and decision.action not in ('plan', 'clarify'):
        decision = TurnPlan(action='clarify', reply=search_question(state['plan_review']['unresolved_fields']))
    if state.get('repair_decision'):
        needed = {f['role'] for f in state.get('feedback', [])}
        tasks = [t for t in decision.tasks if t.role in needed and (not state.get('focus') or t.role == state['focus'])]
        for role in ('transport', 'stays', 'experience'):
            issues = [f['detail'] for f in state.get('feedback', []) if f['role'] == role]
            if issues and not any(t.role == role for t in tasks) and (not state.get('focus') or state['focus'] == role):
                tasks.append(AgentTask(role=role, goal='Исправь замечания по сохранённым фактам и целевым поиском: ' + '; '.join(issues)[:1000]))
        if any(t.role == 'transport' for t in tasks):
            tasks = [t.model_copy(update={'depends_on': ['transport'] if t.role == 'stays' else []}) for t in tasks]
        return {'tasks': [t.model_dump() for t in tasks], 'search_round': 1, 'repair_decision': False,
                'route': 'delegate' if tasks else 'respond'}
    if decision.action == 'destinations':
        try:
            revised, _ = apply_delta(TripConstraints.model_validate(state.get('constraints', {})), decision.patch)
        except ValidationError:
            return {'route': 'finish', 'status': 'needs_input', 'answer': 'Уточните даты поездки: сейчас они противоречат друг другу.'}
        proposals = decision.scenarios
        answer = decision.reply or 'Выберите направление по России или назовите любой другой город.'
        return {'route': 'finish', 'stage': 'scenarios', 'status': 'needs_input',
                'constraints': revised.model_dump(mode='json'), 'revision': state.get('revision', 0) + 1,
                'scenarios': [item.model_dump(mode='json') for item in proposals],
                'choices': [{'id': item.id, 'title': item.destination + ' — ' + item.title,
                             'details': item.purpose + ' ' + item.tradeoff} for item in proposals],
                'options': [], 'cards': [], 'selected': None, 'selected_transport': None, 'selected_stay': None,
                'selected_scenario': None, 'results': {}, 'tasks': [], 'answer': answer, 'plan_answer': answer,
                'focus': None if decision.focus == 'trip' else decision.focus or state.get('focus'),
                'requested_choice': None}
    selected_scenario = state.get('selected_scenario')
    if decision.focus == 'trip' and not state.get('options') and decision.action in ('answer', 'chat'):
        decision.action = 'plan'
    if decision.action == 'select' and state.get('stage') == 'scenarios':
        proposal = next((item for item in state.get('scenarios', []) if item['id'] == decision.option_id), None)
        if proposal:
            selected_scenario = proposal['id']
            patch = decision.patch.model_dump(exclude_none=True, exclude={'clear'})
            patch.update(destination=proposal['destination'], purpose=proposal['purpose'], interests=proposal['interests'])
            decision = TurnPlan(action='plan', patch=TripDelta(**patch))
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
        return {'route': 'finish', 'answer': decision.reply or 'Я помогу спланировать поездку по России. Расскажите, какой отдых вам хочется.', 'requested_choice': None}
    if decision.action == 'unsupported':
        return {'route': 'finish', 'status': 'unsupported', 'answer': decision.reply or 'Планирую поездки только по России для взрослых.'}
    if decision.action == 'remember':
        return {'route': 'finish', 'profile_update': decision.profile_interests, 'answer': 'Предпочтения сохранены для следующих поездок.'}
    if decision.action == 'answer' and decision.reply:
        status = state.get('status', 'needs_input')
        if status == 'error' and (state.get('options') or state.get('cards')):
            status = 'partial' if state.get('feedback') or any(row.get('status') != 'ok' for row in state.get('results', {}).values()) else 'ready'
        return {'route': 'finish', 'answer': decision.reply, 'decision': decision.model_dump(mode='json'),
                'status': status,
                'requested_choice': None}
    if decision.action in ('answer', 'research'):
        return {'route': decision.action, 'decision': {**decision.model_dump(mode='json'), 'task': decision.reply}, 'requested_choice': None}
    if decision.action == 'select':
        candidate = next((c for role in ('transport', 'stays') for c in state.get('results', {}).get(role, {}).get('candidates', []) if c['id'] == decision.option_id), None)
        if candidate is not None:
            trip = TripConstraints.model_validate(state['constraints'])
            card = offer_card(Candidate.model_validate(candidate), trip)
            from travel_agent.agents.supervisor.response import component_cards, stay_cards
            selectable = candidate['id'] in {c['id'] for c in stay_cards(state)} if candidate['role'] == 'stays' else card.selectable
            if not selectable:
                return {'route': 'finish', 'answer': 'Этот тариф устарел или не соответствует условиям. Обновите поиск.'}
            if candidate['role'] == 'transport':
                trip, _ = apply_delta(trip, TripDelta(start=candidate['start'], end=candidate['end'],
                    check_in=datetime.fromisoformat(candidate['arrival_at']).date(), check_out=datetime.fromisoformat(candidate['return_departure_at']).date()))
                standalone = state.get('focus') == 'transport'
                cards = component_cards({**state, 'constraints': trip.model_dump(mode='json')}, 'transport') if standalone else []
                tasks = [] if standalone else [AgentTask(role=role, goal='Обнови компонент для выбранного транспорта и актуальных дат.') for role in ('stays', 'experience')]
                return {'route': 'finish' if standalone else 'delegate', 'constraints': trip.model_dump(mode='json'),
                    'revision': state.get('revision', 0) + 1, 'selected_transport': candidate['id'], 'selected_stay': None,
                    'selected': None, 'requested_choice': None, 'preserved_roles': ['transport'],
                    'tasks': [t.model_dump() for t in tasks], 'search_round': 0, 'repair_decision': False, 'feedback': [],
                    'options': [], 'choices': [{'id': card['id'], 'title': card['title'], 'details': card['description']} for card in cards],
                    'cards': cards, 'plan_answer': '', 'answer': 'Билеты выбраны: ' + candidate['name'] + '.',
                    'decision': {'action': 'compose'}}
            if state.get('focus') == 'stays':
                trip, _ = apply_delta(trip, TripDelta(hotel=candidate['name'], start=candidate['start'], end=candidate['end']))
                return {'route': 'finish', 'constraints': trip.model_dump(mode='json'), 'selected_stay': candidate['id'], 'selected': None, 'requested_choice': None,
                        'answer': 'Отель выбран: ' + candidate['name'] + '.'}
            decision = TurnPlan(action='plan', focus='trip', patch=TripDelta(hotel=candidate['name']))
    if decision.action == 'select':
        option = next((o for o in state.get('options', []) if o['id'] == decision.option_id), None)
        if option is None:
            return {'route': 'finish', 'answer': 'Какой вариант из текущего списка выбираете?', 'requested_choice': None}
        trip = TripConstraints.model_validate(state['constraints'])
        journey, stay = option.get('transport'), option.get('stay')
        if not journey or not stay:
            return {'route': 'finish', 'answer': 'Этот вариант пока неполный. Сначала обновим недостающий компонент.'}
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
    focus = None if decision.focus == 'trip' else decision.focus or state.get('focus')
    if decision.action == 'clarify' and search_requirements(revised, focus):
        return {'route': 'finish', 'status': 'needs_input', 'answer': decision.reply,
                'constraints': revised.model_dump(mode='json'), 'revision': state.get('revision', 0) + int(revised != current),
                'focus': None if decision.focus == 'trip' else decision.focus or state.get('focus'),
                'decision': decision.model_dump(mode='json'), 'tasks': [], 'requested_choice': None}
    tasks = list(decision.tasks)
    if focus == 'stays' and revised.stay_start and revised.stay_end and not (revised.start and revised.end):
        revised = TripConstraints.model_validate({**revised.model_dump(), 'start': revised.stay_start, 'end': revised.stay_end})
    affected.update(role for role in ('transport', 'stays', 'experience') if role not in state.get('results', {}))
    if not focus and not search_requirements(revised):
        _, feedback = compose_packages(revised, state.get('results', {}), state.get('revision', 0))
        affected.update(item.role for item in feedback)
    required = {dep for task in tasks for dep in task.depends_on if dep not in state.get('results', {})}
    affected.update(required - {t.role for t in tasks})
    for role in sorted(affected - {t.role for t in tasks}):
        tasks.append(AgentTask(role=role, goal='Обнови зависимый компонент по актуальным ограничениям и цели поездки; сравни подходящие варианты.'))
    affected.update(t.role for t in tasks)
    if focus:
        tasks = [t.model_copy(update={'depends_on': []}) for t in tasks if t.role == focus]
    elif any(t.role == 'transport' for t in tasks):
        for task in tasks:
            if task.role == 'transport':
                task.depends_on = []
            elif task.role == 'stays':
                task.depends_on = ['transport']
            elif not revised.start or not revised.end:
                task.depends_on = list(dict.fromkeys([*task.depends_on, 'transport']))
    destination_changed = revised.destination != current.destination
    results = {} if destination_changed else dict(state.get('results', {}))
    baseline = next((o for o in state.get('options', []) if o['id'] == (decision.option_id or state.get('selected'))), {})
    if destination_changed:
        baseline = {}
    if baseline.get('days') and 'experience' in results and not results['experience'].get('days'):
        results['experience'] = {**results['experience'], 'days': [
            {'date': day['date'], 'source_ids': [c['id'] for c in day.get('candidates', [])]}
            for day in baseline['days']
        ]}
    changed = revised != current or bool(tasks)
    update = {'autonomous': True, 'focus': focus, 'constraints': revised.model_dump(mode='json'), 'revision': state.get('revision', 0) + int(changed),
              'selected_scenario': selected_scenario,
              'tasks': [t.model_dump() for t in tasks], 'search_round': 0, 'repair_decision': False, 'feedback': [],
              'results': results, 'requested_choice': None, 'selected': None if changed else state.get('selected'),
              'decision': {'action': 'compose'}, 'stage': 'review', 'route': 'delegate' if tasks else 'evaluate',
              'selected_transport': (baseline.get('transport') or {}).get('id') or (None if 'transport' in affected else state.get('selected_transport')),
              'selected_stay': (baseline.get('stay') or {}).get('id') or (None if 'stays' in affected else state.get('selected_stay'))}
    missing = search_requirements(revised, focus)
    if changed:
        update.update(options=[], choices=[], cards=[], plan_answer='', research={})
    if missing:
        logging.getLogger(__name__).warning('planner outcome=incomplete_search_parameters missing=%s', missing)
        update.update(route='finish', status='needs_input', tasks=[])
        if not reviewed:
            review = {**state, **update, 'plan_review': {'unresolved_fields': missing}}
            return {**update, **await prepare(review, decide, reviewed=True)}
        return {**update, 'answer': search_question(missing)}
    update['preserved_roles'] = [role for role, key in (('transport', 'selected_transport'), ('stays', 'selected_stay'))
                                 if role not in affected and state.get(key)]
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
    requested_trip = trip
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
    if role == 'stays':
        transport_pending = any(t['role'] == 'transport' for t in state.get('tasks', [])) and not completed(state, 'transport')
        journeys = [] if transport_pending or state.get('focus') == 'stays' else [Candidate.model_validate(c) for c in state.get('results', {}).get('transport', {}).get('candidates', [])]
        journeys = [c for c in journeys if transport_matches(c, requested_trip, datetime.now().astimezone())]
        preferred_modes = [next(c for c in journeys if c.transport_mode == mode) for mode in dict.fromkeys(c.transport_mode for c in journeys)]
        windows = list(dict.fromkeys((str(c.arrival_at.date()), str(c.return_departure_at.date())) for c in [*preferred_modes, *journeys]))[:3]
        context['transport_stays'] = [{'check_in': start, 'check_out': end} for start, end in windows]
        if journeys:
            chosen = journeys[0]
            pairs = search_dates(requested_trip)
            trip = TripConstraints.model_validate({**trip.model_dump(), 'start': chosen.start, 'end': chosen.end,
                'check_in': chosen.arrival_at.date(), 'check_out': chosen.return_departure_at.date(),
                'date_from': min(p[0] for p in pairs), 'date_to': max(p[1] for p in pairs)})
    context['current_transport'] = next((c for c in state.get('results', {}).get('transport', {}).get('candidates', [])
                                         if state.get('focus') != 'stays' and c['id'] == state.get('selected_transport')), None)
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
    elif role == 'experience' and not result.days and context.get('current_days'):
        from travel_agent.schemas import ProposedDay
        saved_days = [ProposedDay.model_validate(day) for day in context['current_days']]
        known_ids = {c.id for c in result.candidates}
        if any(day.source_ids for day in saved_days) and all(ident in known_ids for day in saved_days for ident in day.source_ids) and all(trip.start <= day.date <= trip.end for day in saved_days):
            result.days = saved_days
            result.status = 'partial'
            result.warnings.append('program_update_incomplete')
    progress({'transport': 'Предложения транспорта получены', 'stays': 'Варианты проживания получены', 'experience': 'Программа подготовлена'}[role],
             role=role, status=result.status, candidates=len(result.candidates),
             preview=[offer_card(c, trip).model_dump(mode='json') for c in result.candidates[:3]])
    return {'task_results': {role: {'revision': state['revision'], 'round': state.get('search_round', 0), 'result': result.model_dump(mode='json')}}}


def evaluate(state: TripState, *, final: bool = False) -> dict:
    results = dict(state.get('results', {}))
    for role, slot in state.get('task_results', {}).items():
        if slot.get('revision') == state['revision'] and slot.get('round') == state.get('search_round', 0):
            row = dict(slot['result'])
            row['candidates'] = list({c['id']: c for c in row['candidates']}.values())
            results[role] = row
    pending = any(not completed(state, t['role']) for t in state.get('tasks', []))
    if pending and not final:
        return {'results': results, 'route': 'delegate'}
    if not final:
        progress('Проверяю совместимость, бюджет и программу')
    trip = TripConstraints.model_validate(state['constraints'])
    if state.get('focus') in ('transport', 'stays'):
        from travel_agent.agents.supervisor.response import component_cards
        cards = component_cards({**state, 'results': results}, state['focus'])
        return {'results': results, 'options': [], 'choices': [{'id': c['id'], 'title': c['title'], 'details': c['description']} for c in cards], 'cards': cards, 'feedback': [], 'stage': state['focus'], 'status': 'ready' if cards else 'partial', 'route': 'respond', 'repair_decision': False, 'decision': {'action': 'compose'}}
    package_results = dict(results)
    scheduled = {task['role'] for task in state.get('tasks', [])}
    for role, key in (('transport', 'selected_transport'), ('stays', 'selected_stay')):
        if role in state.get('preserved_roles', []) and role not in scheduled and state.get(key) and role in results:
            saved = [c for c in results[role].get('candidates', []) if c['id'] == state[key]]
            if saved:
                package_results[role] = {**results[role], 'candidates': saved}
    options, feedback = compose_packages(trip, package_results, state['revision'])
    corrections = []
    if not final:
        for role, code in (('stays', 'arrival_stay_mismatch'), ('experience', 'empty_program')):
            issues = [f.detail for f in feedback if f.role == role and f.code == code]
            if issues and not completed(state, role):
                corrections.append(AgentTask(role=role, goal='Исправь совместимость компонента с найденным транспортом: ' + '; '.join(issues)[:1000]))
    if corrections:
        roles = {task.role for task in corrections}
        return {'results': results, 'tasks': [t for t in state.get('tasks', []) if t['role'] not in roles] + [t.model_dump() for t in corrections], 'route': 'delegate'}
    from travel_agent.agents.supervisor.response import component_cards
    cards = [] if options else [card for role in ('transport', 'stays') for card in component_cards({**state, 'results': results}, role)]
    chosen = next((o for o in options if o.transport.id == state.get('selected_transport') and o.stay.id == state.get('selected_stay')), options[0] if options else None)
    return {'results': results, 'options': [o.model_dump(mode='json') for o in options],
            'feedback': [f.model_dump() for f in feedback], 'stage': 'review',
            'selected': chosen.id if chosen else None,
            'selected_transport': chosen.transport.id if chosen else state.get('selected_transport'),
            'selected_stay': chosen.stay.id if chosen else state.get('selected_stay'),
            'cards': cards,
            'choices': [{'id': o.id, 'title': f"{o.transport.name} + {o.stay.name}", 'details': f"Известная сумма {o.budget.known_subtotal} ₽ за группу"} for o in options]
                if options else [{'id': c['id'], 'title': c['title'], 'details': c['description']} for c in cards],
            'status': 'ready' if options and not feedback else 'partial', 'decision': {'action': 'compose'},
            'route': 'repair' if feedback and state.get('search_round', 0) == 0 else 'respond', 'repair_decision': bool(feedback) and state.get('search_round', 0) == 0}


async def respond(state: TripState, present) -> dict:
    from travel_agent.agents.supervisor.response import render_options, render_components

    progress('Сравниваю варианты и готовлю рекомендацию')
    fallback = render_options(state) if state.get('options') else render_components(state)
    answer = await present({**state, 'answer': fallback}) if present else fallback
    return {'answer': answer, 'plan_answer': answer}


def finish(state: TripState) -> dict:
    metadata = {'component_comparison': True} if state.get('route') == 'respond' and state.get('focus') in ('transport', 'stays') else {}
    return {'messages': [AIMessage(content=state.get('answer', ''), response_metadata=metadata)], 'repair_decision': False}


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
