from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from database.models import Task, User
from web.utils import WEEKDAY_LABELS, manager_task_kind_value


@dataclass
class TaskBoardStats:
    active: int
    overdue: int
    completed: int
    deleted: int


@dataclass(frozen=True)
class TaskBoardItem:
    task: Task
    status: str  # active | completed | deleted
    is_overdue: bool


@dataclass(frozen=True)
class TaskDayGroup:
    key: str
    label: str
    sort_tier: int
    sort_sub: int
    tasks: list[TaskBoardItem]


@dataclass(frozen=True)
class TaskManagerSection:
    manager: User
    active_count: int
    overdue_count: int
    visible_count: int
    day_groups: list[TaskDayGroup]
    archive: list[TaskBoardItem]


def task_status(task: Task) -> str:
    if task.deleted_at is not None:
        return "deleted"
    if task.completed_at is not None:
        return "completed"
    return "active"


def _schedule_group(task: Task, today: date) -> tuple[int, int, str]:
    """Повертає (tier, sub, label) для групування активних задач."""
    dl = task.deadline
    if dl is not None:
        if dl < today:
            return 0, dl.toordinal(), "Прострочені"
        if dl == today:
            return 1, 0, "Сьогодні"
        if dl == today + timedelta(days=1):
            return 2, dl.toordinal(), "Завтра"
        wd = WEEKDAY_LABELS[dl.weekday()]
        return 3, dl.toordinal(), f"{dl.strftime('%d.%m.%Y')} · {wd}"

    if task.weekday is not None:
        return 4, task.weekday, f"Нагадування · {WEEKDAY_LABELS[task.weekday]}"

    return 5, 0, "Без дати"


def _board_item(task: Task, today: date) -> TaskBoardItem:
    status = task_status(task)
    overdue = (
        status == "active"
        and task.deadline is not None
        and task.deadline < today
    )
    return TaskBoardItem(task=task, status=status, is_overdue=overdue)


TASK_STATUS_ACTIVE = "active"
TASK_STATUS_OVERDUE = "overdue"
TASK_STATUS_COMPLETED = "completed"


def build_tasks_board(
    tasks: list[Task],
    managers: list[User],
    *,
    today: date | None = None,
    manager_id: int | None = None,
    show_completed: bool = False,
    status_filter: str = TASK_STATUS_ACTIVE,
    kind_filter: str | None = None,
) -> tuple[TaskBoardStats, list[TaskManagerSection]]:
    today = today or date.today()

    if kind_filter:
        tasks = [t for t in tasks if manager_task_kind_value(t.kind) == kind_filter]

    if manager_id is not None:
        managers = [m for m in managers if m.id == manager_id]

    by_assignee: dict[int, list[Task]] = {}
    for t in tasks:
        by_assignee.setdefault(t.assignee_id, []).append(t)

    stats = TaskBoardStats(active=0, overdue=0, completed=0, deleted=0)
    sections: list[TaskManagerSection] = []

    for manager in managers:
        manager_tasks = by_assignee.get(manager.id, [])
        if not manager_tasks and manager_id is None:
            continue

        active_items: list[TaskBoardItem] = []
        archive_items: list[TaskBoardItem] = []

        for task in manager_tasks:
            item = _board_item(task, today)
            if item.status == "active":
                stats.active += 1
                if item.is_overdue:
                    stats.overdue += 1
                active_items.append(item)
            else:
                if item.status == "completed":
                    stats.completed += 1
                else:
                    stats.deleted += 1
                archive_items.append(item)

        display_active = active_items
        display_archive = archive_items
        if status_filter == TASK_STATUS_OVERDUE:
            display_active = [i for i in active_items if i.is_overdue]
            display_archive = []
        elif status_filter == TASK_STATUS_COMPLETED:
            display_active = []
            display_archive = [i for i in archive_items if i.status == "completed"]
            if show_completed:
                display_archive = [
                    i for i in archive_items if i.status in ("completed", "deleted")
                ]
        elif not show_completed:
            display_archive = []

        if not display_active and not display_archive:
            if manager_id is not None:
                sections.append(
                    TaskManagerSection(
                        manager=manager,
                        active_count=0,
                        overdue_count=0,
                        visible_count=0,
                        day_groups=[],
                        archive=[],
                    )
                )
            continue

        groups_map: dict[tuple[int, int, str], list[TaskBoardItem]] = {}
        for item in display_active:
            tier, sub, label = _schedule_group(item.task, today)
            key = (tier, sub, label)
            groups_map.setdefault(key, []).append(item)

        day_groups: list[TaskDayGroup] = []
        for (tier, sub, label), items in sorted(groups_map.items(), key=lambda x: x[0]):
            items.sort(
                key=lambda i: (
                    i.task.deadline or date.max,
                    -(i.task.created_at.timestamp() if i.task.created_at else 0),
                ),
            )
            day_groups.append(
                TaskDayGroup(
                    key=f"{tier}:{sub}:{label}",
                    label=label,
                    sort_tier=tier,
                    sort_sub=sub,
                    tasks=items,
                )
            )

        archive_items.sort(
            key=lambda i: (
                i.task.completed_at or i.task.deleted_at or i.task.created_at,
            ),
            reverse=True,
        )

        overdue_count = sum(1 for i in active_items if i.is_overdue)
        visible_count = sum(len(g.tasks) for g in day_groups) + len(display_archive)
        sections.append(
            TaskManagerSection(
                manager=manager,
                active_count=len(active_items),
                overdue_count=overdue_count,
                visible_count=visible_count,
                day_groups=day_groups,
                archive=display_archive,
            )
        )

    if status_filter == TASK_STATUS_COMPLETED:
        sections.sort(
            key=lambda s: (-len(s.archive), (s.manager.name or "").lower()),
        )
    elif status_filter == TASK_STATUS_OVERDUE:
        sections.sort(
            key=lambda s: (
                -sum(len(g.tasks) for g in s.day_groups),
                (s.manager.name or "").lower(),
            ),
        )
    else:
        sections.sort(
            key=lambda s: (
                -s.active_count,
                -s.overdue_count,
                (s.manager.name or "").lower(),
            ),
        )
    return stats, sections
