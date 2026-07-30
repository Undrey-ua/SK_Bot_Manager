"""PDF-звіт матриці продажів."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fpdf import FPDF
from fpdf.enums import Align, XPos, YPos
from fpdf.fonts import FontFace

from web.services.analytics import MatrixCell, MatrixColumn
from web.stands_pdf import (
    COLOR_BORDER,
    COLOR_HEADER_BG,
    COLOR_HEADER_TEXT,
    COLOR_MUTED,
    COLOR_ROW_ALT,
    COLOR_SUMMARY_BG,
    KYIV,
    _unicode_font_path,
)


def _fmt_qty(value: Decimal | None) -> str:
    if value is None:
        return "—"
    q = Decimal(value)
    if q == q.to_integral_value():
        return str(int(q))
    text = f"{q:.2f}"
    return text.rstrip("0").rstrip(".")


def _cell_text(cell: MatrixCell) -> str:
    if cell.kind == "sale":
        return _fmt_qty(cell.quantity)
    if cell.kind == "no_sale":
        return "0"
    return "×"


def _stands_text(badges: list[str]) -> str:
    if not badges:
        return "—"
    return ", ".join(badges)


class SalesMatrixPDF(FPDF):
    def __init__(self, *, doc_title: str) -> None:
        super().__init__(orientation="L", unit="mm", format="A4")
        self._doc_title = doc_title
        font_path = _unicode_font_path()
        self.add_font("Unicode", "", font_path)
        self.add_font("Unicode", "B", font_path)
        self.set_auto_page_break(auto=True, margin=12)
        self.alias_nb_pages()
        self.set_margins(8, 8, 8)

    def header(self) -> None:
        if self.page_no() > 1:
            self.set_font("Unicode", "B", 8)
            self.set_text_color(*COLOR_MUTED)
            self.cell(0, 5, self._doc_title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(1)

    def footer(self) -> None:
        self.set_y(-9)
        self.set_font("Unicode", "", 7)
        self.set_text_color(*COLOR_MUTED)
        self.cell(
            0,
            5,
            f"SK Bot Manager  ·  {self._doc_title}  ·  стор. {self.page_no()}/{{nb}}",
            align=Align.C,
        )


def _draw_header(
    pdf: SalesMatrixPDF,
    *,
    title: str,
    generated_at: datetime,
    matrix_total: int,
    matrix_worked: int,
    matrix_failed: int,
    matrix_pct: int,
) -> None:
    stamp = generated_at.astimezone(KYIV).strftime("%d.%m.%Y %H:%M")

    pdf.set_fill_color(*COLOR_HEADER_BG)
    pdf.rect(8, 8, pdf.epw, 12, style="F")
    pdf.set_xy(11, 10)
    pdf.set_font("Unicode", "B", 10)
    pdf.set_text_color(*COLOR_HEADER_TEXT)
    pdf.cell(35, 5, "SK Bot Manager", new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_font("Unicode", "", 7)
    pdf.set_text_color(180, 190, 210)
    pdf.cell(0, 5, "Матриця продажів", align=Align.R)

    pdf.set_y(24)
    pdf.set_text_color(15, 23, 42)
    pdf.set_font("Unicode", "B", 14)
    pdf.multi_cell(0, 6, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Unicode", "", 7)
    pdf.set_text_color(*COLOR_MUTED)
    pdf.cell(0, 4, f"Сформовано: {stamp}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    pdf.set_font("Unicode", "", 7)
    pdf.set_text_color(60, 60, 60)
    pdf.multi_cell(
        0,
        3.5,
        "Легенда: число — продаж (кв. м); 0 — стенд є, продажу немає; × — стенду немає.",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.ln(2)

    card_w = (pdf.epw - 6) / 4
    card_y = pdf.get_y()
    card_h = 14
    cards = [
        ("Торгових точок", str(matrix_total)),
        ("Спрацювало", str(matrix_worked)),
        ("Не спрацювало", str(matrix_failed)),
        ("Відсоток", f"{matrix_pct}%"),
    ]
    for i, (label, value) in enumerate(cards):
        x = 8 + i * (card_w + 2)
        pdf.set_fill_color(*COLOR_SUMMARY_BG)
        pdf.set_draw_color(*COLOR_BORDER)
        pdf.rect(x, card_y, card_w, card_h, style="DF")
        pdf.set_xy(x + 2.5, card_y + 2)
        pdf.set_font("Unicode", "", 6)
        pdf.set_text_color(*COLOR_MUTED)
        pdf.cell(card_w - 5, 3.5, label)
        pdf.set_xy(x + 2.5, card_y + 6)
        pdf.set_font("Unicode", "B", 10)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(card_w - 5, 5, value)

    pdf.set_y(card_y + card_h + 5)


def _build_matrix_table(
    pdf: SalesMatrixPDF,
    *,
    columns: list[MatrixColumn],
    rows: list[dict[str, object]],
) -> None:
    if not rows:
        pdf.set_font("Unicode", "", 10)
        pdf.multi_cell(0, 5, "Немає даних для матриці.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        return

    headings_style = FontFace(
        family="Unicode",
        emphasis="BOLD",
        size_pt=6.5,
        color=COLOR_HEADER_TEXT,
        fill_color=COLOR_HEADER_BG,
    )
    body_style = FontFace(family="Unicode", size_pt=6)
    alt_style = FontFace(family="Unicode", size_pt=6, fill_color=COLOR_ROW_ALT)
    inactive_style = FontFace(family="Unicode", size_pt=6, fill_color=(255, 247, 237))

    num_w = 7
    total_w = 14
    stands_w = 32
    name_w = 38
    brand_count = max(len(columns), 1)
    brand_w = max(11, (pdf.epw - num_w - name_w - stands_w - total_w) / brand_count)

    col_widths = [num_w, name_w, stands_w] + [brand_w] * len(columns) + [total_w]
    align = ("CENTER", "LEFT", "LEFT") + ("CENTER",) * len(columns) + ("CENTER",)

    with pdf.table(
        width=pdf.epw,
        col_widths=col_widths,
        headings_style=headings_style,
        line_height=4.2,
        text_align=align,
    ) as table:
        header = table.row()
        header.cell("№")
        header.cell("Торгова точка")
        header.cell("Стенди")
        for col in columns:
            meta = (
                f"{col.total_points} ТТ · {col.worked_points} так · "
                f"{col.failed_points} ні · {col.pct}%"
            )
            header.cell(f"{col.label}\n{meta}")
        header.cell("Всього")

        for idx, row in enumerate(rows, 1):
            worked = bool(row.get("worked"))
            style = body_style if worked else inactive_style
            if idx % 2 == 0 and worked:
                style = alt_style

            client = str(row.get("client") or "")
            legal = str(row.get("legal_name") or "").strip()
            if legal:
                client = f"{client}\n{legal}"

            cells_dict: dict[str, MatrixCell] = row.get("cells") or {}
            total = row.get("total") or Decimal(0)
            total_text = _fmt_qty(total) if total else "0"

            data_row = table.row()
            data_row.cell(str(idx), style=style)
            data_row.cell(client, style=style)
            data_row.cell(_stands_text(list(row.get("stand_badges") or [])), style=style)
            for col in columns:
                cell = cells_dict.get(col.key, MatrixCell(kind="na"))
                data_row.cell(_cell_text(cell), style=style)
            data_row.cell(total_text, style=style)


def build_sales_matrix_pdf(
    *,
    title: str,
    columns: list[MatrixColumn],
    rows: list[dict[str, object]],
    generated_at: datetime | None = None,
) -> bytes:
    when = generated_at or datetime.now(KYIV)
    matrix_total = len(rows)
    matrix_worked = sum(1 for r in rows if r.get("worked"))
    matrix_failed = matrix_total - matrix_worked
    matrix_pct = int(round(matrix_worked / matrix_total * 100)) if matrix_total else 0

    pdf = SalesMatrixPDF(doc_title=title)
    pdf.add_page()
    _draw_header(
        pdf,
        title=title,
        generated_at=when,
        matrix_total=matrix_total,
        matrix_worked=matrix_worked,
        matrix_failed=matrix_failed,
        matrix_pct=matrix_pct,
    )
    _build_matrix_table(pdf, columns=columns, rows=rows)
    return bytes(pdf.output())
