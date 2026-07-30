"""Дані для діаграм порівняльної аналітики."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from web.services.analytics import CompareRow


def compare_totals_row(rows: list[CompareRow]) -> CompareRow | None:
    for row in rows:
        if row.label == "Разом":
            return row
    return None


def build_compare_bar_items(
    rows: list[CompareRow],
    *,
    limit: int = 10,
    exclude: frozenset[str] = frozenset({"Разом"}),
) -> list[dict[str, float | str]]:
    filtered = [r for r in rows if r.label not in exclude]
    filtered.sort(
        key=lambda r: max(float(r.current), float(r.previous)),
        reverse=True,
    )
    filtered = filtered[:limit]
    if not filtered:
        return []

    max_val = max(
        max(float(r.current), float(r.previous)) for r in filtered
    )
    if max_val <= 0:
        max_val = 1.0

    items: list[dict[str, float | str]] = []
    for row in filtered:
        base = float(row.previous)
        report = float(row.current)
        items.append(
            {
                "label": row.label,
                "base": base,
                "report": report,
                "base_pct": base / max_val * 100,
                "report_pct": report / max_val * 100,
                "delta": report - base,
                "pct": row.pct,
            }
        )
    return items


def compare_kpi_bar_items(rows: list[CompareRow]) -> list[dict[str, float | str]]:
    if not rows:
        return []

    max_val = max(
        max(float(r.current), float(r.previous)) for r in rows
    )
    if max_val <= 0:
        max_val = 1.0

    short_labels = {
        "Кількість торгових точок, що спрацювали": "Торгові точки",
        "Кількість стендів, що спрацювали": "Стенди",
    }
    items: list[dict[str, float | str]] = []
    for row in rows:
        base = float(row.previous)
        report = float(row.current)
        items.append(
            {
                "label": short_labels.get(row.label, row.label),
                "base": base,
                "report": report,
                "base_pct": base / max_val * 100,
                "report_pct": report / max_val * 100,
            }
        )
    return items


def total_bar_heights(base: Decimal, report: Decimal) -> tuple[float, float]:
    base_f = float(base)
    report_f = float(report)
    peak = max(base_f, report_f, 1.0)
    return base_f / peak * 100, report_f / peak * 100
