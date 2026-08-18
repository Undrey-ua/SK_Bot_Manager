"""Періоди візитів: сьогодні та ISO-тиждень (Київ, понеділок–неділя)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from database.models import VISIT_TYPE_LABELS, VisitType

KYIV = ZoneInfo("Europe/Kyiv")
VISIT_FILTER_FIRST_YEAR = 2020


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


def iso_year_range(year: int) -> tuple[datetime, datetime]:
    start, _ = iso_week_range(year, 1)
    _, end = iso_week_range(year, iso_weeks_in_year(year))
    return start, end


def today_range(now: datetime | None = None) -> tuple[datetime, datetime]:
    current = now or now_kyiv()
    start = datetime.combine(current.date(), time.min, tzinfo=KYIV)
    return start, start + timedelta(days=1)


def week_option_label(year: int, week: int) -> str:
    start_d = date.fromisocalendar(year, week, 1)
    end_d = start_d + timedelta(days=6)
    return f"Тиждень {week} ({start_d.strftime('%d.%m')}–{end_d.strftime('%d.%m')})"


def last_week_of(year: int, *, current_year: int, current_week: int) -> int:
    if year == current_year:
        return current_week
    return iso_weeks_in_year(year)


def week_options(year: int, *, up_to_week: int | None = None) -> list[tuple[int, str]]:
    last = iso_weeks_in_year(year)
    if up_to_week is not None:
        last = min(last, up_to_week)
    return [
        (week, week_option_label(year, week))
        for week in range(last, 0, -1)
    ]


def visit_year_options(current_year: int) -> list[int]:
    first = min(VISIT_FILTER_FIRST_YEAR, current_year)
    return list(range(current_year, first - 1, -1))


@dataclass(frozen=True)
class VisitPeriodFilter:
    start_at: datetime | None
    end_at: datetime | None
    period: str | None
    week: int | None
    iso_year: int
    current_year: int
    current_week: int
    selected_year: int | None
    title: str
    filename: str


def parse_visit_type_filter(raw: str | None) -> str | None:
    if raw in {VisitType.PVH.value, VisitType.STAND.value}:
        return raw
    return None


def visits_title_with_type(title: str, visit_type: str | None) -> str:
    if visit_type is None:
        return title
    label = VISIT_TYPE_LABELS[VisitType(visit_type)]
    if title == "Візити":
        return f"Візити — {label}"
    return f"{title} · {label}"


def visits_filename_with_type(filename: str, visit_type: str | None) -> str:
    if visit_type is None:
        return filename
    return filename.removesuffix(".pdf") + f"-{visit_type}.pdf"


def parse_visit_period(
    *,
    period: str | None,
    week: int | None,
    year: int | None = None,
) -> VisitPeriodFilter:
    now = now_kyiv()
    current_year, current_week = current_iso_week(now)
    first_year = min(VISIT_FILTER_FIRST_YEAR, current_year)
    selected_year = (
        year if year is not None and first_year <= year <= current_year else None
    )
    week_year = selected_year if selected_year is not None else current_year
    max_week = last_week_of(
        week_year, current_year=current_year, current_week=current_week
    )
    selected_week = week if week is not None and 1 <= week <= max_week else None

    if selected_week is not None:
        start, end = iso_week_range(week_year, selected_week)
        return VisitPeriodFilter(
            start_at=start,
            end_at=end,
            period=None,
            week=selected_week,
            iso_year=week_year,
            current_year=current_year,
            current_week=current_week,
            selected_year=week_year,
            title=f"Візити — {week_option_label(week_year, selected_week)} {week_year}",
            filename=f"visits-{week_year}-week-{selected_week}.pdf",
        )

    if period == "today":
        start, end = today_range(now)
        return VisitPeriodFilter(
            start_at=start,
            end_at=end,
            period="today",
            week=None,
            iso_year=current_year,
            current_year=current_year,
            current_week=current_week,
            selected_year=None,
            title="Візити — сьогодні",
            filename="visits-today.pdf",
        )

    if selected_year is not None:
        start, end = iso_year_range(selected_year)
        return VisitPeriodFilter(
            start_at=start,
            end_at=end,
            period=None,
            week=None,
            iso_year=selected_year,
            current_year=current_year,
            current_week=current_week,
            selected_year=selected_year,
            title=f"Візити — {selected_year}",
            filename=f"visits-{selected_year}.pdf",
        )

    return VisitPeriodFilter(
        start_at=None,
        end_at=None,
        period=None,
        week=None,
        iso_year=current_year,
        current_year=current_year,
        current_week=current_week,
        selected_year=None,
        title="Візити",
        filename="visits.pdf",
    )


def visits_page_query(
    *,
    manager_id: int | None = None,
    visit_type: str | None = None,
    year: int | None = None,
    period: str | None = None,
    week: int | None = None,
    page: int | None = None,
) -> str:
    parts: list[str] = []
    if manager_id is not None:
        parts.append(f"manager_id={manager_id}")
    if visit_type in {VisitType.PVH.value, VisitType.STAND.value}:
        parts.append(f"visit_type={visit_type}")
    if period == "today":
        parts.append("period=today")
    else:
        if year is not None:
            parts.append(f"year={year}")
        if week is not None:
            parts.append(f"week={week}")
    if page is not None and page > 1:
        parts.append(f"page={page}")
    return ("?" + "&".join(parts)) if parts else ""
