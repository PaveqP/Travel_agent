import asyncio
import contextvars
import inspect
import json
import logging
import os
import runpy
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
from langchain_core.callbacks import AsyncCallbackHandler

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path('/tmp/flinters-live-e2e')
CONTEXT = contextvars.ContextVar('e2e_context', default={})
ROLE = contextvars.ContextVar('e2e_role', default='supervisor')


def emit(event: str, **fields) -> None:
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    row = {'timestamp': datetime.now(timezone.utc).isoformat(), **CONTEXT.get(),
           'role': ROLE.get(), 'event': event, **fields}
    with (PRIVATE / 'events.jsonl').open('a') as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + '\n')


class Budget:
    def __init__(self, limit: Decimal):
        if not Decimal('0') < limit <= Decimal('4.50'):
            raise ValueError('Soft limit must be at most $4.50')
        self.limit = limit
        self.spent = Decimal('0')
        self.pending: dict[str, Decimal] = {}
        self.rows: list[dict] = []

    def reserve(self, amount: Decimal, provider: str) -> str:
        if amount < 0 or self.spent + sum(self.pending.values()) + amount > self.limit:
            raise ValueError('Global E2E budget guard')
        ident = str(uuid4())
        self.pending[ident] = amount
        self.rows.append({'id': ident, **CONTEXT.get(), 'provider': provider,
                          'reserved_usd': str(amount), 'status': 'pending'})
        self.save()
        return ident

    def settle(self, ident: str, cost: Decimal | None, **usage) -> None:
        reserve = self.pending.pop(ident)
        amount = reserve if cost is None else max(cost, Decimal('0'))
        self.spent += amount
        row = next(x for x in self.rows if x['id'] == ident)
        row.update(status='settled', accounted_usd=str(amount), reported=cost is not None, **usage)
        self.save()

    def save(self) -> None:
        PRIVATE.mkdir(mode=0o700, exist_ok=True)
        (PRIVATE / 'budget.json').write_text(json.dumps({'soft_limit_usd': str(self.limit),
            'accounted_usd': str(self.spent), 'pending_usd': str(sum(self.pending.values())),
            'rows': self.rows}, ensure_ascii=False, indent=2))


def safe_params(values: dict) -> dict:
    allowed = {'origin', 'destination', 'departure_date', 'return_date', 'check_in', 'check_out',
               'adults', 'passengers', 'page_size', 'query', 'latitude', 'longitude', 'radius',
               'product_type', 'date', 'limit', 'categories', 'from', 'to', 'transport', 'points',
               'min_stars', 'min_rating', 'direct_only', 'sort', 'search_depth', 'area', 'city_name',
               'page', 'source_id', 'hotel_id', 'offer_id', 'view', 'free_cancellation',
               'hotel_amenities', 'room_amenities', 'meals', 'breakfast_included', 'price_max'}
    return {k: v for k, v in values.items() if k in allowed}


def cardinality(data) -> int | None:
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in ('candidates', 'offers', 'hotels', 'places', 'results', 'items', 'features', 'values', 'segments'):
            if isinstance(data.get(key), list):
                return len(data[key])
    return None


