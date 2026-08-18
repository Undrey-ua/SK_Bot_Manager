"""Спільна оболонка PDF-звітів панелі (смуга SK Bot Manager, картки, таблиця)."""

from __future__ import annotations

from datetime import datetime

from fpdf import FPDF
from fpdf.enums import Align, XPos, YPos

from web.stands_pdf import (
    COLOR_BORDER,
    COLOR_HEADER_BG,
    COLOR_HEADER_TEXT,
    COLOR_MUTED,
    COLOR_SUMMARY_BG,
    KYIV,
    _unicode_font_path,
)


class ReportPDF(FPDF):
    def __init__(self, *, doc_title: str, strip_label: str) -> None:
        super().__init__(orientation="L", unit="mm", format="A4")
        self._doc_title = doc_title
        self._strip_label = strip_label
        font_path = _unicode_font_path()
        self.add_font("Unicode", "", font_path)
        self.add_font("Unicode", "B", font_path)
        self.set_auto_page_break(auto=True, margin=14)
        self.alias_nb_pages()
        self.set_margins(10, 10, 10)

    def header(self) -> None:
        if self.page_no() > 1:
            self.set_font("Unicode", "B", 9)
            self.set_text_color(*COLOR_MUTED)
            self.cell(0, 6, self._doc_title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(1)

    def footer(self) -> None:
        self.set_y(-10)
        self.set_font("Unicode", "", 7)
        self.set_text_color(*COLOR_MUTED)
        self.cell(
            0,
            6,
            f"SK Bot Manager  ·  {self._doc_title}  ·  стор. {self.page_no()}/{{nb}}",
            align=Align.C,
        )


def draw_title_block(
    pdf: ReportPDF,
    *,
    title: str,
    generated_at: datetime,
    summaries: list[tuple[str, str]],
) -> None:
    stamp = generated_at.astimezone(KYIV).strftime("%d.%m.%Y %H:%M")

    pdf.set_fill_color(*COLOR_HEADER_BG)
    pdf.rect(10, 10, pdf.epw, 14, style="F")
    pdf.set_xy(14, 12)
    pdf.set_font("Unicode", "B", 11)
    pdf.set_text_color(*COLOR_HEADER_TEXT)
    pdf.cell(40, 6, "SK Bot Manager", new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_font("Unicode", "", 8)
    pdf.set_text_color(180, 190, 210)
    pdf.cell(0, 6, pdf._strip_label, align=Align.R)

    pdf.set_y(28)
    pdf.set_text_color(15, 23, 42)
    pdf.set_font("Unicode", "B", 15)
    pdf.multi_cell(0, 7, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Unicode", "", 8)
    pdf.set_text_color(*COLOR_MUTED)
    pdf.cell(0, 5, f"Сформовано: {stamp}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)

    if not summaries:
        return

    n = len(summaries)
    gap = 4
    card_w = (pdf.epw - gap * (n - 1)) / n
    card_y = pdf.get_y()
    card_h = 16
    for i, (label, value) in enumerate(summaries):
        x = 10 + i * (card_w + gap)
        pdf.set_fill_color(*COLOR_SUMMARY_BG)
        pdf.set_draw_color(*COLOR_BORDER)
        pdf.rect(x, card_y, card_w, card_h, style="DF")
        pdf.set_xy(x + 3, card_y + 3)
        pdf.set_font("Unicode", "", 7)
        pdf.set_text_color(*COLOR_MUTED)
        pdf.cell(card_w - 6, 4, label, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_x(x + 3)
        pdf.set_font("Unicode", "B", 9)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(card_w - 6, 6, value)

    pdf.set_y(card_y + card_h + 6)


def draw_empty_message(pdf: ReportPDF, text: str) -> None:
    pdf.set_font("Unicode", "", 11)
    pdf.set_text_color(*COLOR_MUTED)
    pdf.multi_cell(0, 6, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
