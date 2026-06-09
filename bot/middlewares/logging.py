import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.text:
            user = event.from_user
            logger.info(
                "Message from %s (%s): %s",
                user.full_name if user else "?",
                user.id if user else "?",
                event.text[:80],
            )
        elif isinstance(event, CallbackQuery):
            user = event.from_user
            logger.info(
                "Callback from %s (%s): %s",
                user.full_name if user else "?",
                user.id if user else "?",
                event.data,
            )
        try:
            return await handler(event, data)
        except Exception:
            logger.exception("Handler error")
            raise