def install(budget: Budget) -> None:
    original_send = httpx.AsyncClient.send

    async def send(client, request, *args, **kwargs):
        host = request.url.host
        body = {}
        if request.method == 'POST':
            try:
                body = json.loads(request.content)
            except (ValueError, httpx.RequestNotRead):
                pass
        llm = host == 'openrouter.ai' and request.url.path.endswith('/chat/completions')
        mcp = host in ('mcp.tutu.ru', 'mcp-2gis.api.2gis.com')
        provider = {'mcp.tutu.ru': 'tutu', 'mcp-2gis.api.2gis.com': '2gis',
                    'api.tavily.com': 'tavily', 'api.geoapify.com': 'geoapify',
                    'api.rasp.yandex-net.ru': 'yandex_rasp', 'api.travelpayouts.com': 'travelpayouts',
                    'api.open-meteo.com': 'openmeteo', 'geocoding-api.open-meteo.com': 'openmeteo', 'api.timepad.ru': 'timepad',
                    'api.opentripmap.com': 'opentripmap'}.get(host)
        local = host in ('localhost', '127.0.0.1')
        if local:
            return await original_send(client, request, *args, **kwargs)
        amount = Decimal('0')
        operation = request.url.path
        if llm:
            provider = 'llm'
            operation = 'chat/completions'
            if body.get('model') != os.environ['MODEL'] or body.get('stream'):
                raise httpx.RequestError('Unexpected model or streaming request', request=request)
            maximum = body.get('max_tokens', body.get('max_completion_tokens'))
            if not isinstance(maximum, int) or maximum > 8192:
                raise httpx.RequestError('Unbounded LLM completion', request=request)
            amount = Decimal(len(request.content) + 8192 + maximum) * Decimal('0.000002')
        elif mcp:
            operation = body.get('params', {}).get('name', body.get('method', request.method))
            if body.get('method') == 'tools/call':
                amount = Decimal('0.05') if provider == '2gis' else Decimal('0')
        elif provider == 'tavily':
            if request.url.path not in ('/search', '/extract'):
                raise httpx.RequestError('Non-read Tavily operation blocked', request=request)
            amount = Decimal('0.016')
        elif provider == 'geoapify':
            amount = Decimal('0.01')
        elif provider in ('yandex_rasp', 'travelpayouts', 'openmeteo', 'timepad', 'opentripmap'):
            amount = Decimal('0.001')
        else:
            emit('validation_error', reason='unpriced_external_host', host=host)
            raise httpx.RequestError('Unpriced external host blocked', request=request)
        try:
            ident = budget.reserve(amount, provider)
        except ValueError:
            emit('validation_error', reason='budget_guard', provider=provider,
                 required_reserve_usd=str(amount), available_usd=str(budget.limit-budget.spent-sum(budget.pending.values())))
            raise httpx.RequestError('Global E2E budget guard', request=request) from None
        started = time.monotonic()
        emit('external_call_start', call_id=ident, provider=provider, operation=operation,
             reserve_usd=str(amount), parameters=safe_params(body.get('params', {}).get('arguments', body) if mcp else dict(request.url.params) if request.method == 'GET' else body))
        try:
            response = await original_send(client, request, *args, **kwargs)
            usage = {}
            cost = None
            count = None
            if llm:
                await response.aread()
                if response.status_code == 200:
                    usage = response.json().get('usage', {})
                    if usage.get('cost') is not None:
                        cost = Decimal(str(usage['cost']))
            elif not mcp:
                await response.aread()
                try:
                    count = cardinality(response.json())
                except ValueError:
                    pass
            metrics = {k: usage.get(k) for k in ('prompt_tokens', 'completion_tokens', 'total_tokens') if k in usage}
            metrics['cached_tokens'] = usage.get('prompt_tokens_details', {}).get('cached_tokens', 0)
            budget.settle(ident, cost, **metrics)
            emit('external_call_end', call_id=ident, provider=provider, operation=operation,
                 duration_ms=round((time.monotonic()-started)*1000), http_status=response.status_code,
                 count=count, reported_cost_usd=str(cost) if cost is not None else None,
                 accounted_usd=str(cost if cost is not None else amount), **metrics)
            return response
        except BaseException as exc:
            if ident in budget.pending:
                budget.settle(ident, None)
            emit('external_call_end', call_id=ident, provider=provider, operation=operation,
                 duration_ms=round((time.monotonic()-started)*1000), error=type(exc).__name__, accounted_usd=str(amount))
            raise

    httpx.AsyncClient.send = send

    class Trace(AsyncCallbackHandler):
        async def on_tool_start(self, serialized, input_str, *, run_id, inputs=None, **kwargs):
            if not inputs:
                try:
                    inputs = json.loads(input_str)
                except ValueError:
                    inputs = {}
            emit('tool_call_start', run_id=str(run_id), tool=serialized.get('name'),
                 parameters=safe_params(inputs if isinstance(inputs, dict) else {}))

        async def on_tool_end(self, output, *, run_id, **kwargs):
            data = getattr(output, 'content', output)
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except ValueError:
                    data = {}
            emit('tool_call_end', run_id=str(run_id), status=data.get('status') if isinstance(data, dict) else None,
                 count=cardinality(data), warnings=data.get('warnings') if isinstance(data, dict) else None)

        async def on_tool_error(self, error, *, run_id, **kwargs):
            emit('tool_call_end', run_id=str(run_id), error=type(error).__name__)

    import travel_agent.tools as tool_module
    original_tools = tool_module.build_tools

    def build_tools(*args, **kwargs):
        result = original_tools(*args, **kwargs)
        for tool in result:
            tool.callbacks = [Trace()]
        return result

    tool_module.build_tools = build_tools
    original_mcp = tool_module.runtime_call

    async def runtime_call(role, provider, name, args, env, owned=frozenset()):
        started = time.monotonic()
        result = await original_mcp(role, provider, name, args, env, owned)
        data = result.get('data', {})
        rows = data.get('offers', data.get('hotels', [])) if isinstance(data, dict) else []
        quotes = [{'id': r.get('offer_id', r.get('hotel_id')), 'price': r.get('price', (r.get('best_offer') or {}).get('price')),
                   'basis': r.get('price_basis', (r.get('best_offer') or {}).get('price_basis'))}
                  for r in rows if isinstance(r, dict)]
        emit('mcp_result', provider=provider, tool=name, initiating_agent=role, quotes=quotes,
             pricing=data.get('meta', {}).get('pricing') if isinstance(data, dict) else None,
             parameters=safe_params(args), duration_ms=round((time.monotonic()-started)*1000),
             status=result.get('status'), attempts=result.get('attempts'), count=cardinality(result.get('data')))
        return result

    tool_module.runtime_call = runtime_call

    import travel_agent.planning as planning
    for name in ('prepare', 'worker', 'evaluate', 'respond', 'finish'):
        original = getattr(planning, name)

        def wrap(fn, node_name):
            async def run(state, *args, **kwargs):
                node = kwargs.get('role', node_name)
                if node_name == 'prepare':
                    node = 'repair' if state.get('repair_decision') else 'supervisor'
                token = ROLE.set(node)
                started = time.monotonic()
                emit('graph_node_start', node=node, revision=state.get('revision'))
                if node_name == 'worker':
                    emit('agent_start', agent=node, task=state.get('active_task'))
                try:
                    if node_name == 'prepare' and 'decide' in kwargs:
                        decide = kwargs['decide']
                        async def traced_decide(current):
                            decision = await decide(current)
                            emit('typed_supervisor_decision', decision=decision.model_dump(mode='json'))
                            return decision
                        kwargs['decide'] = traced_decide
                    result = fn(state, *args, **kwargs)
                    if inspect.isawaitable(result):
                        result = await result
                    if node_name == 'prepare':
                        emit('supervisor_decision', action=result.get('decision', {}).get('action'),
                             route=result.get('route'), tasks=result.get('tasks'), revision=result.get('revision'))
                    if node_name == 'worker':
                        slot = result.get('task_results', {}).get(node, {}).get('result', {})
                        emit('agent_end', agent=node, duration_ms=round((time.monotonic()-started)*1000),
                             status=slot.get('status'), tool_calls=slot.get('tool_calls'), warnings=slot.get('warnings'),
                             count=len(slot.get('candidates', [])))
                    emit('graph_node_end', node=node, duration_ms=round((time.monotonic()-started)*1000),
                         route=result.get('route'), feedback=result.get('feedback'), status=result.get('status'))
                    return result
                except BaseException as exc:
                    emit('graph_node_end', node=node, duration_ms=round((time.monotonic()-started)*1000), error=type(exc).__name__)
                    raise
                finally:
                    ROLE.reset(token)
            return run
        setattr(planning, name, wrap(original, name))


    original_state_graph = planning.StateGraph

    def state_graph(*args, **kwargs):
        graph = original_state_graph(*args, **kwargs)
        add_node = graph.add_node

        def add(name, action=None, **options):
            if name in ('delegate', 'answer', 'research'):
                original_action = action
                async def traced(state):
                    token = ROLE.set('presenter' if name == 'answer' else name)
                    started = time.monotonic()
                    emit('graph_node_start', node=name)
                    try:
                        result = original_action(state)
                        if inspect.isawaitable(result):
                            result = await result
                        emit('graph_node_end', node=name, duration_ms=round((time.monotonic()-started)*1000))
                        return result
                    finally:
                        ROLE.reset(token)
                action = traced
            return add_node(name, action, **options)
        graph.add_node = add
        return graph

    planning.StateGraph = state_graph

    import travel_agent.web as web
    original_factory = web.create_web_app

    def factory():
        app = original_factory()

        @app.middleware('http')
        async def context(request, call_next):
            case = request.headers.get('x-e2e-case', 'preflight')
            session = request.url.path.split('/')[2] if request.url.path.startswith('/trips/') else None
            token = CONTEXT.set({'case_id': case, 'session_id': session})
            try:
                return await call_next(request)
            finally:
                CONTEXT.reset(token)
        return app

    web.create_web_app = factory


if __name__ == '__main__':
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    from travel_agent.config import environment
    os.environ.update(environment())
    budget = Budget(Decimal('4.50'))
    if (PRIVATE / 'budget.json').exists():
        if '--resume-budget' not in sys.argv:
            raise RuntimeError('Existing live budget ledger; use --resume-budget')
        saved = json.loads((PRIVATE / 'budget.json').read_text())
        budget.spent = Decimal(saved['accounted_usd']) + Decimal(saved['pending_usd'])
        budget.rows = saved['rows']
        for row in budget.rows:
            if row['status'] == 'pending':
                row.update(status='settled', accounted_usd=row['reserved_usd'], reported=False)
    budget.save()
    install(budget)
    logging.basicConfig(level=logging.WARNING)
    sys.argv = ['scripts/serve_web.py', '--local-postgres']
    runpy.run_path(str(ROOT / 'scripts/serve_web.py'), run_name='__main__')
