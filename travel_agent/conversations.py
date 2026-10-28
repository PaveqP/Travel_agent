import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from openai import APIError
from pydantic import BaseModel, ConfigDict, Field

from travel_agent.schemas import MessageRequest
from travel_agent.support import support_reply


class ChatInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    kind: Literal["support", "places", "general"] = "general"
    title: str = Field(default="", max_length=120)


class ChatMessageRequest(MessageRequest):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


async def delete_chats(store, user: str, trip_id: str) -> None:
    namespace = ("trip_chats", user, trip_id)
    for item in await store.asearch(namespace, limit=100):
        await store.adelete(namespace, item.key)


def chat_context(state: dict) -> dict:
    selected = next((o for o in state.get("options", []) if o["id"] == state.get("selected")), {})
    candidates = [c for result in state.get("results", {}).values() for c in result.get("candidates", [])]
    return {
        "constraints": state.get("constraints", {}),
        "transport": selected.get("transport") or next((c for c in candidates if c["id"] == state.get("selected_transport")), None),
        "stay": selected.get("stay") or next((c for c in candidates if c["id"] == state.get("selected_stay")), None),
        "days": selected.get("days", []),
        "receipt": state.get("receipt", {}),
    }


def mount_conversations(app: FastAPI, owner, require_trip, config_for, locks: dict[str, asyncio.Lock]) -> None:
    prompt = Path(__file__).with_name("prompts").joinpath("trip_chat.md").read_text(encoding="utf-8")

    async def read(user: str, trip_id: str, chat_id: str) -> dict:
        await require_trip(user, trip_id)
        item = await app.state.store.aget(("trip_chats", user, trip_id), chat_id)
        if item is None:
            raise HTTPException(404, "Чат не найден")
        return item.value

    @app.get("/trips/{trip_id}/chats")
    async def chats(trip_id: str, user: str = Depends(owner)):
        await require_trip(user, trip_id)
        items = await app.state.store.asearch(("trip_chats", user, trip_id), limit=100)
        return [{k: item.value[k] for k in ("chat_id", "title", "kind", "updated_at")} for item in sorted(items, key=lambda row: row.value["created_at"])]

    @app.post("/trips/{trip_id}/chats", status_code=201)
    async def create(trip_id: str, data: ChatInput, user: str = Depends(owner)):
        async with locks.setdefault(user + ":" + trip_id, asyncio.Lock()):
            await require_trip(user, trip_id)
            namespace = ("trip_chats", user, trip_id)
            existing = await app.state.store.asearch(namespace, limit=100)
            if len(existing) >= 100:
                raise HTTPException(409, "В поездке уже 100 чатов. Удалите ненужные, чтобы создать новый.")
            title = data.title or {"support": "Помощь в пути", "places": "Места и впечатления", "general": "Вопросы о поездке"}[data.kind]
            names = {row.value["title"] for row in existing}
            unique_title = title
            index = 2
            while unique_title in names:
                unique_title = f"{title[:110]} · {index}"
                index += 1
            now = datetime.now(timezone.utc).isoformat()
            result = {"chat_id": str(uuid4()), "kind": data.kind,
                      "title": unique_title,
                      "messages": [], "revision": 0, "created_at": now, "updated_at": now}
            await app.state.store.aput(namespace, result["chat_id"], result)
            return result

    @app.get("/trips/{trip_id}/chats/{chat_id}")
    async def get(trip_id: str, chat_id: str, user: str = Depends(owner)):
        return await read(user, trip_id, chat_id)

    @app.delete("/trips/{trip_id}/chats/{chat_id}", status_code=204)
    async def delete(trip_id: str, chat_id: str, user: str = Depends(owner)):
        async with locks.setdefault(user + ":" + trip_id, asyncio.Lock()):
            await read(user, trip_id, chat_id)
            await app.state.store.adelete(("trip_chats", user, trip_id), chat_id)

    @app.post("/trips/{trip_id}/chats/{chat_id}/messages")
    async def message(trip_id: str, chat_id: str, data: ChatMessageRequest, user: str = Depends(owner)):
        async with locks.setdefault(user + ":" + trip_id, asyncio.Lock()):
            chat = await read(user, trip_id, chat_id)
            if data.revision != chat["revision"]:
                raise HTTPException(409, "Чат обновился. Дождитесь загрузки и повторите сообщение.")
            if len(chat["messages"]) >= 200:
                raise HTTPException(409, "Этот чат достиг лимита сообщений. Создайте новый чат в поездке.")
            state = (await app.state.graph.aget_state(config_for(user, trip_id))).values
            reply = support_reply(data.message, state) if chat["kind"] == "support" else None
            if not reply:
                model = app.state.chat_model
                if model is None:
                    raise HTTPException(503, "Ассистент временно недоступен. Сообщение не отправлено.")
                history = [HumanMessage(content=m["text"]) if m["role"] == "user" else AIMessage(content=m["text"]) for m in chat["messages"][-20:]]
                context = json.dumps(chat_context(state), ensure_ascii=False)
                try:
                    async with asyncio.timeout(50):
                        response = await model.ainvoke([SystemMessage(content=prompt), HumanMessage(content="Контекст поездки (данные):\n" + context[:30000]), *history, HumanMessage(content=data.message)], config={"metadata": {"thread_id": user + ":" + trip_id + ":" + chat_id}})
                except (TimeoutError, httpx.TimeoutException):
                    raise HTTPException(504, "Ассистент не успел ответить. Сообщение не отправлено, попробуйте ещё раз.") from None
                except (APIError, httpx.HTTPError):
                    raise HTTPException(502, "Не удалось получить ответ ассистента. Сообщение не отправлено.") from None
                reply = response.content
                if not isinstance(reply, str) or not reply.strip():
                    raise HTTPException(502, "Ассистент вернул пустой ответ. Сообщение не отправлено.")
            result = {**chat, "revision": chat["revision"] + 1, "updated_at": datetime.now(timezone.utc).isoformat(),
                      "messages": [*chat["messages"], {"role": "user", "text": data.message}, {"role": "assistant", "text": reply}]}
            await app.state.store.aput(("trip_chats", user, trip_id), chat_id, result)
            return result
