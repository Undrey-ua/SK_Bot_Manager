"""Періоди візитів: сьогодні та ISO-тиждень (Київ, понеділок–неділя)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

KYIV = ZoneInfo("Europe/Kyiv")


def now_kyiv() -> datetime:
    return datetime.now(KYIV)


def iso_weeks_in_year(year: int) -> int:
    return date(year, 12, 28).isocalendar().week


def current_iso_week(now: datetime | None = None) -> tuple[int, int]:
    """(ISO-рік, номер тижня 1–53)."""
    current = now or now_kyiv()
    iso = current.isocalendar()
    return iso.year, iso.week


def iso_week_range(year: int, week: int) -> tuple[datetime, datetime]:
    start_d = date.fromisocalendar(year, week, 1)
    start = datetime.combine(start_d, time.min, tzinfo=KYIV)
    return start, start + timedelta(days=7)


def today_range(now: datetime | None = None) -> tuple[datetime, datetime]:
    current = now or now_kyiv()
    start = datetime.combine(current.date(), time.min, tzinfo=KYIV)
    return start, start + timedelta(days=1)


def week_option_label(year: int, week: int) -> str:
    start_d = date.fromisocalendar(year, week, 1)
    end_d = start_d + timedelta(days=6)
    return f"Тиждень {week} ({start_d.strftime('%d.%m')}–{end_d.strftime('%d.%m')})"


def week_options(year: int, *, up_to_week: int | None = None) -> list[tuple[int, str]]:
    last = iso_weeks_in_year(year)
    if up_to_week is not None:
        last = min(last, up_to_week)
    return [
        (week, week_option_label(year, week))
        for week in range(1, last + 1)
    ]


@dataclass(frozen=True)
class VisitPeriodFilter:
    start_at: datetime | None
    end_at: datetime | None
    period: str | None
    week: int | None
    iso_year: int
    current_week: int
    title: str
    filename: str


def parse_visit_period(*, period: str | None, week: int | None) -> VisitPeriodFilter:
    now = now_kyiv()
    iso_year, current_week = current_iso_week(now)
    selected_week = (
        week if week is not None and 1 <= week <= current_week else None
    )

    if selected_week is not None:
        start, end = iso_week_range(iso_year, selected_week)
        return VisitPeriodFilter(
            start_at=start,
            end_at=end,
            period=None,
            week=selected_week,
            iso_year=iso_year,
            current_week=current_week,
            title=f"Візити — {week_option_label(iso_year, selected_week)}",
            filename=f"visits-week-{selected_week}.pdf",
        )

    if period == "today":
        start, end = today_range(now)
        return VisitPeriodFilter(
            start_at=start,
            end_at=end,
            period="today",
            week=None,
            iso_year=iso_year,
            current_week=current_week,
            title="Візити — сьогодні",
            filename="visits-today.pdf",
        )

    return VisitPeriodFilter(
        start_at=None,
        end_at=None,
        period=None,
        week=None,
        iso_year=iso_year,
        current_week=current_week,
        title="Візити",
        filename="visits.pdf",
    )


def visits_page_query(
    *,
    manager_id: int | None = None,
    period: str | None = None,
    week: int | None = None,
    page: int | None = None,
) -> str:
    parts: list[str] = []
    if manager_id is not None:
        parts.append(f"manager_id={manager_id}")
    if period == "today":
        parts.append("period=today")
    elif week is not None:
        parts.append(f"week={week}")
    if page is not None and page > 1:
        parts.append(f"page={page}")
    return ("?" + "&".join(parts)) if parts else ""
