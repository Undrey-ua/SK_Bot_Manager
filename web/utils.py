from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from database.models import (
    MANAGER_TASK_KIND_DEFAULT,
    MANAGER_TASK_KIND_LABELS,
    VISIT_TYPE_LABELS,
    Client,
    ManagerTaskKind,
    Visit,
    VisitType,
)
from visit_task_labels import visit_task_label

MANAGER_TASK_KIND_CHOICES: list[tuple[str, str]] = [
    (k.value, MANAGER_TASK_KIND_LABELS[k]) for k in ManagerTaskKind
]

UK_MONTHS: list[tuple[int, str]] = [
    (1, "Січень"),
    (2, "Лютий"),
    (3, "Березень"),
    (4, "Квітень"),
    (5, "Травень"),
    (6, "Червень"),
    (7, "Липень"),
    (8, "Серпень"),
    (9, "Вересень"),
    (10, "Жовтень"),
    (11, "Листопад"),
    (12, "Грудень"),
]

KYIV = ZoneInfo("Europe/Kyiv")

WEEKDAY_LABELS: list[str] = [
    "Понеділок",
    "Вівторок",
    "Середа",
    "Четвер",
    "П'ятниця",
    "Субота",
    "Неділя",
]


def task_label(task_value: str) -> str:
    return visit_task_label(task_value)


def visit_type_label(visit_type: str) -> str:
    try:
        return VISIT_TYPE_LABELS[VisitType(visit_type)]
    except (ValueError, KeyError):
        return visit_type


def manager_task_kind_value(task_kind: str | None) -> str:
    from database.models import normalize_manager_task_kind

    return normalize_manager_task_kind(task_kind)


def manager_task_kind_label(task_kind: str | None) -> str:
    key = manager_task_kind_value(task_kind)
    try:
        return MANAGER_TASK_KIND_LABELS[ManagerTaskKind(key)]
    except KeyError:
        return key


def user_initials(name: str | None) -> str:
    """Ініціали з ПІБ, напр. «Serhiy Shalia» → SS."""
    if not name or not name.strip():
        return "?"
    parts = [p for p in name.strip().split() if p]
    if len(parts) == 1:
        token = parts[0]
        return (token[:2] if len(token) >= 2 else token).upper()
    return f"{parts[0][0]}{parts[-1][0]}".upper()


def uk_month_name(month: int) -> str:
    for num, name in UK_MONTHS:
        if num == month:
            return name
    return str(month)


def plan_progress_pct(actual: Decimal, target: Decimal | None) -> int:
    if target is None or target <= 0:
        return 0
    return int(min(Decimal(100), (actual / target * Decimal(100)).quantize(Decimal("1"))))


def parse_manager_task_kind_filter(raw: str | None) -> str | None:
    """None = усі типи."""
    if not raw or not str(raw).strip():
        return None
    try:
        return ManagerTaskKind(str(raw).strip()).value
    except ValueError:
        return None


def tasks_page_query(
    *,
    manager_id: int | None = None,
    status: str | None = None,
    kind: str | None = None,
    show_completed: bool = False,
) -> str:
    """Query string for /tasks links (без leading ? якщо порожньо)."""
    parts: list[str] = []
    if manager_id is not None:
        parts.append(f"manager_id={manager_id}")
    if status and status != "active":
        parts.append(f"status={status}")
    if kind:
        parts.append(f"kind={kind}")
    if show_completed:
        parts.append("show_completed=1")
    return ("?" + "&".join(parts)) if parts else ""


def format_date(d: date | None) -> str:
    if d is None:
        return "—"
    return d.strftime("%d.%m.%Y")


def format_dt(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    local = dt.astimezone(KYIV)
    return local.strftime("%d.%m.%Y %H:%M")


def format_qty(value: Decimal | float | int | None, *, decimals: int = 3) -> str:
    if value is None:
        return "—"
    n = Decimal(str(value))
    return f"{n:.{decimals}f}"


def format_signed_qty(value: Decimal | float | int | None, *, decimals: int = 3) -> str:
    if value is None:
        return "—"
    n = Decimal(str(value))
    if n > 0:
        return f"+{n:.{decimals}f}"
    return f"{n:.{decimals}f}"


def format_signed_pct(value: float | None, *, decimals: int = 1) -> str:
    if value is None:
        return ""
    if value > 0:
        return f"+{value:.{decimals}f}%"
    return f"{value:.{decimals}f}%"


def client_stands(client: Client) -> str:
    names = [
        link.stand.name
        for link in client.stand_links
        if link.stand and link.stand.is_active
    ]
    return ", ".join(names) or "—"


def client_has_equipment(client: Client) -> bool:
    for link in client.stand_links:
        if link.stand and link.stand.is_active:
            return True
    for link in client.swatch_links:
        if link.brand and link.brand.is_active:
            return True
    return False


def client_stands_map_json(clients: list[Client]) -> str:
    """JSON для фільтра стендів у модалці переміщення/списання."""
    data: dict[str, list[dict[str, int | str]]] = {}
    for client in clients:
        items: list[dict[str, int | str]] = []
        for link in client.stand_links:
            stand = link.stand
            if stand is None or not stand.is_active:
                continue
            items.append(
                {
                    "id": link.stand_id,
                    "name": stand.name,
                    "qty": max(1, int(getattr(link, "quantity", 1) or 1)),
                }
            )
        if items:
            data[str(client.id)] = items
    return json.dumps(data, ensure_ascii=False)


def warehouse_stands_map_json(rows: list) -> str:
    """JSON для модалки «Зі складу» (список стендів на складі менеджера)."""
    items = [
        {"id": row.stand_id, "name": row.stand_name, "qty": row.quantity}
        for row in rows
    ]
    return json.dumps(items, ensure_ascii=False)


def warehouse_stands_modal_json(overview_rows: list) -> str:
    """JSON для модалки зі складу: регіональні залишки + підказка, якщо список порожній."""
    items = [
        {
            "id": row.stand_id,
            "name": row.stand_name,
            "qty": row.regional_quantity,
        }
        for row in overview_rows
        if row.regional_quantity > 0
    ]
    has_central = any(row.central_quantity > 0 for row in overview_rows)
    has_regional = bool(items)
    empty_hint = ""
    if not has_regional and has_central:
        empty_hint = (
            "Стенди є на центральному складі. Керівник має перемістити їх "
            "на регіональний перед встановленням на ТТ."
        )
    elif not has_regional:
        empty_hint = "На регіональному складі немає стендів для встановлення."
    return json.dumps(
        {"items": items, "empty_hint": empty_hint},
        ensure_ascii=False,
    )
