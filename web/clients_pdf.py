"""PDF-звіт списку клієнтів (стенди / ПВХ / потенційні)."""

from __future__ import annotations

from datetime import datetime

from fpdf.fonts import FontFace

from database.models import Client
from web.client_geo import client_city, client_display_legal_name
from web.pdf_report import ReportPDF, draw_empty_message, draw_title_block
from web.stands_pdf import COLOR_HEADER_BG, COLOR_HEADER_TEXT, COLOR_ROW_ALT, KYIV
from web.utils import client_stands


def clients_title(*, is_potential: bool, is_pvc: bool) -> str:
    if is_pvc and is_potential:
        return "Потенційні клієнти ПВХ"
    if is_pvc:
        return "Клієнти ПВХ"
    if is_potential:
        return "Потенційні клієнти"
    return "Клієнти"


def clients_pdf_filename(*, is_potential: bool, is_pvc: bool) -> str:
    if is_pvc and is_potential:
        return "clients-pvc-potential.pdf"
    if is_pvc:
        return "clients-pvc.pdf"
    if is_potential:
        return "clients-potential.pdf"
    return "clients.pdf"


def build_clients_pdf(
    *,
    clients: list[Client],
    is_potential: bool = False,
    is_pvc: bool = False,
    show_manager: bool = True,
    generated_at: datetime | None = None,
) -> bytes:
    title = clients_title(is_potential=is_potential, is_pvc=is_pvc)
    when = generated_at or datetime.now(KYIV)
    pdf = ReportPDF(doc_title=title, strip_label="База клієнтів")
    pdf.add_page()
    draw_title_block(
        pdf,
        title=title,
        generated_at=when,
        summaries=[("Клієнтів", str(len(clients)))],
    )

    if not clients:
        empty = (
            "Потенційних клієнтів за обраними фільтрами не знайдено."
            if is_potential
            else "Клієнтів за обраними фільтрами не знайдено."
        )
        draw_empty_message(pdf, empty)
        return bytes(pdf.output())

    headings_style = FontFace(
        family="Unicode",
        emphasis="BOLD",
        size_pt=8,
        color=COLOR_HEADER_TEXT,
        fill_color=COLOR_HEADER_BG,
    )
    body_style = FontFace(family="Unicode", size_pt=7.5)
    alt_style = FontFace(family="Unicode", size_pt=7.5, fill_color=COLOR_ROW_ALT)

    headers = ["№", "Назва", "Юридична назва"]
    if show_manager:
        headers.append("Менеджер")
    headers.extend(["Область", "Місто", "Адреса"])
    if not is_pvc:
        headers.append("Стенди")

    n = len(headers)
    num_w = 8
    rest = pdf.epw - num_w
    if is_pvc:
        if show_manager:
            shares = (0.22, 0.22, 0.16, 0.14, 0.12, 0.14)
        else:
            shares = (0.26, 0.26, 0.16, 0.14, 0.18)
    else:
        if show_manager:
            shares = (0.18, 0.18, 0.14, 0.12, 0.10, 0.14, 0.14)
        else:
            shares = (0.22, 0.22, 0.14, 0.12, 0.16, 0.14)

    col_widths = [num_w] + [rest * s for s in shares]
    leftover = pdf.epw - sum(col_widths)
    col_widths[-1] += leftover

    align = ["CENTER"] + ["LEFT"] * (n - 1)

    with pdf.table(
        width=pdf.epw,
        col_widths=col_widths,
        headings_style=headings_style,
        line_height=5,
        text_align=tuple(align),
    ) as table:
        header_row = table.row()
        for h in headers:
            header_row.cell(h)

        for idx, client in enumerate(clients, 1):
            style = alt_style if idx % 2 == 0 else body_style
            data_row = table.row()
            cells = [
                str(idx),
                client.name,
                client_display_legal_name(client),
            ]
            if show_manager:
                cells.append(client.manager.name if client.manager else "—")
            cells.extend(
                [
                    client.region.name if client.region else "—",
                    client_city(client),
                    client.address or "—",
                ]
            )
            if not is_pvc:
                cells.append(client_stands(client))
            for text in cells:
                data_row.cell(text, style=style)

    return bytes(pdf.output())
