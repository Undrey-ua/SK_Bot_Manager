from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from database.models import (
    TASK_PRIORITY_LABELS,
    TASK_WORKFLOW_LABELS,
    TASK_WORKFLOW_OPEN,
    Task,
    TaskWorkflowStatus,
    User,
    normalize_task_priority,
    normalize_task_workflow_status,
)
from web.utils import WEEKDAY_LABELS, manager_task_kind_value

UK_MONTHS_GEN: list[str] = [
    "січня",
    "лютого",
    "березня",
    "квітня",
    "травня",
    "червня",
    "липня",
    "серпня",
    "вересня",
    "жовтня",
    "листопада",
    "грудня",
]

UK_MONTHS_NOM: list[str] = [
    "Січень",
    "Лютий",
    "Березень",
    "Квітень",
    "Травень",
    "Червень",
    "Липень",
    "Серпень",
    "Вересень",
    "Жовтень",
    "Листопад",
    "Грудень",
]

UK_WEEKDAYS_SHORT: list[str] = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]
UK_WEEKDAYS_FULL: list[str] = [
    "Понеділок",
    "Вівторок",
    "Середа",
    "Четвер",
    "Пʼятниця",
    "Субота",
    "Неділя",
]

WORKFLOW_COLUMNS: list[tuple[str, str]] = [
    (TaskWorkflowStatus.NEW.value, "Нова"),
    (TaskWorkflowStatus.IN_PROGRESS.value, "В роботі"),
    (TaskWorkflowStatus.WAITING.value, "Очікує"),
    (TaskWorkflowStatus.DONE.value, "Виконано"),
    (TaskWorkflowStatus.CANCELLED.value, "Скасовано"),
]


def workflow_status(task: Task) -> str:
    return normalize_task_workflow_status(
        getattr(task, "status", None),
        completed=task.completed_at is not None,
        cancelled=task.deleted_at is not None,
    )


def task_priority(task: Task) -> str:
    return normalize_task_priority(getattr(task, "priority", None))


def is_open_task(task: Task) -> bool:
    return workflow_status(task) in TASK_WORKFLOW_OPEN


def is_overdue_task(task: Task, today: date) -> bool:
    return (
        is_open_task(task)
        and task.deadline is not None
        and task.deadline < today
    )


def format_task_when(task: Task, today: date) -> str:
    dl = task.deadline
    time = ""
    due_time = getattr(task, "due_time", None)
    if due_time:
        time = f", {due_time}"
    if dl is None:
        if task.weekday is not None:
            return f"Нагадування · {WEEKDAY_LABELS[task.weekday]}"
        return "Без дедлайну"
    if dl == today:
        return f"Сьогодні{time}"
    if dl == today + timedelta(days=1):
        return f"Завтра{time}"
    return f"{dl.day} {UK_MONTHS_GEN[dl.month - 1]} {dl.year}{time}"


def format_task_when_short(task: Task, today: date) -> str:
    dl = task.deadline
    time = getattr(task, "due_time", None) or ""
    if dl is None:
        return "Без дедлайну"
    suffix = f", {time}" if time else ""
    if dl == today:
        return f"Сьогодні{suffix}" if time else "Сьогодні"
    if dl == today + timedelta(days=1):
        return f"Завтра{suffix}" if time else "Завтра"
    return f"{dl.day} {UK_MONTHS_GEN[dl.month - 1][:3]}.{suffix}"


@dataclass
class TaskWorkspaceStats:
    active: int
    overdue: int
    done: int
    today: int


@dataclass
class TaskCardVM:
    task: Task
    status: str
    status_label: str
    priority: str
    priority_label: str
    is_overdue: bool
    when_label: str
    when_short: str
    checklist_done: int
    checklist_total: int


@dataclass
class TaskListGroup:
    key: str
    label: str
    tone: str
    tasks: list[TaskCardVM]


@dataclass
class TaskKanbanColumn:
    status: str
    label: str
    tasks: list[TaskCardVM]


@dataclass
class WeekDayVM:
    date: date
    weekday_label: str
    date_label: str
    is_today: bool
    tasks: list[TaskCardVM]


@dataclass
class WeekPlanner:
    start: date
    end: date
    week_number: int
    label: str
    days: list[WeekDayVM]
    notes: str
    notes_manager_id: int | None
    total: int
    high: int
    normal: int
    low: int
    prev_start: date
    next_start: date


@dataclass
class CalendarDay:
    date: date
    in_month: bool
    is_today: bool
    tasks: list[TaskCardVM]


@dataclass
class TaskWorkspace:
    stats: TaskWorkspaceStats
    cards: list[TaskCardVM]
    list_groups: list[TaskListGroup]
    kanban: list[TaskKanbanColumn]
    week: WeekPlanner
    calendar_weeks: list[list[CalendarDay]]
    calendar_label: str
    calendar_year: int
    calendar_month: int
    selected_day: date
    selected_day_tasks: list[TaskCardVM]
    selected_day_label: str
    clients: list
    focus_manager_name: str | None = None


