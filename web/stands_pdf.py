"""PDF-звіт списку ТТ зі стендами."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fpdf import FPDF
from fpdf.enums import Align, XPos, YPos
from fpdf.fonts import FontFace

from web.services.analytics import StandClientDetailRow

_FONT_CANDIDATES = (
    Path(__file__).resolve().parent / "static" / "fonts" / "DejaVuSans.ttf",
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
)

KYIV = ZoneInfo("Europe/Kyiv")

# Кольори як у веб-панелі (.table--darkhead)
COLOR_HEADER_BG = (11, 18, 32)
COLOR_HEADER_TEXT = (255, 255, 255)
COLOR_ACCENT = (37, 99, 235)
COLOR_MUTED = (100, 116, 139)
COLOR_ROW_ALT = (248, 250, 252)
COLOR_BORDER = (226, 232, 240)
COLOR_SUMMARY_BG = (241, 245, 249)


def _unicode_font_path() -> str:
    for path in _FONT_CANDIDATES:
        if path.is_file():
            return str(path)
    raise FileNotFoundError(
        "Не знайдено шрифт для PDF. Встановіть fonts-dejavu-core або додайте DejaVuSans.ttf."
    )


def _format_stands(lines: list[tuple[str, int]]) -> str:
    return ", ".join(
        f"{name}" if qty <= 1 else f"{name} ×{qty}" for name, qty in lines
    )


def _stand_total(lines: list[tuple[str, int]]) -> int:
    return sum(qty for _, qty in lines)


def _stands_summary(rows: list[StandClientDetailRow]) -> str:
    counter: Counter[str] = Counter()
    for row in rows:
        for name, qty in row.stand_lines:
            counter[name] += qty
    if not counter:
        return "—"
    parts = [f"{name}: {qty} шт" for name, qty in counter.most_common()]
    return " · ".join(parts)


class StandsClientsPDF(FPDF):
    def __init__(self, *, doc_title: str) -> None:
        super().__init__(orientation="L", unit="mm", format="A4")
        self._doc_title = doc_title
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


def _draw_title_block(
    pdf: StandsClientsPDF,
    *,
    title: str,
    generated_at: datetime,
    rows: list[StandClientDetailRow],
) -> None:
    total_stands = sum(_stand_total(r.stand_lines) for r in rows)
    generated_local = generated_at.astimezone(KYIV)
    stamp = generated_local.strftime("%d.%m.%Y %H:%M")

    # Брендова смуга
    pdf.set_fill_color(*COLOR_HEADER_BG)
    pdf.rect(10, 10, pdf.epw, 14, style="F")
    pdf.set_xy(14, 12)
    pdf.set_font("Unicode", "B", 11)
    pdf.set_text_color(*COLOR_HEADER_TEXT)
    pdf.cell(40, 6, "SK Bot Manager", new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_font("Unicode", "", 8)
    pdf.set_text_color(180, 190, 210)
    pdf.cell(0, 6, "Звіт по встановлених стендах", align=Align.R)

    pdf.set_y(28)
    pdf.set_text_color(15, 23, 42)
    pdf.set_font("Unicode", "B", 15)
    pdf.multi_cell(0, 7, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Unicode", "", 8)
    pdf.set_text_color(*COLOR_MUTED)
    pdf.cell(0, 5, f"Сформовано: {stamp}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)

    # Підсумкові картки
    card_w = (pdf.epw - 8) / 3
    card_y = pdf.get_y()
    card_h = 16
    summaries = [
        ("Торгових точок", str(len(rows))),
        ("Встановлень (шт)", str(total_stands)),
        ("По марках", _stands_summary(rows)),
    ]
    for i, (label, value) in enumerate(summaries):
        x = 10 + i * (card_w + 4)
        pdf.set_fill_color(*COLOR_SUMMARY_BG)
        pdf.set_draw_color(*COLOR_BORDER)
        pdf.rect(x, card_y, card_w, card_h, style="DF")
        pdf.set_xy(x + 3, card_y + 3)
        pdf.set_font("Unicode", "", 7)
        pdf.set_text_color(*COLOR_MUTED)
        pdf.cell(card_w - 6, 4, label, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_x(x + 3)
        pdf.set_font("Unicode", "B", 9 if i < 2 else 7)
        pdf.set_text_color(15, 23, 42)
        if i < 2:
            pdf.cell(card_w - 6, 6, value)
        else:
            pdf.multi_cell(card_w - 6, 4, value, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_y(card_y + card_h + 6)


def _build_table(
    pdf: StandsClientsPDF,
    *,
    rows: list[StandClientDetailRow],
    show_manager: bool,
) -> None:
    headings_style = FontFace(
        family="Unicode",
        emphasis="BOLD",
        size_pt=8,
        color=COLOR_HEADER_TEXT,
        fill_color=COLOR_HEADER_BG,
    )
    body_style = FontFace(family="Unicode", size_pt=7.5)
    alt_style = FontFace(family="Unicode", size_pt=7.5, fill_color=COLOR_ROW_ALT)

    headers = ["№", "Торгова точка", "Юридична назва", "Стенди", "К-сть", "Місто", "Область"]
    if show_manager:
        headers.append("Менеджер")
    headers.append("Адреса")

    n = len(headers)
    num_w = 8
    qty_w = 10
    city_w = 22
    oblast_w = 26
    rest = pdf.epw - num_w - qty_w - city_w - oblast_w
    if show_manager:
        fixed_share = rest * 0.22
        col_widths = [
            num_w,
            rest * 0.20,
            rest * 0.22,
            rest * 0.24,
            qty_w,
            city_w,
            oblast_w,
            fixed_share,
            rest - rest * 0.20 - rest * 0.22 - rest * 0.24 - fixed_share,
        ]
    else:
        col_widths = [
            num_w,
            rest * 0.22,
            rest * 0.24,
            rest * 0.26,
            qty_w,
            city_w,
            oblast_w,
            rest - rest * 0.22 - rest * 0.24 - rest * 0.26,
        ]

    with pdf.table(
        width=pdf.epw,
        col_widths=col_widths,
        headings_style=headings_style,
        line_height=5,
        text_align=("CENTER", "LEFT", "LEFT", "LEFT", "CENTER", "LEFT", "LEFT")
        + (("LEFT",) if show_manager else ())
        + ("LEFT",),
    ) as table:
        header_row = table.row()
        for h in headers:
            header_row.cell(h)

        for idx, row in enumerate(rows, 1):
            style = alt_style if idx % 2 == 0 else body_style
            data_row = table.row()
            cells = [
                str(idx),
                row.name,
                row.legal_name or "—",
                _format_stands(row.stand_lines),
                str(_stand_total(row.stand_lines)),
                row.city,
                row.oblast,
            ]
            if show_manager:
                cells.append(row.manager)
            cells.append(row.address if row.address and row.address != "—" else "—")
            for text, cell_style in zip(cells, [style] * len(cells)):
                data_row.cell(text, style=cell_style)


def build_stands_clients_pdf(
    *,
    title: str,
    rows: list[StandClientDetailRow],
    show_manager: bool = True,
    generated_at: datetime | None = None,
) -> bytes:
    when = generated_at or datetime.now(KYIV)
    pdf = StandsClientsPDF(doc_title=title)
    pdf.add_page()
    _draw_title_block(pdf, title=title, generated_at=when, rows=rows)

    if not rows:
        pdf.set_font("Unicode", "", 11)
        pdf.set_text_color(*COLOR_MUTED)
        pdf.multi_cell(
            0,
            6,
            "Немає торгових точок за обраними критеріями.",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        return bytes(pdf.output())

    _build_table(pdf, rows=rows, show_manager=show_manager)
    return bytes(pdf.output())
