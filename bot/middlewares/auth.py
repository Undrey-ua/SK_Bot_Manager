import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from database.models import User

logger = logging.getLogger(__name__)

PUBLIC_COMMANDS = {"/start"}


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_service = data["user_service"]
        telegram_user = data.get("event_from_user")

        if telegram_user is None:
            return await handler(event, data)

        db_user = await user_service.get_by_telegram_id(telegram_user.id)
        data["db_user"] = db_user

        if db_user is not None:
            return await handler(event, data)

        if self._is_public(event):
            return await handler(event, data)

        await self._deny_access(event)
        return None

    @staticmethod
    def _is_public(event: TelegramObject) -> bool:
        if isinstance(event, Message) and event.text:
            command = event.text.split()[0].split("@")[0]
            return command in PUBLIC_COMMANDS
        return False

    @staticmethod
    async def _deny_access(event: TelegramObject) -> None:
        text = (
            "⛔ Доступ заборонено.\n"
            "Зверніться до адміністратора для активації облікового запису."
        )
        if isinstance(event, Message):
            await event.answer(text)
        elif isinstance(event, CallbackQuery) and event.message:
            await event.answer("Доступ заборонено", show_alert=True)
            await event.message.answer(text)
