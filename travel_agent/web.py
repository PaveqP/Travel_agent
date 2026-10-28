import asyncio
import time
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage
from pydantic import BaseModel, ConfigDict, Field

from travel_agent.accounts import AccountInput, AccountProfile, LoginInput
from travel_agent.config import environment
from travel_agent.graph import present_stage
from travel_agent.support import GUIDES, support_letter


class BackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage: str = Field(pattern=r"^(scenarios|transport|stays|itinerary|review)$")
    revision: int = Field(ge=0)


class ProgressRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    completed: dict[str, bool] = Field(max_length=200)


class DeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: str = Field(pattern=r"^УДАЛИТЬ$")


class TelegramLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=32, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")


def checklist(state: dict) -> list[dict]:
    rows = [{"id": key, "title": title, "date": None} for key, title in (
        ("documents", "Проверить документы"), ("tickets", "Проверить реальные билеты"),
        ("hotel", "Связаться с отелем"), ("packing", "Собрать вещи"))]
    option = next((o for o in state.get("options", []) if o["id"] == state.get("selected")), {})
    days = state.get("receipt", {}).get("itinerary") if state.get("stage") == "booked" else option.get("days", [])
    for day in days or []:
        for index, activity in enumerate(day.get("candidates", [])):
            rows.append({"id": f"{day['date']}:{index}", "title": activity["name"], "date": day["date"]})
    return rows


