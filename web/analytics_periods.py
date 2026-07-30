from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date
    label: str


def month_range(year: int, month: int) -> DateRange:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return DateRange(start, end, f"{month:02d}.{year}")


def quarter_range(year: int, quarter: int) -> DateRange:
    start_month = (quarter - 1) * 3 + 1
    start = date(year, start_month, 1)
    if start_month == 10:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, start_month + 3, 1)
    return DateRange(start, end, f"Q{quarter} {year}")


def halfyear_range(year: int, half: int) -> DateRange:
    """half=1: січень–червень, half=2: липень–грудень."""
    if half == 1:
        return DateRange(date(year, 1, 1), date(year, 7, 1), f"I півр. {year}")
    return DateRange(date(year, 7, 1), date(year + 1, 1, 1), f"II півр. {year}")


def year_range(year: int) -> DateRange:
    return DateRange(date(year, 1, 1), date(year + 1, 1, 1), str(year))


def prev_month_range(year: int, month: int) -> DateRange:
    if month == 1:
        return month_range(year - 1, 12)
    return month_range(year, month - 1)


def prev_quarter_range(year: int, quarter: int) -> DateRange:
    if quarter == 1:
        return quarter_range(year - 1, 4)
    return quarter_range(year, quarter - 1)


def prev_year_range(year: int) -> DateRange:
    return year_range(year - 1)


def current_month_range(today: date | None = None) -> DateRange:
    today = today or date.today()
    return month_range(today.year, today.month)


def rolling_months_range(months: int, today: date | None = None) -> DateRange:
    """Поточний місяць і (months - 1) попередніх, з 1-го числа."""
    today = today or date.today()
    y, m = today.year, today.month
    start_m = m - (months - 1)
    start_y = y
    while start_m < 1:
        start_m += 12
        start_y -= 1
    start = date(start_y, start_m, 1)
    if m == 12:
        end = date(y + 1, 1, 1)
    else:
        end = date(y, m + 1, 1)
    return DateRange(start, end, f"останні {months} міс.")
