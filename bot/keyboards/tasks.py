from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.models import Task, User

WEEKDAYS_UA = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]


def tasks_hub_keyboard(*, for_leader: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    add_label = "➕ Нова задача" if for_leader else "➕ Додати задачу"
    builder.row(InlineKeyboardButton(text=add_label, callback_data="tasks:new"))
    builder.row(InlineKeyboardButton(text="📋 Усі", callback_data="tasks:list:all"))
    builder.row(
        InlineKeyboardButton(text="Пн", callback_data="tasks:list:0"),
        InlineKeyboardButton(text="Вт", callback_data="tasks:list:1"),
        InlineKeyboardButton(text="Ср", callback_data="tasks:list:2"),
        InlineKeyboardButton(text="Чт", callback_data="tasks:list:3"),
        InlineKeyboardButton(text="Пт", callback_data="tasks:list:4"),
    )
    builder.row(InlineKeyboardButton(text="◀️ Меню", callback_data="menu:main"))
    return builder.as_markup()


def tasks_list_keyboard(tasks: list[Task]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for t in tasks[:50]:
        dl = f" до {t.deadline.isoformat()}" if t.deadline else ""
        wd = f" ({WEEKDAYS_UA[t.weekday]})" if t.weekday is not None else ""
        builder.row(
            InlineKeyboardButton(
                text=f"#{t.id} {t.title[:28]}{wd}{dl}",
                callback_data=f"tasks:show:{t.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="tasks:hub"))
    return builder.as_markup()


def task_actions_keyboard(task_id: int, *, is_overdue: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Виконано", callback_data=f"tasks:done:{task_id}"))
    if is_overdue:
        builder.row(InlineKeyboardButton(text="⏩ Продовжити дедлайн", callback_data=f"tasks:extend:{task_id}"))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="tasks:hub"))
    return builder.as_markup()


def task_assignees_keyboard(managers: list[User]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for manager in managers:
        builder.row(
            InlineKeyboardButton(
                text=manager.name[:60],
                callback_data=f"tasks:assignee:{manager.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="Всім", callback_data="tasks:assignee:all"))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="tasks:hub"))
    return builder.as_markup()


def weekday_pick_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Пн", callback_data="tasks:weekday:0"),
        InlineKeyboardButton(text="Вт", callback_data="tasks:weekday:1"),
        InlineKeyboardButton(text="Ср", callback_data="tasks:weekday:2"),
        InlineKeyboardButton(text="Чт", callback_data="tasks:weekday:3"),
        InlineKeyboardButton(text="Пт", callback_data="tasks:weekday:4"),
    )
    builder.row(InlineKeyboardButton(text="⏭ Без дня", callback_data="tasks:weekday:skip"))
    return builder.as_markup()