def _to_card(task: Task, today: date) -> TaskCardVM:
    status = workflow_status(task)
    priority = task_priority(task)
    items = list(getattr(task, "checklist_items", None) or [])
    return TaskCardVM(
        task=task,
        status=status,
        status_label=TASK_WORKFLOW_LABELS[status],
        priority=priority,
        priority_label=TASK_PRIORITY_LABELS[priority],
        is_overdue=is_overdue_task(task, today),
        when_label=format_task_when(task, today),
        when_short=format_task_when_short(task, today),
        checklist_done=sum(1 for i in items if i.is_done),
        checklist_total=len(items),
    )


def _matches_deadline_filter(task: Task, key: str | None, today: date) -> bool:
    if not key:
        return True
    dl = task.deadline
    if key == "today":
        return dl == today
    if key == "overdue":
        return is_overdue_task(task, today)
    if key == "none":
        return dl is None
    if key == "week":
        if dl is None:
            return False
        end = today + timedelta(days=7)
        return today <= dl <= end
    return True


def filter_workspace_tasks(
    tasks: list[Task],
    *,
    today: date,
    q: str | None = None,
    client_id: int | None = None,
    kind: str | None = None,
    priority: str | None = None,
    deadline_key: str | None = None,
    workflow: str | None = None,
    status_bucket: str | None = None,
) -> list[Task]:
    needle = (q or "").strip().lower()
    out: list[Task] = []
    for task in tasks:
        status = workflow_status(task)
        if client_id is not None and task.client_id != client_id:
            continue
        if kind and manager_task_kind_value(task.kind) != kind:
            continue
        if priority and task_priority(task) != priority:
            continue
        if workflow and status != workflow:
            continue
        if not _matches_deadline_filter(task, deadline_key, today):
            continue
        if status_bucket == "overdue" and not is_overdue_task(task, today):
            continue
        if status_bucket == "completed" and status != TaskWorkflowStatus.DONE.value:
            continue
        if status_bucket == "active" and status not in TASK_WORKFLOW_OPEN:
            continue
        if needle:
            hay = " ".join(
                [
                    task.title or "",
                    task.comment or "",
                    task.client.name if task.client else "",
                    task.assignee.name if task.assignee else "",
                ]
            ).lower()
            if needle not in hay:
                continue
        out.append(task)
    return out


def _list_group_key(task: Task, today: date) -> tuple[int, int, str, str]:
    if is_overdue_task(task, today):
        return 0, 0, "overdue", "Прострочені"
    dl = task.deadline
    if dl == today:
        return 1, 0, "today", "Сьогодні"
    if dl == today + timedelta(days=1):
        return 2, 0, "soon", "Завтра"
    if dl is not None:
        label = f"{dl.day} {UK_MONTHS_GEN[dl.month - 1]} {dl.year}"
        return 3, dl.toordinal(), "later", label
    if task.weekday is not None:
        return 4, task.weekday, "reminder", f"Нагадування · {WEEKDAY_LABELS[task.weekday]}"
    return 5, 0, "none", "Без дедлайну"


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def format_week_range(start: date, end: date) -> str:
    if start.month == end.month and start.year == end.year:
        return f"{start.day} – {end.day} {UK_MONTHS_GEN[start.month - 1]} {start.year}"
    if start.year == end.year:
        return (
            f"{start.day} {UK_MONTHS_GEN[start.month - 1]} – "
            f"{end.day} {UK_MONTHS_GEN[end.month - 1]} {end.year}"
        )
    return (
        f"{start.day} {UK_MONTHS_GEN[start.month - 1]} {start.year} – "
        f"{end.day} {UK_MONTHS_GEN[end.month - 1]} {end.year}"
    )


def _task_on_date(task: Task, day: date) -> bool:
    if workflow_status(task) == TaskWorkflowStatus.CANCELLED.value:
        return False
    if task.deadline == day:
        return True
    return (
        task.deadline is None
        and task.weekday is not None
        and task.weekday == day.weekday()
    )


def _build_week_planner(
    cards: list[TaskCardVM],
    *,
    today: date,
    week_start: date,
    notes: str = "",
    notes_manager_id: int | None = None,
) -> WeekPlanner:
    start = monday_of(week_start)
    end = start + timedelta(days=4)
    days: list[WeekDayVM] = []
    week_cards: list[TaskCardVM] = []
    for offset in range(5):
        day = start + timedelta(days=offset)
        day_cards = [c for c in cards if _task_on_date(c.task, day)]
        day_cards.sort(
            key=lambda c: (
                0 if c.priority == "high" else 1 if c.priority == "normal" else 2,
                c.task.created_at.timestamp() if c.task.created_at else 0,
            )
        )
        week_cards.extend(day_cards)
        days.append(
            WeekDayVM(
                date=day,
                weekday_label=UK_WEEKDAYS_FULL[offset],
                date_label=f"{day.day} {UK_MONTHS_GEN[day.month - 1]}",
                is_today=day == today,
                tasks=day_cards,
            )
        )
    return WeekPlanner(
        start=start,
        end=end,
        week_number=start.isocalendar().week,
        label=format_week_range(start, end),
        days=days,
        notes=notes,
        notes_manager_id=notes_manager_id,
        total=len(week_cards),
        high=sum(1 for c in week_cards if c.priority == "high"),
        normal=sum(1 for c in week_cards if c.priority == "normal"),
        low=sum(1 for c in week_cards if c.priority == "low"),
        prev_start=start - timedelta(days=7),
        next_start=start + timedelta(days=7),
    )


