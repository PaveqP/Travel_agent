import json
from datetime import date, datetime, timezone
from decimal import Decimal

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage, SystemMessage
from openai import APIError
from pydantic import ValidationError

from travel_agent.schemas import UserResponse


def option_context(state: dict) -> list[dict]:
    return [
        {
            **{k: o[k] for k in ("id", "transport", "stay", "budget", "warnings")},
            "days": [
                {
                    "date": d["date"],
                    "places": [
                        {"name": c["name"], "area": c.get("area")}
                        for c in d["candidates"]
                    ],
                }
                for d in o.get("days", [])
            ],
        }
        for o in state.get("options", [])
    ]


def render_options(state: dict, response: UserResponse | None = None) -> str:
    comments = {o.option_id: o for o in response.options} if response else {}
    lines = [response.text if response else "Вот доступные варианты поездки:"]
    trip = state.get("constraints", {})
    start = (
        date.fromisoformat(trip["start"]).strftime("%d.%m.%Y")
        if trip.get("start")
        else "дата не указана"
    )
    end = (
        date.fromisoformat(trip["end"]).strftime("%d.%m.%Y")
        if trip.get("end")
        else "дата не указана"
    )
    lines.append(
        f"{trip.get('origin', '')} → {trip.get('destination', 'Сочи')}, {start} — {end}; взрослых: {trip.get('adults', '')}."
    )
    for index, option in enumerate(state.get("options", []), 1):
        stay, flight = option.get("stay"), option.get("transport")
        lines.append(
            f"\n{index}. {stay['name'] if stay else 'Проживание пока не найдено'}"
            + (f" — {stay.get('area') or 'район не определён'}" if stay else "")
        )
        if flight:
            arrival = datetime.fromisoformat(flight["arrival_at"]).strftime(
                "%d.%m в %H:%M"
            )
            departure = datetime.fromisoformat(flight["return_departure_at"]).strftime(
                "%d.%m в %H:%M"
            )
            lines.append(
                f"Перелёт: {flight['name']}; прилёт {arrival}, обратный вылет {departure} (местное время)."
            )
        amount = (
            f"{Decimal(option['budget']['known_subtotal']):,.2f}".rstrip("0")
            .rstrip(".")
            .replace(",", " ")
            .replace(".", ",")
        )
        lines.append(
            f"Билеты и проживание: известная сумма {amount} ₽ на всю группу и весь период."
        )
        if not flight or not stay:
            lines.append("Сумма неполная: транспорт или проживание ещё не найдены.")
        if option["id"] in comments:
            comment = comments[option["id"]]
            lines.append(f"Подойдёт: {comment.benefit}\nКомпромисс: {comment.tradeoff}")
        if any("превышает бюджет" in w for w in option["warnings"]):
            lines.append("Известная сумма уже превышает ваш бюджет.")
    if len(state.get("options", [])) < 5:
        lines.append(
            "\nПоказываю столько различных вариантов, сколько удалось проверить; до пяти."
        )
    lines.append(
        "Питание, местные переезды, активности и дополнительные сборы не включены. Полная стоимость неизвестна; наличие и бронирование не подтверждены."
    )
    lines.append(
        "Какой вариант обсудим? Можно спросить об отеле или районе, изменить пожелания или выбрать номер варианта."
    )
    return "\n".join(lines)


def llm_presenter(model, prompt: str):
    structured = model.with_structured_output(UserResponse, method="function_calling")

    async def present(state: dict) -> str:
        planning = state.get("decision", {}).get("action") == "compose"
        research = state.get("research", {})
        sources = research.get("sources", [])
        context = {
            "phase": "present_options" if planning else "answer_question",
            "now": datetime.now(timezone.utc).isoformat(),
            "constraints": state.get("constraints", {}),
            "results": {
                role: {"status": row["status"], "warnings": row.get("warnings", [])}
                for role, row in state.get("results", {}).items()
            },
            "options": option_context(state),
            "selected": state.get("selected"),
            "research": research,
        }
        fallback = (
            render_options(state)
            if planning and state.get("options")
            else state.get("answer", "")
        )
        if (
            not planning
            and state.get("decision", {}).get("action") == "research"
            and not sources
        ):
            return "Сейчас не удалось получить веб-источники по этому вопросу. Не могу подтвердить детали отеля или района. Сохранённые варианты поездки остаются доступны; можно обсудить их цены или изменить пожелания."
        try:
            result = UserResponse.model_validate(
                await structured.ainvoke(
                    [
                        SystemMessage(content=prompt),
                        *state.get("messages", [])[-8:],
                        HumanMessage(content=json.dumps(context, ensure_ascii=False)),
                    ]
                )
            )
            allowed = {o["id"] for o in state.get("options", [])}
            if any(o.option_id not in allowed for o in result.options):
                return fallback
            if planning and {o.option_id for o in result.options} != allowed:
                return fallback
            urls = {s["url"] for s in sources}
            if any(url not in urls for url in result.source_urls):
                return fallback
            if sources and not result.source_urls:
                return fallback
            answer = (
                render_options(state, result) if planning and allowed else result.text
            )
            if result.source_urls:
                answer += "\n\nИсточники:\n" + "\n".join(result.source_urls)
            return answer
        except (APIError, TimeoutError, ValidationError, OutputParserException):
            return fallback

    return present