def mount_portal(app: FastAPI, owner, require_trip, config_for, view, sync_trip, save_profile, locks: dict[str, asyncio.Lock]) -> None:
    attempts: dict[str, tuple[float, int]] = {}

    def check_origin(request: Request) -> None:
        origin = request.headers.get("origin")
        if request.headers.get("sec-fetch-site") == "cross-site" or origin and origin != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "Запрос с другого сайта запрещён")

    def login_limit(request: Request) -> None:
        check_origin(request)
        key = request.client.host if request.client else "local"
        now = time.monotonic()
        start, count = attempts.get(key, (now, 0))
        if now - start > 600:
            start, count = now, 0
        if count >= 20:
            raise HTTPException(429, "Слишком много попыток. Повторите через 10 минут.")
        if len(attempts) > 10000:
            for old in [k for k, v in attempts.items() if now - v[0] > 600]:
                attempts.pop(old, None)
        attempts[key] = (start, count + 1)

    async def account_owner(user: str = Depends(owner)) -> str:
        if not await app.state.accounts.account(user):
            raise HTTPException(401, "Войдите в личный кабинет")
        return user

    async def login_response(user: str, request: Request, response: Response) -> dict:
        token = await app.state.accounts.session(user)
        response.set_cookie("travel_session", token, max_age=30 * 86400, httponly=True, secure=request.url.scheme == "https", samesite="strict", path="/")
        return await app.state.accounts.account(user)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if not request.url.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/config")
    async def public_config():
        bot = getattr(app.state, "bot", None)
        return {"telegram_url": "https://t.me/ostrovok_helper_ryadom_bot", "telegram_configured": bool(bot and bot.ready)}

    @app.post("/api/auth/register")
    async def register(data: AccountInput, request: Request, response: Response):
        login_limit(request)
        try:
            user = await app.state.accounts.register(data)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        return await login_response(user, request, response)

    @app.post("/api/auth/login")
    async def login(data: LoginInput, request: Request, response: Response):
        login_limit(request)
        user = await app.state.accounts.login(data)
        if not user:
            raise HTTPException(401, "Неверный email или пароль")
        return await login_response(user, request, response)

    @app.post("/api/auth/logout", status_code=204)
    async def logout(request: Request, response: Response, user: str = Depends(account_owner)):
        await app.state.accounts.revoke(request.cookies.get("travel_session", "") or request.headers.get("authorization", "").removeprefix("Bearer "))
        response.delete_cookie("travel_session", path="/")

    @app.post("/api/auth/telegram")
    async def telegram_login(data: TelegramLogin, request: Request, response: Response):
        login_limit(request)
        user = await app.state.accounts.consume_web_login(data.token)
        if not user:
            raise HTTPException(401, "Ссылка устарела или уже использована. Получите новую командой /site в боте.")
        return await login_response(user, request, response)

    @app.get("/api/account")
    async def read_account(user: str = Depends(account_owner)):
        return await app.state.accounts.account(user)

    @app.put("/api/account")
    async def update_account(data: AccountProfile, user: str = Depends(account_owner)):
        await app.state.accounts.update(user, data)
        await save_profile(user, data.interests)
        return await app.state.accounts.account(user)

    @app.delete("/api/account", status_code=204)
    async def delete_account(data: DeleteRequest, response: Response, user: str = Depends(account_owner)):
        trips = await app.state.accounts.trips(user)
        for trip in trips:
            async with locks.setdefault(user + ":" + trip["trip_id"], asyncio.Lock()):
                if app.state.graph.checkpointer:
                    await app.state.graph.checkpointer.adelete_thread(user + ":" + trip["trip_id"])
                await app.state.store.adelete(("trips", user), trip["trip_id"])
        await app.state.store.adelete(("profiles", user), "preferences")
        await app.state.accounts.delete(user)
        response.delete_cookie("travel_session", path="/")

    @app.get("/trips")
    async def list_trips(user: str = Depends(account_owner)):
        return await app.state.accounts.trips(user)

    @app.post("/api/telegram/link")
    async def link_telegram(user: str = Depends(account_owner)):
        token = await app.state.accounts.link(user)
        return {"url": "https://t.me/ostrovok_helper_ryadom_bot?start=link_" + token, "expires_in": 600}

    @app.delete("/api/telegram/link", status_code=204)
    async def unlink_telegram(user: str = Depends(account_owner)):
        await app.state.accounts.unlink(user)

    @app.post("/trips/{trip_id}/back")
    async def back(trip_id: str, data: BackRequest, user: str = Depends(owner)):
        await require_trip(user, trip_id)
        config = config_for(user, trip_id)
        async with locks.setdefault(user + ":" + trip_id, asyncio.Lock()):
            await require_trip(user, trip_id)
            state = (await app.state.graph.aget_state(config)).values
            if state.get('autonomous'):
                raise HTTPException(409, 'Измените пожелания в чате: обновятся только зависимые компоненты поездки.')
            stages = ("scenarios", "transport", "stays", "itinerary", "review", "booked")
            if data.revision != state.get("revision", 0):
                raise HTTPException(409, "План изменился. Обновите поездку.")
            if stages.index(data.stage) >= stages.index(state.get("stage", "scenarios")):
                raise HTTPException(409, "Можно вернуться только к предыдущему этапу")
            update = {"stage": data.stage, "revision": state.get("revision", 0) + 1,
                      "selected": None, "choices": [], "options": [], "pending_check_in": None, "research": {}, "requested_choice": None}
            if data.stage in ("scenarios", "transport"):
                update.update(selected_transport=None, selected_stay=None)
            if data.stage == "scenarios":
                update["selected_scenario"] = None
            if data.stage == "stays":
                update["selected_stay"] = None
            update["results"] = {k: v for k, v in state.get("results", {}).items() if k not in (
                ("transport", "stays", "experience") if data.stage == "scenarios" else
                ("stays", "experience") if data.stage == "transport" else
                ("experience",) if data.stage == "stays" else ())}
            update.update(present_stage({**state, **update}))
            update["messages"] = [AIMessage(content="Вернулись к этапу: " + {"scenarios": "идея поездки", "transport": "билеты", "stays": "проживание", "itinerary": "программа", "review": "проверка заказа"}[data.stage] + ". Можно выбрать заново или обсудить изменения.")]
            await app.state.graph.aupdate_state(config, update)
            final = (await app.state.graph.aget_state(config)).values
            await sync_trip(user, trip_id, final)
            return view(final)

    @app.get("/api/support")
    async def guides():
        return [support_letter(g.id, {}) for g in GUIDES]

    @app.get("/trips/{trip_id}/support/{guide_id}")
    async def letter(trip_id: str, guide_id: str, user: str = Depends(owner)):
        await require_trip(user, trip_id)
        state = (await app.state.graph.aget_state(config_for(user, trip_id))).values
        account = await app.state.accounts.account(user)
        try:
            return support_letter(guide_id, state, account["name"] if account else "[ваше имя]")
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from None

    @app.get("/trips/{trip_id}/progress")
    async def read_progress(trip_id: str, user: str = Depends(account_owner)):
        await require_trip(user, trip_id)
        state = (await app.state.graph.aget_state(config_for(user, trip_id))).values
        saved = await app.state.accounts.one("SELECT progress FROM portal_trips WHERE owner=%s AND id=%s", (user, trip_id))
        import json

        return {"items": checklist(state), "completed": json.loads(saved[0])}

    @app.put("/trips/{trip_id}/progress")
    async def update_progress(trip_id: str, data: ProgressRequest, user: str = Depends(account_owner)):
        await require_trip(user, trip_id)
        state = (await app.state.graph.aget_state(config_for(user, trip_id))).values
        if set(data.completed) - {c["id"] for c in checklist(state)}:
            raise HTTPException(422, "Неизвестный пункт маршрута")
        await app.state.accounts.progress(user, trip_id, data.completed)
        return {"items": checklist(state), "completed": data.completed}

    @app.get("/trips/{trip_id}/itinerary.pdf")
    async def pdf(trip_id: str, user: str = Depends(owner)):
        from travel_agent.itinerary_pdf import itinerary_pdf

        await require_trip(user, trip_id)
        state = (await app.state.graph.aget_state(config_for(user, trip_id))).values
        if not state.get("options") and not state.get("receipt"):
            raise HTTPException(409, "Сначала составьте программу поездки")
        data = await asyncio.to_thread(itinerary_pdf, view(state), trip_id)
        return Response(data, media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="ostrovok-itinerary.pdf"'})

    static = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if static.is_dir():
        app.mount("/", StaticFiles(directory=static, html=True), name="web")


def create_web_app() -> FastAPI:
    from travel_agent.api import create_app

    env = environment()
    dsn = env.get("TRAVEL_DATABASE_URL")
    if env.get("TRAVEL_POSTGRES_HOST"):
        if not env.get("TRAVEL_POSTGRES_PASSWORD"):
            raise RuntimeError("Set TRAVEL_POSTGRES_PASSWORD for the container's PostgreSQL database")
        password = quote(env["TRAVEL_POSTGRES_PASSWORD"], safe="")
        dsn = f"postgresql://travel:{password}@{env['TRAVEL_POSTGRES_HOST']}:5432/travel"
    if not dsn or not dsn.startswith(("postgresql://", "postgres://")):
        raise RuntimeError("Set TRAVEL_DATABASE_URL to the project's PostgreSQL database before starting the web application")
    return create_app(portal_database_url=dsn)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_web_app(), host="127.0.0.1", port=8000, access_log=False)
