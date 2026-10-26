import argparse
import asyncio
import hashlib
import json
import os
import sys
from contextlib import AsyncExitStack, contextmanager
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import httpx


@contextmanager
def terminal_input() -> Iterator[None]:
    if sys.platform != "linux" or not sys.stdin.isatty():
        yield
        return
    import termios

    descriptor = sys.stdin.fileno()
    attributes = termios.tcgetattr(descriptor)
    original = attributes[0]
    # Linux canonical erase must remove a whole UTF-8 character, not one byte.
    utf8_flag = getattr(termios, "IUTF8", 0x4000)
    attributes[0] |= utf8_flag
    termios.tcsetattr(descriptor, termios.TCSANOW, attributes)
    try:
        yield
    finally:
        attributes = termios.tcgetattr(descriptor)
        attributes[0] = (attributes[0] & ~utf8_flag) | (original & utf8_flag)
        termios.tcsetattr(descriptor, termios.TCSANOW, attributes)


async def dialogue(client: httpx.AsyncClient, trip_id: str) -> None:
    print("Опишите поездку своими словами. Можно задавать вопросы и менять пожелания.")
    print(
        "Команды: /show — варианты; /select НОМЕР — выбрать; /book confirm — имитация бронирования; /quit — выйти."
    )
    while True:
        try:
            text = (await asyncio.to_thread(input, "\nВы: ")).strip()
            text.encode("utf-8")
        except EOFError:
            break
        except (UnicodeDecodeError, UnicodeEncodeError):
            print(
                "Не удалось прочитать строку: повреждена кодировка. Введите сообщение ещё раз — оно не было отправлено."
            )
            continue
        if text == "/quit":
            break
        if not text:
            continue
        try:
            current = await client.get("/trips/" + trip_id)
            current.raise_for_status()
            state = current.json()
            revision = state["revision"]
            if text == "/show":
                print(
                    "\nАгент:",
                    state.get("plan_answer")
                    or state["answer"]
                    or "Пока нет вариантов. Расскажите о поездке.",
                )
                continue
            if text.startswith("/select "):
                value = text.split(maxsplit=1)[1]
                options = state["options"]
                if not value.isdigit() or not 1 <= int(value) <= len(options):
                    print("Укажите номер из последнего списка вариантов.")
                    continue
                selected = options[int(value) - 1]["id"]
                response = await client.post(
                    f"/trips/{trip_id}/select/{selected}", params={"revision": revision}
                )
                response.raise_for_status()
                print(
                    "Агент: Вариант выбран. Можно обсудить детали или выполнить /book confirm для имитации бронирования."
                )
            elif text.startswith("/book"):
                if text != "/book confirm":
                    print(
                        "Для явного подтверждения имитации введите /book confirm. Реальной оплаты не будет."
                    )
                    continue
                if not state["selected"]:
                    print("Сначала выберите вариант командой /select НОМЕР.")
                    continue
                response = await client.post(
                    f"/trips/{trip_id}/bookings",
                    json={
                        "option_id": state["selected"],
                        "revision": revision,
                        "confirm": True,
                        "idempotency_key": f"console-{revision}-{state['selected']}",
                    },
                )
                response.raise_for_status()
                print("Агент:", response.json()["message"])
            else:
                print("Агент: Думаю…")
                response = await client.post(
                    f"/trips/{trip_id}/messages",
                    json={"message": text, "revision": revision},
                )
                response.raise_for_status()
                print("\nАгент:", response.json()["answer"])
        except httpx.HTTPStatusError as exc:
            messages = {
                401: "Не удалось авторизоваться.",
                409: "Вариант устарел или не выбран. Посмотрите /show; при необходимости попросите обновить предложения.",
                504: "Поиск занял слишком долго. Посмотрите /show: часть результатов могла сохраниться.",
            }
            print(
                "Агент:",
                messages.get(
                    exc.response.status_code,
                    "Не удалось обработать запрос. Повторите сообщение.",
                ),
            )
        except httpx.RequestError:
            print("Агент: Не удалось связаться с сервисом. Попробуйте ещё раз.")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Диалог с Travel Agent")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--trip")
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--new", action="store_true")
    args = parser.parse_args()
    async with AsyncExitStack() as stack:
        transport = None
        saved = None
        trip_id = args.trip
        if args.local:
            from travel_agent.api import create_app
            from travel_agent.config import environment

            token = environment().get("TRAVEL_API_TOKEN") or "local-console-only"
            os.environ["TRAVEL_API_TOKEN"] = token
            token = token.split(",")[0]
            directory = Path(".travel-agent")
            directory.mkdir(mode=0o700, exist_ok=True)
            app = create_app(local_database=str(directory / "checkpoints.sqlite"))
            await stack.enter_async_context(app.router.lifespan_context(app))
            transport = httpx.ASGITransport(app=app)
            user = hashlib.sha256(token.encode()).hexdigest()
            saved = directory / (user + ".json")
            if not trip_id and not args.new and saved.exists():
                trip_id = json.loads(saved.read_text())["trip_id"]
            trip_id = trip_id or str(uuid4())
            await app.state.store.aput(("trips", user), trip_id, {})
            saved.write_text(json.dumps({"trip_id": trip_id}))
            print(
                "Диалог сохраняется локально. Следующий запуск продолжит эту поездку; --new начнёт новую."
            )
        else:
            token = os.environ.get("TRAVEL_API_TOKEN", "")
        client = await stack.enter_async_context(
            httpx.AsyncClient(
                base_url=args.url,
                transport=transport,
                headers={"Authorization": "Bearer " + token},
                timeout=450,
            )
        )
        if not trip_id:
            response = await client.post("/trips")
            response.raise_for_status()
            trip_id = response.json()["trip_id"]
        with terminal_input():
            await dialogue(client, trip_id)


if __name__ == "__main__":
    asyncio.run(main())
