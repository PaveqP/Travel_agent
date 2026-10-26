import asyncio
import hashlib
import hmac
from contextlib import AsyncExitStack, asynccontextmanager
from functools import partial
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.memory import InMemoryStore
from langgraph.store.postgres.aio import AsyncPostgresStore

from travel_agent.agents.model import create_model
from travel_agent.agents.research import research
from travel_agent.agents.supervisor.response import llm_presenter
from travel_agent.agents.supervisor.agent import llm_decider
from travel_agent.agents.transport.agent import run as run_transport
from travel_agent.agents.stays.agent import run as run_stays
from travel_agent.agents.experience.agent import run as run_experience
from travel_agent.prompts import read_prompts
from travel_agent.config import environment, settings
from travel_agent.engine import usable
from travel_agent.graph import build_graph
from travel_agent.schemas import (
    BookingRequest,
    MessageRequest,
    TripConstraints,
    TripOption,
)
from datetime import datetime, timezone


def create_app(
    graph=None,
    store=None,
    tokens: tuple[str, ...] = (),
    local_database: str | None = None,
) -> FastAPI:
    locks: dict[str, asyncio.Lock] = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with AsyncExitStack() as stack:
            if graph is not None:
                app.state.graph = graph
                app.state.store = store or InMemoryStore()
                app.state.tokens = tokens
                app.state.persistent = False
            else:
                env = environment()
                config = settings(env)
                if not config.api_token:
                    raise RuntimeError("Set TRAVEL_API_TOKEN before starting the API")
                app.state.tokens = tuple(config.api_token.get_secret_value().split(","))
                client = await stack.enter_async_context(
                    httpx.AsyncClient(timeout=35, follow_redirects=False)
                )
                if local_database:
                    saver = await stack.enter_async_context(
                        AsyncSqliteSaver.from_conn_string(local_database)
                    )
                    await saver.setup()
                    app.state.store = InMemoryStore()
                    app.state.persistent = True
                elif config.database_url:
                    dsn = config.database_url.get_secret_value()
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
                    role: create_model(config, client)
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
                    )
                    for role, run in (
                        ("transport", run_transport),
                        ("stays", run_stays),
                        ("experience", run_experience),
                    )
                }
                supervisor_model = create_model(config, client)
                app.state.graph = build_graph(
                    llm_decider(supervisor_model, prompts["supervisor"]),
                    runners,
                    saver,
                    present=llm_presenter(
                        create_model(config, client, max_tokens=4096),
                        prompts["response"],
                    ),
                    research=partial(
                        research,
                        models=models,
                        client=client,
                        env=env,
                        prompt=prompts["research"],
                    ),
                )
            yield

    app = FastAPI(title="Greater Sochi Travel Agent", lifespan=lifespan)

    async def owner(authorization: str = Header(default="")) -> str:
        supplied = authorization.removeprefix("Bearer ")
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
        entry = await app.state.store.aget(("trips", user), trip_id)
        if entry is None:
            raise HTTPException(404, "Trip not found")

    def view(values: dict) -> dict:
        return {
            k: values.get(k, default)
            for k, default in (
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
            )
        }

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
        return {"trip_id": trip_id, "revision": 0}

    @app.get("/trips/{trip_id}")
    async def read_trip(trip_id: str, user: str = Depends(owner)):
        await require_trip(user, trip_id)
        snapshot = await app.state.graph.aget_state(config_for(user, trip_id))
        return view(snapshot.values)

    @app.post("/trips/{trip_id}/messages")
    async def message(
        trip_id: str, request: MessageRequest, user: str = Depends(owner)
    ):
        await require_trip(user, trip_id)
        config = config_for(user, trip_id)
        async with locks.setdefault(user + ":" + trip_id, asyncio.Lock()):
            snapshot = await app.state.graph.aget_state(config)
            if request.revision != snapshot.values.get("revision", 0):
                raise HTTPException(409, "Stale revision")
            initial = {
                "messages": [HumanMessage(content=request.message)],
                "calls": 0,
                "attempts": [],
            }
            if not snapshot.values:
                profile = await app.state.store.aget(("profiles", user), "preferences")
                initial["constraints"] = (
                    {"interests": profile.value["interests"]} if profile else {}
                )
            try:
                async with asyncio.timeout(420):
                    result = await app.state.graph.ainvoke(initial, config)
            except TimeoutError:
                raise HTTPException(
                    504,
                    "Turn deadline exceeded; read current trip state before retrying",
                ) from None
            return view(result)

    @app.post("/trips/{trip_id}/select/{option_id}")
    async def select(
        trip_id: str, option_id: str, revision: int, user: str = Depends(owner)
    ):
        await require_trip(user, trip_id)
        config = config_for(user, trip_id)
        async with locks.setdefault(user + ":" + trip_id, asyncio.Lock()):
            snapshot = await app.state.graph.aget_state(config)
            if revision != snapshot.values.get("revision", 0) or option_id not in [
                o["id"] for o in snapshot.values.get("options", [])
            ]:
                raise HTTPException(409, "Unknown option or stale revision")
            await app.state.graph.aupdate_state(config, {"selected": option_id})
        return {"selected": option_id, "revision": revision}

    @app.post("/trips/{trip_id}/bookings")
    async def book(trip_id: str, request: BookingRequest, user: str = Depends(owner)):
        await require_trip(user, trip_id)
        config = config_for(user, trip_id)
        async with locks.setdefault(user + ":" + trip_id, asyncio.Lock()):
            snapshot = await app.state.graph.aget_state(config)
            state = snapshot.values
            bookings = dict(state.get("bookings", {}))
            previous = bookings.get(request.idempotency_key)
            if previous:
                if (previous["option_id"], previous["revision"]) != (
                    request.option_id,
                    request.revision,
                ):
                    raise HTTPException(409, "Idempotency key already used")
                return previous
            if not request.confirm:
                raise HTTPException(
                    400, "Explicit confirmation is required for simulation"
                )
            if (
                request.revision != state.get("revision", 0)
                or state.get("selected") != request.option_id
            ):
                raise HTTPException(409, "Select a current option first")
            option = next(
                (
                    TripOption.model_validate(o)
                    for o in state.get("options", [])
                    if o["id"] == request.option_id
                ),
                None,
            )
            trip = TripConstraints.model_validate(state.get("constraints", {}))
            if option is None or not option.transport or not option.stay:
                raise HTTPException(409, "Incomplete trip")
            if not all(
                usable(c, trip, datetime.now(timezone.utc))
                for c in (option.transport, option.stay)
            ):
                raise HTTPException(409, "Quotes expired; refresh search")
            booking = {
                "id": str(uuid4()),
                "option_id": request.option_id,
                "revision": request.revision,
                "simulated": True,
                "status": "simulated",
                "paid": False,
                "reserved": False,
                "message": "Имитация: реальные места не зарезервированы, оплата не выполнялась.",
            }
            bookings[request.idempotency_key] = booking
            await app.state.graph.aupdate_state(config, {"bookings": bookings})
            return booking

    @app.put("/profile")
    async def profile(interests: list[str], user: str = Depends(owner)):
        if len(interests) > 10 or any(len(i) > 100 for i in interests):
            raise HTTPException(422, "At most ten interests, each up to 100 characters")
        await app.state.store.aput(
            ("profiles", user), "preferences", {"interests": interests}
        )
        return {"interests": interests}

    return app


app = create_app()
