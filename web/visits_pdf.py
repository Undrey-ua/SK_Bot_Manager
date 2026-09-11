"""PDF-звіт візитів (список без фото; картка візиту — з фото)."""

from __future__ import annotations

import logging
from datetime import datetime
from io import BytesIO

import httpx
from fpdf.errors import FPDFException
from fpdf.enums import XPos, YPos
from fpdf.fonts import FontFace

from database.models import Reserve, Task, Visit
from web.client_geo import client_city
from web.pdf_report import ReportPDF, draw_empty_message, draw_title_block
from web.stands_pdf import COLOR_HEADER_BG, COLOR_HEADER_TEXT, COLOR_MUTED, COLOR_ROW_ALT, KYIV
from web.utils import format_qty, format_visit_date, task_label, visit_type_label

logger = logging.getLogger(__name__)


def _tasks_text(visit: Visit) -> str:
    labels = [task_label(t.task) for t in visit.tasks]
    return ", ".join(labels) if labels else "—"


def _visit_row(visit: Visit, *, show_manager: bool) -> list[str]:
    client = visit.client
    cells = [
        format_visit_date(visit.created_at),
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


def _table_styles() -> tuple[FontFace, FontFace, FontFace]:
    headings_style = FontFace(
        family="Unicode",
        emphasis="BOLD",
        size_pt=7.5,
        color=COLOR_HEADER_TEXT,
        fill_color=COLOR_HEADER_BG,
    )
    body_style = FontFace(family="Unicode", size_pt=7)
    alt_style = FontFace(family="Unicode", size_pt=7, fill_color=COLOR_ROW_ALT)
    return headings_style, body_style, alt_style


_SECTION_KEEP_MM = 32


def _draw_section_heading(pdf: ReportPDF, title: str) -> None:
    if pdf.will_page_break(_SECTION_KEEP_MM):
        pdf.add_page()
    else:
        pdf.ln(6)
    pdf.set_font("Unicode", "B", 11)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 7, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)


def _draw_rows_table(
    pdf: ReportPDF,
    *,
    headers: list[str],
    rows: list[list[str]],
    col_widths: list[float],
    align: tuple[str, ...],
    empty_text: str,
) -> None:
    if not rows:
        draw_empty_message(pdf, empty_text)
        return

    headings_style, body_style, alt_style = _table_styles()
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
        for idx, cells in enumerate(rows, 1):
            style = alt_style if idx % 2 == 0 else body_style
            data_row = table.row()
            for text in cells:
                data_row.cell(text, style=style)


def _reserve_status(reserve: Reserve, *, now: datetime) -> str:
    if reserve.sold_at:
        return "Продаж"
    if reserve.cancelled_at:
        return "Скасовано"
    if reserve.expires_at is not None and reserve.expires_at <= now:
        return "Прострочений"
    return "Активний"


def _task_pdf_row(task: Task, *, show_manager: bool) -> list[str]:
    cells = [format_visit_date(task.completed_at)]
    if show_manager:
        cells.append(task.assignee.name if task.assignee else "—")
    cells.extend(
        [
            task.client.name if task.client else "—",
            task.title or "—",
            task.comment or "—",
        ]
    )
    return cells


def _reserve_pdf_row(reserve: Reserve, *, show_manager: bool, now: datetime) -> list[str]:
    cells = [format_visit_date(reserve.created_at)]
    if show_manager:
        cells.append(reserve.manager.name if reserve.manager else "—")
    cells.extend(
        [
            reserve.region.name if reserve.region else "—",
            reserve.client.name if reserve.client else "—",
            reserve.material or "—",
            format_qty(reserve.quantity, decimals=2),
            _reserve_status(reserve, now=now),
        ]
    )
    return cells


