from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone

from aiogram import Bot

from bot.container import Container
from bot.keyboards.reserves import reserve_owner_actions_keyboard
from bot.keyboards.tasks import WEEKDAYS_UA, tasks_hub_keyboard
from database.models import User

logger = logging.getLogger(__name__)


async def _notify_expired_reserves(bot: Bot, container: Container) -> None:
    async with container.session_factory() as session:
        reserve_service = container.reserve_service(session)
        user_service = container.user_service(session)
        expired = await reserve_service.list_expired_needing_notify()
        for r in expired:
            try:
                await bot.send_message(
                    chat_id=r.manager.telegram_id,
                    text=(
                        f"⏰ <b>Резерв #{r.id} закінчився</b>\n\n"
                        f"{r.client.name} · {r.region.name}\n"
                        f"{r.material} — {r.quantity} кв. м\n\n"
                        "Продовжити ще на 7 днів або скасувати?"
                    ),
                    reply_markup=reserve_owner_actions_keyboard(r.id),
                )
                await reserve_service.mark_expiry_notified(r.id)
                await session.commit()
            except Exception:
                logger.exception("Failed to notify reserve expiry %s", r.id)


async def _notify_weekday_tasks(bot: Bot, container: Container) -> None:
    now = datetime.now(timezone.utc)
    # Щоб не спамити — надсилаємо тільки вранці (06:00-06:20 UTC ≈ 09:00 Київ)
    if not (now.hour == 6 and now.minute < 20):
        return
    today = date.today()
    weekday = today.weekday()
    async with container.session_factory() as session:
        task_service = container.task_service(session)
        user_service = container.user_service(session)
        tasks = await task_service.list_due_weekday(weekday, day=today)
        if not tasks:
            return
        # групуємо по менеджеру
        by_user: dict[int, list] = {}
        for t in tasks:
            by_user.setdefault(t.assignee_id, []).append(t)
        for assignee_id, items in by_user.items():
            user = await session.get(User, assignee_id)
            if not user:
                continue
            lines = [f"• #{t.id} {t.title}" for t in items[:20]]
            text = (
                f"🔔 <b>Нагадування на сьогодні ({WEEKDAYS_UA[weekday]})</b>\n\n"
                + "\n".join(lines)
            )
            try:
                await bot.send_message(user.telegram_id, text, reply_markup=tasks_hub_keyboard())
                for t in items:
                    await task_service.mark_reminded(t.id, today)
                await session.commit()
            except Exception:
                logger.exception("Failed to notify tasks for user %s", user.telegram_id)


async def notifications_loop(bot: Bot, container: Container) -> None:
    while True:
        try:
            await _notify_expired_reserves(bot, container)
            await _notify_weekday_tasks(bot, container)
        except Exception:
            logger.exception("notifications_loop tick failed")
        await asyncio.sleep(600)  # 10 хв

