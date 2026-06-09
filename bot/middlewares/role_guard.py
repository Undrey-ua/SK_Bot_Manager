from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject

from bot.utils.roles import callback_allowed_for_user, is_sales_manager
from database.models import User


class RoleGuardMiddleware(BaseMiddleware):
    """Обмеження callback для менеджера збуту."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        db_user: User | None = data.get("db_user")
        if (
            isinstance(event, CallbackQuery)
            and event.data
            and db_user is not None
            and is_sales_manager(db_user)
            and not callback_allowed_for_user(db_user, event.data)
        ):
            await event.answer(
                "Доступно лише: Резерви та Додати продаж",
                show_alert=True,
            )
            return None
        return await handler(event, data)
