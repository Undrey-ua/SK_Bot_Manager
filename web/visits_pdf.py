"""PDF-звіт візитів (усі поля крім фото)."""

from __future__ import annotations

from datetime import datetime

from fpdf.enums import XPos, YPos
from fpdf.fonts import FontFace

from database.models import Visit
from web.client_geo import client_city
from web.pdf_report import ReportPDF, draw_empty_message, draw_title_block
from web.stands_pdf import COLOR_HEADER_BG, COLOR_HEADER_TEXT, COLOR_ROW_ALT, KYIV
from web.utils import format_dt, task_label, visit_type_label


def _tasks_text(visit: Visit) -> str:
    labels = [task_label(t.task) for t in visit.tasks]
    return ", ".join(labels) if labels else "—"


def _visit_row(visit: Visit, *, show_manager: bool) -> list[str]:
    client = visit.client
    cells = [
        format_dt(visit.created_at),
    ]
    if show_manager:
        cells.append(visit.manager.name if visit.manager else "—")
    cells.extend(
        [
            client.name if client else "—",
            client.region.name if client and client.region else "—",
            client_city(client) if client else "—",
            (client.address or "—") if client else "—",
            visit_type_label(visit.visit_type),
            _tasks_text(visit),
            visit.comment or "—",
        ]
    )
    return cells


def build_visits_pdf(
    *,
    title: str,
    visits: list[Visit],
    show_manager: bool = True,
    generated_at: datetime | None = None,
) -> bytes:
    when = generated_at or datetime.now(KYIV)
    pdf = ReportPDF(doc_title=title, strip_label="Звіт по візитах")
    pdf.add_page()
    draw_title_block(
        pdf,
        title=title,
        generated_at=when,
        summaries=[("Візитів", str(len(visits)))],
    )

    if not visits:
        draw_empty_message(pdf, "Візитів за обраний період немає.")
        return bytes(pdf.output())

    headings_style = FontFace(
        family="Unicode",
        emphasis="BOLD",
        size_pt=7.5,
        color=COLOR_HEADER_TEXT,
        fill_color=COLOR_HEADER_BG,
    )
    body_style = FontFace(family="Unicode", size_pt=7)
    alt_style = FontFace(family="Unicode", size_pt=7, fill_color=COLOR_ROW_ALT)

    headers = ["Дата"]
    if show_manager:
        headers.append("Менеджер")
    headers.extend(
        ["Клієнт", "Область", "Місто", "Адреса", "Тип", "Задачі", "Коментар"]
    )

    if show_manager:
        col_widths = [28, 28, 32, 28, 22, 36, 16, 32, pdf.epw - 222]
        align = (
            "LEFT",
            "LEFT",
            "LEFT",
            "LEFT",
            "LEFT",
            "LEFT",
            "CENTER",
            "LEFT",
            "LEFT",
        )
    else:
        col_widths = [30, 36, 30, 24, 40, 18, 36, pdf.epw - 214]
        align = (
            "LEFT",
            "LEFT",
            "LEFT",
            "LEFT",
            "LEFT",
            "CENTER",
            "LEFT",
            "LEFT",
        )

    with pdf.table(
        width=pdf.epw,
        col_widths=col_widths,
        headings_style=headings_style,
        line_height=4.6,
        text_align=align,
    ) as table:
        header_row = table.row()
        for h in headers:
            header_row.cell(h)

        for idx, visit in enumerate(visits, 1):
            style = alt_style if idx % 2 == 0 else body_style
            data_row = table.row()
            for text in _visit_row(visit, show_manager=show_manager):
                data_row.cell(text, style=style)

    return bytes(pdf.output())


def build_visit_detail_pdf(
    *,
    visit: Visit,
    show_manager: bool = True,
    generated_at: datetime | None = None,
) -> bytes:
    when = generated_at or datetime.now(KYIV)
    client = visit.client
    title = f"Візит від {format_dt(visit.created_at)}"
    pdf = ReportPDF(doc_title=title, strip_label="Звіт по візиту")
    pdf.add_page()
    draw_title_block(
        pdf,
        title=title,
        generated_at=when,
        summaries=[
            ("Тип", visit_type_label(visit.visit_type)),
            ("Клієнт", (client.name if client else "—")[:40]),
        ],
    )

    rows: list[tuple[str, str]] = [
        ("Дата", format_dt(visit.created_at)),
    ]
    if show_manager:
        rows.append(("Менеджер", visit.manager.name if visit.manager else "—"))
    rows.extend(
        [
            ("Клієнт", client.name if client else "—"),
            ("Область", client.region.name if client and client.region else "—"),
            ("Місто", client_city(client) if client else "—"),
            ("Адреса", (client.address or "—") if client else "—"),
            ("Тип візиту", visit_type_label(visit.visit_type)),
            ("Задачі", _tasks_text(visit)),
            ("Коментар", visit.comment or "—"),
        ]
    )

    label_w = 36
    value_w = pdf.epw - label_w
    for label, value in rows:
        y = pdf.get_y()
        pdf.set_fill_color(241, 245, 249)
        pdf.set_font("Unicode", "", 8)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(label_w, 7, label, fill=True)
        pdf.set_xy(10 + label_w, y)
        pdf.set_font("Unicode", "", 9)
        pdf.set_text_color(15, 23, 42)
        pdf.multi_cell(value_w, 7, value, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(1)

    return bytes(pdf.output())