def build_task_workspace(
    tasks: list[Task],
    *,
    today: date,
    calendar_year: int,
    calendar_month: int,
    selected_day: date | None = None,
    focus_manager: User | None = None,
    clients: list | None = None,
    status_bucket: str | None = None,
    week_start: date | None = None,
    week_notes: str = "",
    notes_manager_id: int | None = None,
) -> TaskWorkspace:
    cards = [_to_card(t, today) for t in tasks]
    stats = TaskWorkspaceStats(
        active=sum(1 for t in tasks if is_open_task(t)),
        overdue=sum(1 for t in tasks if is_overdue_task(t, today)),
        done=sum(1 for t in tasks if workflow_status(t) == TaskWorkflowStatus.DONE.value),
        today=sum(
            1
            for t in tasks
            if is_open_task(t) and t.deadline == today
        ),
    )

    list_source = cards
    if status_bucket == "overdue":
        list_source = [c for c in cards if c.is_overdue]
    elif status_bucket == "completed":
        list_source = [c for c in cards if c.status == TaskWorkflowStatus.DONE.value]
    elif status_bucket == "active":
        list_source = [c for c in cards if c.status in TASK_WORKFLOW_OPEN]

    groups_map: dict[tuple[int, int, str, str], list[TaskCardVM]] = {}
    for card in list_source:
        key = _list_group_key(card.task, today)
        groups_map.setdefault(key, []).append(card)
    list_groups: list[TaskListGroup] = []
    for (tier, sub, tone, label), items in sorted(groups_map.items(), key=lambda x: (x[0][0], x[0][1])):
        items.sort(
            key=lambda c: (
                c.task.deadline or date.max,
                c.task.due_time or "99:99",
                -(c.task.created_at.timestamp() if c.task.created_at else 0),
            )
        )
        list_groups.append(TaskListGroup(key=f"{tier}:{sub}:{tone}", label=label, tone=tone, tasks=items))

    by_status: dict[str, list[TaskCardVM]] = {key: [] for key, _ in WORKFLOW_COLUMNS}
    for card in cards:
        by_status.setdefault(card.status, []).append(card)
    kanban = [
        TaskKanbanColumn(status=key, label=label, tasks=by_status.get(key, []))
        for key, label in WORKFLOW_COLUMNS
    ]

    week_planner = _build_week_planner(
        cards,
        today=today,
        week_start=week_start or today,
        notes=week_notes,
        notes_manager_id=notes_manager_id,
    )

    cal = calendar.Calendar(firstweekday=0)
    selected = selected_day or today
    weeks: list[list[CalendarDay]] = []
    by_day: dict[date, list[TaskCardVM]] = {}
    for card in cards:
        task = card.task
        if not getattr(task, "add_to_calendar", True):
            continue
        if task.deadline is None:
            continue
        by_day.setdefault(task.deadline, []).append(card)

    for cal_week in cal.monthdatescalendar(calendar_year, calendar_month):
        row: list[CalendarDay] = []
        for day in cal_week:
            row.append(
                CalendarDay(
                    date=day,
                    in_month=day.month == calendar_month,
                    is_today=day == today,
                    tasks=by_day.get(day, []),
                )
            )
        weeks.append(row)

    day_tasks = by_day.get(selected, [])
    selected_label = f"{selected.day} {UK_MONTHS_GEN[selected.month - 1]}"
    calendar_label = f"{UK_MONTHS_NOM[calendar_month - 1]} {calendar_year}"

    return TaskWorkspace(
        stats=stats,
        cards=cards,
        list_groups=list_groups,
        kanban=kanban,
        week=week_planner,
        calendar_weeks=weeks,
        calendar_label=calendar_label,
        calendar_year=calendar_year,
        calendar_month=calendar_month,
        selected_day=selected,
        selected_day_tasks=day_tasks,
        selected_day_label=selected_label,
        clients=clients or [],
        focus_manager_name=focus_manager.name if focus_manager else None,
    )


def apply_workflow_status(task: Task, status: str) -> None:
    normalized = normalize_task_workflow_status(
        status,
        completed=False,
        cancelled=False,
    )
    if normalized not in TASK_WORKFLOW_LABELS:
        normalized = TaskWorkflowStatus.NEW.value
    task.status = normalized
    stamp = datetime.now(timezone.utc)
    if normalized == TaskWorkflowStatus.DONE.value:
        task.completed_at = task.completed_at or stamp
        task.deleted_at = None
    elif normalized == TaskWorkflowStatus.CANCELLED.value:
        task.deleted_at = task.deleted_at or stamp
        task.completed_at = None
    else:
        task.completed_at = None
        task.deleted_at = None
