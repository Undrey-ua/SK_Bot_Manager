from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.keyboards.tasks import WEEKDAYS_UA, tasks_hub_keyboard
from database.models import MANAGER_TASK_KIND_LABELS, ManagerTaskKind, Task, User

logger = logging.getLogger(__name__)

WEEKDAY_NAMES_UA = [
    "Понеділок",
    "Вівторок",
    "Середа",
    "Четвер",
    "П'ятниця",
    "Субота",
    "Неділя",
]


def format_new_task_assigned_message(
    task: Task,
    *,
    creator_name: str,
) -> str:
    dl = task.deadline.strftime("%d.%m.%Y") if task.deadline else "—"
    if task.weekday is not None:
        wd = WEEKDAY_NAMES_UA[task.weekday]
        wd_short = WEEKDAYS_UA[task.weekday]
        wd_line = f"{wd} ({wd_short})"
    else:
        wd_line = "—"
    comment = task.comment.strip() if task.comment else "—"
    try:
        kind_label = MANAGER_TASK_KIND_LABELS[ManagerTaskKind(task.kind)]
    except (ValueError, KeyError, AttributeError):
        kind_label = MANAGER_TASK_KIND_LABELS[ManagerTaskKind.GENERAL]
    return (
        f"📋 <b>Нове завдання від {creator_name}</b>\n\n"
        f"{task.title}\n\n"
        f"Тип: {kind_label}\n"
        f"Дедлайн: {dl}\n"
        f"День нагадування: {wd_line}\n"
        f"Коментар: {comment}"
    )


def should_notify_task_assigned(task: Task) -> bool:
    """Сповіщати лише коли задачу призначив інший користувач (керівник → менеджер)."""
    return task.assignee_id != task.created_by_id


async def notify_task_assigned(
    *,
    bot_token: str,
    task: Task,
    assignee: User,
    creator: User | None,
    force: bool = False,
) -> None:
    if not force and not should_notify_task_assigned(task):
        logger.info(
            "Skip task #%s notify: assignee_id=%s equals created_by_id=%s",
            task.id,
            task.assignee_id,
            task.created_by_id,
        )
        return
    creator_name = creator.name if creator and creator.name else "керівника"
    text = format_new_task_assigned_message(task, creator_name=creator_name)
    bot = Bot(
        token=bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        await bot.send_message(
            assignee.telegram_id,
            text,
            reply_markup=tasks_hub_keyboard(),
        )
        logger.info(
            "Notified user %s about new task #%s",
            assignee.telegram_id,
            task.id,
        )
    except Exception:
        logger.exception(
            "Failed to notify assignee %s about task #%s",
            assignee.telegram_id,
            task.id,
        )
    finally:
        await bot.session.close()