def build_visits_pdf(
    *,
    title: str,
    visits: list[Visit],
    show_manager: bool = True,
    generated_at: datetime | None = None,
    completed_tasks: list[Task] | None = None,
    week_reserves: list[Reserve] | None = None,
    include_week_extras: bool = False,
) -> bytes:
    when = generated_at or datetime.now(KYIV)
    tasks = completed_tasks or []
    reserves = week_reserves or []
    pdf = ReportPDF(doc_title=title, strip_label="Звіт по візитах")
    pdf.add_page()
    summaries = [("Візитів", str(len(visits)))]
    if include_week_extras:
        summaries.extend(
            [
                ("Виконано задач", str(len(tasks))),
                ("Резервів", str(len(reserves))),
            ]
        )
    draw_title_block(
        pdf,
        title=title,
        generated_at=when,
        summaries=summaries,
    )

    headers = ["Дата"]
    if show_manager:
        headers.append("Менеджер")
    headers.extend(
        ["Клієнт", "Область", "Місто", "Адреса", "Тип", "Задачі", "Коментар"]
    )
    if show_manager:
        col_widths = [22, 30, 34, 28, 22, 36, 16, 32, pdf.epw - 220]
        align = ("LEFT", "LEFT", "LEFT", "LEFT", "LEFT", "LEFT", "CENTER", "LEFT", "LEFT")
    else:
        col_widths = [24, 38, 30, 24, 42, 18, 36, pdf.epw - 212]
        align = ("LEFT", "LEFT", "LEFT", "LEFT", "LEFT", "CENTER", "LEFT", "LEFT")

    _draw_rows_table(
        pdf,
        headers=headers,
        rows=[_visit_row(v, show_manager=show_manager) for v in visits],
        col_widths=col_widths,
        align=align,
        empty_text="Візитів за обраний період немає.",
    )

    if include_week_extras:
        if tasks:
            _draw_section_heading(pdf, "Виконані задачі за тиждень")
            task_headers = ["Дата"]
            if show_manager:
                task_headers.append("Менеджер")
            task_headers.extend(["Клієнт", "Завдання", "Нотатки"])
            if show_manager:
                task_widths = [24, 36, 48, 70, pdf.epw - 178]
                task_align = ("LEFT", "LEFT", "LEFT", "LEFT", "LEFT")
            else:
                task_widths = [28, 52, 80, pdf.epw - 160]
                task_align = ("LEFT", "LEFT", "LEFT", "LEFT")
            _draw_rows_table(
                pdf,
                headers=task_headers,
                rows=[_task_pdf_row(t, show_manager=show_manager) for t in tasks],
                col_widths=task_widths,
                align=task_align,
                empty_text="Виконаних задач за цей тиждень немає.",
            )

        if reserves:
            _draw_section_heading(pdf, "Резерви, створені за тиждень")
            reserve_headers = ["Дата"]
            if show_manager:
                reserve_headers.append("Менеджер")
            reserve_headers.extend(["Область", "Клієнт", "Матеріал", "Кв. м", "Статус"])
            if show_manager:
                reserve_widths = [22, 32, 32, 42, 70, 22, pdf.epw - 220]
                reserve_align = ("LEFT", "LEFT", "LEFT", "LEFT", "LEFT", "RIGHT", "CENTER")
            else:
                reserve_widths = [24, 36, 48, 78, 24, pdf.epw - 210]
                reserve_align = ("LEFT", "LEFT", "LEFT", "LEFT", "RIGHT", "CENTER")
            _draw_rows_table(
                pdf,
                headers=reserve_headers,
                rows=[_reserve_pdf_row(r, show_manager=show_manager, now=when) for r in reserves],
                col_widths=reserve_widths,
                align=reserve_align,
                empty_text="Резервів, створених за цей тиждень, немає.",
            )

    return bytes(pdf.output())


async def load_visit_photo_bytes(visit: Visit) -> list[bytes]:
    urls = [photo.photo_url for photo in visit.photos if photo.photo_url]
    if not urls:
        return []
    images: list[bytes] = []
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        for url in urls:
            try:
                response = await client.get(url)
                response.raise_for_status()
                if response.content:
                    images.append(response.content)
            except httpx.HTTPError:
                logger.warning("Не вдалося завантажити фото візиту: %s", url)
    return images


def _embed_photos(pdf: ReportPDF, images: list[bytes]) -> None:
    if not images:
        return

    pdf.ln(4)
    pdf.set_font("Unicode", "B", 11)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 7, f"Фото ({len(images)})", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    cols = 2
    gap = 5
    cell_w = (pdf.epw - gap * (cols - 1)) / cols
    max_h = 72
    x0 = pdf.l_margin
    col = 0
    y = pdf.get_y()
    row_h = 0

    for data in images:
        if col == 0 and pdf.will_page_break(max_h + 6):
            pdf.add_page()
            y = pdf.get_y()
            row_h = 0

        x = x0 + col * (cell_w + gap)
        try:
            pdf.image(
                BytesIO(data),
                x=x,
                y=y,
                w=cell_w,
                h=max_h,
                keep_aspect_ratio=True,
            )
            drawn_h = max_h
        except (FPDFException, OSError, ValueError):
            logger.exception("Не вдалося вставити фото у PDF візиту")
            pdf.set_xy(x, y)
            pdf.set_font("Unicode", "", 8)
            pdf.set_text_color(*COLOR_MUTED)
            pdf.cell(cell_w, 8, "Фото недоступне")
            drawn_h = 8

        row_h = max(row_h, drawn_h)
        col += 1
        if col >= cols:
            y += row_h + gap
            pdf.set_y(y)
            col = 0
            row_h = 0

    if col != 0:
        pdf.set_y(y + row_h + gap)


def build_visit_detail_pdf(
    *,
    visit: Visit,
    show_manager: bool = True,
    generated_at: datetime | None = None,
    photo_bytes: list[bytes] | None = None,
) -> bytes:
    when = generated_at or datetime.now(KYIV)
    client = visit.client
    title = f"Візит від {format_visit_date(visit.created_at)}"
    images = photo_bytes or []
    pdf = ReportPDF(doc_title=title, strip_label="Звіт по візиту")
    pdf.add_page()
    summaries = [
        ("Тип", visit_type_label(visit.visit_type)),
        ("Клієнт", (client.name if client else "—")[:40]),
    ]
    if images:
        summaries.append(("Фото", str(len(images))))
    draw_title_block(
        pdf,
        title=title,
        generated_at=when,
        summaries=summaries,
    )

    rows: list[tuple[str, str]] = [
        ("Дата", format_visit_date(visit.created_at)),
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

    _embed_photos(pdf, images)
    return bytes(pdf.output())
