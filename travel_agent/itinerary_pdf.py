from datetime import datetime
from decimal import Decimal
from html import escape
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ASSETS = Path(__file__).parent / "assets"
for font, filename in (("Noto", "NotoSans-Regular.ttf"), ("NotoBold", "NotoSans-Bold.ttf")):
    pdfmetrics.registerFont(TTFont(font, str(ASSETS / filename)))
BLUE = colors.HexColor("#0646DE")
INK = colors.HexColor("#162544")
MUTED = colors.HexColor("#64718A")
PALE = colors.HexColor("#F0F5FF")


def itinerary_pdf(state: dict, trip_id: str) -> bytes:
    output = BytesIO()
    c = state.get("constraints", {})
    option = next((o for o in state.get("options", []) if o["id"] == state.get("selected")), None)
    option = option or next(iter(state.get("options", [])), {})
    receipt = state.get("receipt", {}) if state.get("stage") == "booked" else {}
    days = receipt.get("itinerary", option.get("days", []))
    regular = ParagraphStyle("body", fontName="Noto", fontSize=9, leading=15, textColor=INK, spaceAfter=8, alignment=TA_LEFT)
    small = ParagraphStyle("small", parent=regular, fontSize=8, leading=12, textColor=MUTED)
    title = ParagraphStyle("title", parent=regular, fontName="NotoBold", fontSize=30, leading=38, spaceAfter=14)
    heading = ParagraphStyle("heading", parent=regular, fontName="NotoBold", fontSize=15, leading=21, spaceBefore=18, spaceAfter=10, keepWithNext=True)
    label = ParagraphStyle("label", parent=small, fontName="NotoBold", textColor=BLUE)

    def p(value: object, style: ParagraphStyle = regular) -> Paragraph:
        return Paragraph(escape(str(value)).replace("\n", "<br/>"), style)

    def amount(value: object) -> str:
        return f"{Decimal(str(value)):,.2f}".replace(",", " ") + " RUB"

    def page(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFillColor(BLUE)
        canvas.roundRect(18 * mm, 276 * mm, 10 * mm, 10 * mm, 3 * mm, fill=1, stroke=0)
        canvas.setFont("NotoBold", 17)
        canvas.setFillColor(colors.white)
        canvas.drawString(20 * mm, 278.5 * mm, "О!")
        canvas.setFont("NotoBold", 11)
        canvas.setFillColor(INK)
        canvas.drawString(32 * mm, 279.5 * mm, "рядом / ваш маршрут")
        canvas.setStrokeColor(colors.HexColor("#DEE7F8"))
        canvas.line(18 * mm, 20 * mm, 192 * mm, 20 * mm)
        canvas.setFont("Noto", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 14 * mm, "Личный план. Заказ и оплата - имитация. Проверяйте услуги у поставщиков.")
        canvas.drawRightString(192 * mm, 14 * mm, str(doc.page))
        canvas.restoreState()

    document = SimpleDocTemplate(output, pagesize=(210 * mm, 297 * mm), rightMargin=18 * mm, leftMargin=18 * mm,
                                 topMargin=34 * mm, bottomMargin=27 * mm, title="О! рядом - маршрут поездки", author="О! рядом")
    story = [Spacer(1, 5 * mm), p("ВАШЕ МАЛЕНЬКОЕ ПРИКЛЮЧЕНИЕ", label), p(c.get("destination", "Большой Сочи"), title)]
    dates = f"{c.get('start') or 'Даты уточняются'} - {c.get('end') or 'дата уточняется'}"
    story.append(p(f"{dates}   /   Взрослых: {c.get('adults') or 'уточняется'}   /   Из: {c.get('origin') or 'уточняется'}"))
    story.append(p(f"Поездка {trip_id} · Версия плана {state.get('revision', 0)}", small))
    story.append(p(c.get("purpose") or "План поездки по вашим пожеланиям"))
    notice = "Имитационный заказ сохранён. Реальные билеты и проживание не оплачены и не зарезервированы." if receipt else "Черновик маршрута. Цены и наличие могут измениться; услуги не забронированы."
    box = Table([[p(notice)]], colWidths=[174 * mm])
    box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PALE), ("LEFTPADDING", (0, 0), (-1, -1), 14), ("RIGHTPADDING", (0, 0), (-1, -1), 14), ("TOPPADDING", (0, 0), (-1, -1), 12), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story.append(box)
    story.append(p("Билеты и проживание", heading))
    components = receipt.get("items") or [{"kind": kind, **item, "details": item} for kind, item in (("transport", option.get("transport")), ("stays", option.get("stay"))) if item]
    for item in components:
        details = item.get("details", {})
        kind = "ТРАНСПОРТ" if item.get("kind") == "transport" else "ПРОЖИВАНИЕ"
        block = [p(kind, label), p(item.get("name", "Уточняется"))]
        if item.get("price"):
            price = item["price"]
            basis = {"party": "за группу", "person": "за человека", "ticket": "за билет", "room_stay": "за проживание", "unknown": "основа не подтверждена"}.get(price.get("basis"), "основа не подтверждена")
            block.append(p(f"{amount(price['amount'])} · {basis}", small))
        block.append(p(f"{details.get('start') or c.get('start') or '?'} - {details.get('end') or c.get('end') or '?'}", small))
        if details.get("arrival_at"):
            block.append(p("Прилёт: " + details["arrival_at"], small))
        if details.get("return_departure_at"):
            block.append(p("Обратный вылет: " + details["return_departure_at"], small))
        if details.get("description"):
            block.append(p(details["description"], small))
        source = item.get("source", {})
        if source:
            block.append(p(f"Источник: {source.get('provider', '?')} · Получено: {source.get('retrieved_at', '?')} · {source.get('evidence', '?')}", small))
        story.append(KeepTogether(block))
    total = receipt.get("payment", {}).get("amount", option.get("budget", {}).get("known_subtotal"))
    if total is not None:
        story.extend([p("Известная сумма за группу", heading), p(amount(total))])
        story.append(p("Питание, местные переезды, активности и дополнительные сборы не включены. Неизвестные расходы не считаются нулевыми.", small))
    for index, day in enumerate(days):
        block = [p(f"День {index + 1} / {day['date']}", label), p(" · ".join(a["name"] for a in day.get("candidates", [])) or "Свободное время и переезды. Распорядок согласуйте с фактическими билетами.")]
        if index == 0:
            block.insert(0, p("День за днём", heading))
        for activity in day.get("candidates", []):
            if activity.get("description"):
                block.append(p(activity["description"], small))
            source = activity.get("source", {})
            if source.get("provider"):
                block.append(p("Источник: " + source["provider"] + " · " + source.get("source_url", ""), small))
        for warning in day.get("warnings", []):
            block.append(p(warning, small))
        story.append(KeepTogether(block))
    story.append(p("Рядом в поездке", heading))
    story.append(p("При изменении рейса проверьте информацию у перевозчика и предупредите отель. Сохраните подтверждения, уведомления и чеки. В чате доступны справочник и черновики писем в отель или авиакомпанию."))
    story.append(p("Telegram: t.me/ostrovok_helper_ryadom_bot", label))
    story.append(p("Сформировано " + datetime.now(ZoneInfo("Europe/Moscow")).strftime("%d.%m.%Y %H:%M МСК"), small))
    document.build(story, onFirstPage=page, onLaterPages=page)
    return output.getvalue()
