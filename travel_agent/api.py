import asyncio
import hashlib
import hmac
import json
import logging

import aiosqlite
from contextlib import AsyncExitStack, asynccontextmanager
from functools import partial
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.memory import InMemoryStore
from langgraph.store.postgres.aio import AsyncPostgresStore

from travel_agent.agents.model import create_model
from travel_agent.agents.research import research
from travel_agent.agents.supervisor.response import llm_presenter
from travel_agent.agents.supervisor.agent import llm_decider, llm_planner
from travel_agent.agents.transport.agent import run as run_transport
from travel_agent.agents.stays.agent import run as run_stays
from travel_agent.agents.experience.agent import run as run_experience
from travel_agent.prompts import read_prompts
from travel_agent.config import environment, settings
from travel_agent.engine import simulate_purchase
from travel_agent.graph import build_graph
from travel_agent.schemas import (
    BookingRequest,
    MessageRequest,
)
from datetime import datetime, timezone


def create_app(
    graph=None,
    store=None,
    tokens: tuple[str, ...] = (),
    local_database: str | None = None,
    portal_database_url: str | None = None,
    autonomous: bool = True,
) -> FastAPI:
    if portal_database_url and local_database:
        raise ValueError("The web and Telegram application requires PostgreSQL for all storage")
    locks: dict[str, asyncio.Lock] = {}
    profile_lock = asyncio.Lock()
    run_progress: dict[str, dict] = {}
    if graph is not None:
        autonomous = 'delegate' in graph.nodes

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger = logging.getLogger('travel_agent')
        logger.setLevel(logging.INFO)
        if not logger.handlers and not logging.getLogger().handlers:
            logger.addHandler(logging.StreamHandler())
        async with AsyncExitStack() as stack:
            app.state.profile_db = None
            app.state.accounts = None
            if portal_database_url:
                from travel_agent.accounts import Accounts
                from psycopg_pool import AsyncConnectionPool

                pool = await stack.enter_async_context(AsyncConnectionPool(portal_database_url, open=False, kwargs={"autocommit": True}))
                await pool.wait(timeout=15)
                app.state.accounts = Accounts(pool)
                await app.state.accounts.setup()
            if graph is not None:
                app.state.graph = graph
                app.state.store = store or InMemoryStore()
                app.state.tokens = tokens
                app.state.persistent = False
            else:
                env = environment()
                config = settings(env)
                env.pop("TELEGRAM_BOT_TOKEN", None)
                if not config.api_token and not portal_database_url:
                    raise RuntimeError("Set TRAVEL_API_TOKEN before starting the API")
                app.state.tokens = tuple(config.api_token.get_secret_value().split(",")) if config.api_token else ()
                client = await stack.enter_async_context(
                    httpx.AsyncClient(timeout=35, follow_redirects=False)
                )
                if local_database:
                    saver = await stack.enter_async_context(
                        AsyncSqliteSaver.from_conn_string(local_database)
                    )
                    await saver.setup()
                    app.state.store = InMemoryStore()
                    db = await stack.enter_async_context(aiosqlite.connect(local_database))
                    await db.execute('CREATE TABLE IF NOT EXISTS travel_profiles (user_id TEXT PRIMARY KEY, interests TEXT NOT NULL)')
                    await db.commit()
                    async with db.execute('SELECT user_id, interests FROM travel_profiles') as cursor:
                        for user_id, interests in await cursor.fetchall():
                            await app.state.store.aput(('profiles', user_id), 'preferences', {'interests': json.loads(interests)})
                    app.state.profile_db = db
                    app.state.persistent = True
                elif config.database_url or portal_database_url:
                    dsn = portal_database_url or config.database_url.get_secret_value()
                    saver = await stack.enter_async_context(
                        AsyncPostgresSaver.from_conn_string(dsn)
                    )
                    app.state.store = await stack.enter_async_context(
                        AsyncPostgresStore.from_conn_string(dsn)
                    )
                    await saver.setup()
                    await app.state.store.setup()
                    app.state.persistent = True
                else:
                    saver = InMemorySaver()
                    app.state.store = InMemoryStore()
                    app.state.persistent = False
                prompts = read_prompts()
                models = {
                    role: create_model(config, client, max_tokens=4096, timeout=45, role=role)
                    for role in ("transport", "stays", "experience")
                }
                runners = {
                    role: partial(
                        run,
                        model=models[role],
                        client=client,
                        env=env,
                        prompt=prompts[role],
                        deadline=config.deadline,
                        autonomous=autonomous,
                    )
                    for role, run in (
                        ("transport", run_transport),
                        ("stays", run_stays),
                        ("experience", run_experience),
                    )
                }
                supervisor_model = create_model(config, client, max_tokens=2600, timeout=35, role='supervisor')
                app.state.graph = build_graph(
                    (llm_planner(supervisor_model, prompts["planner"]) if autonomous else llm_decider(supervisor_model, prompts["supervisor"])),
                    runners,
                    saver,
                    present=llm_presenter(
                        create_model(config, client, max_tokens=3000, timeout=35, role='presenter'),
                        prompts["response"],
                    ),
                    research=partial(
                        research,
                        models=models,
                        client=client,
                        env=env,
                        prompt=prompts["research"],
                    ),
                    autonomous=autonomous,
                )
            if portal_database_url:
                from travel_agent.telegram import TelegramBot

                bot_token = environment().get("TELEGRAM_BOT_TOKEN")
                app.state.bot = None
                if bot_token:
                    telegram_client = await stack.enter_async_context(httpx.AsyncClient(timeout=40, follow_redirects=False))
                    app.state.bot = TelegramBot(app, telegram_client, bot_token)
                    task = asyncio.create_task(app.state.bot.poll())
                    stack.push_async_callback(app.state.bot.stop, task)
            yield

    app = FastAPI(title="Greater Sochi Travel Agent", lifespan=lifespan)

    async def owner(request: Request, authorization: str = Header(default="")) -> str:
        supplied = authorization.removeprefix("Bearer ")
        if app.state.accounts is not None:
            session = supplied or request.cookies.get("travel_session", "")
            account = await app.state.accounts.authenticate(session) if session else None
            if account:
                if not supplied and request.method not in ("GET", "HEAD", "OPTIONS"):
                    origin = request.headers.get("origin")
                    if request.headers.get("sec-fetch-site") == "cross-site" or origin and origin != str(request.base_url).rstrip("/"):
                        raise HTTPException(403, "Запрос с другого сайта запрещён")
                return account
        if not any(
            hmac.compare_digest(supplied, token) for token in app.state.tokens if token
        ):
            raise HTTPException(401, "Invalid bearer token")
        return hashlib.sha256(supplied.encode()).hexdigest()

    def config_for(user: str, trip_id: str) -> dict:
        return {
            "configurable": {"thread_id": user + ":" + trip_id},
            "recursion_limit": 32,
        }

    async def require_trip(user: str, trip_id: str):
        if app.state.accounts is not None and await app.state.accounts.account(user):
            if not await app.state.accounts.owns(user, trip_id):
                raise HTTPException(404, "Trip not found")
            return
        entry = await app.state.store.aget(("trips", user), trip_id)
        if entry is None:
            raise HTTPException(404, "Trip not found")

    def view(values: dict) -> dict:
        result = {
            k: values.get(k, default)
            for k, default in (
                ("autonomous", autonomous),
                ("focus", None),
                ("feedback", []),
                ("status", "needs_input"),
                ("constraints", {}),
                ("revision", 0),
                ("answer", ""),
                ("plan_answer", ""),
                ("options", []),
                ("results", {}),
                ("research", {}),
                ("selected", None),
                ("bookings", {}),
                ("diagnostics", {}),
                ("stage", "scenarios"),
                ("scenarios", []),
                ("selected_scenario", None),
                ("selected_transport", None),
                ("selected_stay", None),
                ("choices", []),
                ("cards", []),
                ("notice", ""),
                ("pending_check_in", None),
                ("receipt", {}),
            )
        }
        result["messages"] = [
            {"role": "user" if isinstance(m, HumanMessage) else "assistant", "text": m.content,
             "presentation": m.response_metadata.get("presentation") if isinstance(m, AIMessage) else None}
            for m in values.get("messages", []) if isinstance(m, (HumanMessage, AIMessage)) and isinstance(m.content, str) and m.content
        ]
        if result["messages"] and result["messages"][-1]["role"] == "assistant":
            last = values.get("messages", [])[-1]
            if "presentation" not in last.response_metadata:
                result["messages"][-1]["presentation"] = presentation(values)
        return result

    def presentation(values: dict) -> dict | None:
        if not values.get("answer") or values.get("answer") != values.get("plan_answer"):
            return None
        if not (values.get("choices") or values.get("options") or values.get("receipt") or
                any(row.get("candidates") for row in values.get("results", {}).values())):
            return None
        return {key: values[key] for key in (
            "autonomous", "focus", "feedback", "status", "constraints", "revision", "options", "results",
            "selected", "diagnostics", "stage", "scenarios", "selected_scenario", "selected_transport",
            "selected_stay", "choices", "cards", "notice", "pending_check_in", "receipt",
        ) if key in values}

    async def save_presentation(user: str, trip_id: str, values: dict) -> None:
        messages = values.get("messages", [])
        if messages and isinstance(messages[-1], AIMessage) and "presentation" not in messages[-1].response_metadata:
            tagged = messages[-1].model_copy(update={"response_metadata": {
                **messages[-1].response_metadata, "presentation": presentation(values),
            }})
            await app.state.graph.aupdate_state(config_for(user, trip_id), {"messages": [tagged]})
            values["messages"] = [*messages[:-1], tagged]

    async def sync_trip(user: str, trip_id: str, values: dict) -> None:
        await save_presentation(user, trip_id, values)
        if app.state.accounts is not None and await app.state.accounts.account(user):
            await app.state.accounts.sync_trip(user, trip_id, view(values))

    @app.get("/health")
    async def health():
        return {"status": "ok", "persistent": app.state.persistent}

    @app.post("/trips")
    async def create_trip(user: str = Depends(owner)):
        trip_id = str(uuid4())
        await app.state.store.aput(
            ("trips", user),
            trip_id,
            {"created_at": datetime.now(timezone.utc).isoformat()},
        )
        await sync_trip(user, trip_id, {})
        return {"trip_id": trip_id, "revision": 0}

    @app.get("/trips/{trip_id}")
    async def read_trip(trip_id: str, user: str = Depends(owner)):
        await require_trip(user, trip_id)
        snapshot = await app.state.graph.aget_state(config_for(user, trip_id))
        return view(snapshot.values)

    @app.delete("/trips/{trip_id}", status_code=204)
    async def delete_trip(trip_id: str, user: str = Depends(owner)):
        key = user + ":" + trip_id
        async with locks.setdefault(key, asyncio.Lock()):
            await require_trip(user, trip_id)
            if app.state.graph.checkpointer:
                await app.state.graph.checkpointer.adelete_thread(key)
            await app.state.store.adelete(("trips", user), trip_id)
            if app.state.accounts is not None:
                await app.state.accounts.delete_trip(user, trip_id)
            run_progress.pop(key, None)

    @app.get('/trips/{trip_id}/status')
    async def read_status(trip_id: str, user: str = Depends(owner)):
        await require_trip(user, trip_id)
        return run_progress.get(user + ':' + trip_id, {'status': 'idle', 'label': '', 'sequence': 0})

    @app.get('/trips/{trip_id}/events')
    async def events(trip_id: str, request: Request, user: str = Depends(owner)):
        await require_trip(user, trip_id)
        async def stream():
            previous = None
            while not await request.is_disconnected():
                current = run_progress.get(user + ':' + trip_id, {'status': 'idle', 'label': '', 'sequence': 0})
                if current != previous:
                    yield 'data: ' + json.dumps(current, ensure_ascii=False) + '\n\n'
                    previous = current
                await asyncio.sleep(0.2)
        return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    @app.post("/trips/{trip_id}/messages")
    async def message(
        trip_id: str, request: MessageRequest, user: str = Depends(owner)
    ):
        await require_trip(user, trip_id)
        config = config_for(user, trip_id)
        async with locks.setdefault(user + ":" + trip_id, asyncio.Lock()):
            await require_trip(user, trip_id)
            snapshot = await app.state.graph.aget_state(config)
            if request.revision != snapshot.values.get("revision", 0):
                raise HTTPException(409, "Stale revision")
            await save_presentation(user, trip_id, snapshot.values)
            initial = {
                "messages": [HumanMessage(content=request.message)],
                "calls": 0,
                "attempts": [],
                "requested_choice": None,
                "profile_update": None,
                "repair_decision": False,
            }
            if portal_database_url and not autonomous:
                from travel_agent.support import support_reply

                reply = support_reply(request.message, snapshot.values)
                if reply:
                    await app.state.graph.aupdate_state(config, {"messages": [HumanMessage(content=request.message), AIMessage(content=reply)], "answer": reply})
                    updated = await app.state.graph.aget_state(config)
                    await sync_trip(user, trip_id, updated.values)
                    return view(updated.values)
            if not snapshot.values:
                profile = await app.state.store.aget(("profiles", user), "preferences")
                initial["constraints"] = (
                    {"interests": profile.value["interests"]} if profile else {}
                )
                if app.state.accounts is not None:
                    account = await app.state.accounts.account(user)
                    if account and account.get("city"):
                        initial["constraints"]["origin"] = account["city"]
            progress_key = user + ':' + trip_id
            run_id = str(uuid4())
            run_progress[progress_key] = {'run_id': run_id, 'status': 'running', 'sequence': 1, 'label': 'Запрос принят, планирую работу', 'previews': {}}
            try:
                async with asyncio.timeout(360 if autonomous else 420):
                    if autonomous:
                        async for kind, event in app.state.graph.astream(initial, config, stream_mode=['custom', 'updates']):
                            if kind == 'custom' and isinstance(event, dict) and event.get('label'):
                                current = run_progress[progress_key]
                                previews = {**current.get('previews', {})}
                                if event.get('preview'):
                                    previews[event['role']] = event['preview']
                                run_progress[progress_key] = {**current, 'sequence': current['sequence'] + 1, 'label': event['label'], 'previews': previews}
                        result = (await app.state.graph.aget_state(config)).values
                    else:
                        result = await app.state.graph.ainvoke(initial, config)
            except TimeoutError:
                run_progress[progress_key] = {**run_progress[progress_key], 'status': 'timeout', 'label': 'Поиск занял слишком долго; сохранённые результаты доступны'}
                raise HTTPException(504, 'Turn deadline exceeded; read current trip state before retrying') from None
            finally:
                if run_progress[progress_key]['status'] == 'running':
                    run_progress[progress_key] = {**run_progress[progress_key], 'status': 'stopped', 'label': 'Обработка завершена'}
            run_progress[progress_key] = {**run_progress[progress_key], 'status': 'finished', 'label': 'Ответ готов'}
            if result.get("profile_update") is not None:
                await save_profile(user, result["profile_update"])
            await sync_trip(user, trip_id, result)
            return view(result)

    @app.post("/trips/{trip_id}/select/{option_id}")
    async def select(
        trip_id: str, option_id: str, revision: int, user: str = Depends(owner)
    ):
        await require_trip(user, trip_id)
        config = config_for(user, trip_id)
        async with locks.setdefault(user + ":" + trip_id, asyncio.Lock()):
            await require_trip(user, trip_id)
            snapshot = await app.state.graph.aget_state(config)
            await save_presentation(user, trip_id, snapshot.values)
            if snapshot.values.get("stage") and option_id in {c["id"] for c in snapshot.values.get("choices", [])}:
                if revision != snapshot.values.get("revision", 0):
                    raise HTTPException(409, "Stale revision")
                try:
                    async with asyncio.timeout(150):
                        result = await app.state.graph.ainvoke({"requested_choice": option_id, "calls": 0, "messages": [HumanMessage(content="/select " + option_id)]}, config)
                except TimeoutError:
                    raise HTTPException(504, "Stage deadline exceeded; read current trip state") from None
                await sync_trip(user, trip_id, result)
                return view(result)
            if snapshot.values.get("stage"):
                raise HTTPException(409, "Unknown choice for the current stage")
            if revision != snapshot.values.get("revision", 0) or option_id not in [
                o["id"] for o in snapshot.values.get("options", [])
            ]:
                raise HTTPException(409, "Unknown option or stale revision")
            await app.state.graph.aupdate_state(config, {"selected": option_id})
            await sync_trip(user, trip_id, {**snapshot.values, "selected": option_id})
        return {"selected": option_id, "revision": revision}

    @app.post("/trips/{trip_id}/bookings")
    async def book(trip_id: str, request: BookingRequest, user: str = Depends(owner)):
        await require_trip(user, trip_id)
        config = config_for(user, trip_id)
        async with locks.setdefault(user + ":" + trip_id, asyncio.Lock()):
            await require_trip(user, trip_id)
            snapshot = await app.state.graph.aget_state(config)
            state = snapshot.values
            try:
                booking = simulate_purchase(state, request)
            except ValueError as exc:
                raise HTTPException(400 if not request.confirm else 409, str(exc)) from None
            if request.idempotency_key not in state.get("bookings", {}):
                await app.state.graph.aupdate_state(config, {
                    "bookings": {**state.get("bookings", {}), request.idempotency_key: booking},
                    "receipt": booking, "stage": "booked", "status": "booked", "choices": [],
                    "answer": booking["message"], "plan_answer": booking["message"],
                })
            updated = await app.state.graph.aget_state(config)
            await sync_trip(user, trip_id, updated.values)
            return booking

    async def save_profile(user: str, interests: list[str]) -> None:
        async with profile_lock:
            if app.state.profile_db is not None:
                await app.state.profile_db.execute(
                    'INSERT INTO travel_profiles(user_id, interests) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET interests=excluded.interests',
                    (user, json.dumps(interests, ensure_ascii=False)),
                )
                await app.state.profile_db.commit()
            await app.state.store.aput(("profiles", user), "preferences", {"interests": interests})
            if app.state.accounts is not None:
                from travel_agent.accounts import AccountProfile

                account = await app.state.accounts.account(user)
                if account:
                    await app.state.accounts.update(user, AccountProfile(name=account["name"], phone=account["phone"], city=account["city"], interests=interests))

    @app.get("/profile")
    async def read_profile(user: str = Depends(owner)):
        saved = await app.state.store.aget(("profiles", user), "preferences")
        return {"interests": saved.value["interests"] if saved else []}

    @app.put("/profile")
    async def profile(interests: list[str], user: str = Depends(owner)):
        if len(interests) > 10 or any(not i.strip() or len(i) > 100 for i in interests):
            raise HTTPException(422, "At most ten interests, each up to 100 characters")
        await save_profile(user, interests)
        return {"interests": interests}

    if portal_database_url:
        from travel_agent.web import mount_portal

        mount_portal(app, owner, require_trip, config_for, view, sync_trip, save_profile, locks)
    return app


app = create_app()
