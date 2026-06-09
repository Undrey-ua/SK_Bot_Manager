from __future__ import annotations

from datetime import date

from web.analytics_periods import (
    DateRange,
    current_month_range,
    month_range,
    prev_month_range,
    quarter_range,
    rolling_months_range,
    year_range,
)

CLIENT_SALES_PERIOD_KINDS = (
    "current",
    "prev",
    "last_3",
    "last_6",
    "year",
    "quarter",
)

CLIENT_SALES_PERIOD_LABELS: dict[str, str] = {
    "current": "Поточний місяць",
    "prev": "Попередній місяць",
    "last_3": "Останні 3 місяці",
    "last_6": "Останні 6 місяців",
    "year": "Рік",
    "quarter": "Квартал",
}


def resolve_client_sales_period(
    period_kind: str,
    *,
    today: date | None = None,
    year: int | None = None,
    quarter: int | None = None,
) -> DateRange:
    today = today or date.today()
    year = year or today.year
    quarter = quarter or ((today.month - 1) // 3 + 1)

    if period_kind == "prev":
        return prev_month_range(today.year, today.month)
    if period_kind == "last_3":
        return rolling_months_range(3, today)
    if period_kind == "last_6":
        return rolling_months_range(6, today)
    if period_kind == "year":
        return year_range(year)
    if period_kind == "quarter":
        return quarter_range(year, quarter)
    return current_month_range(today)
