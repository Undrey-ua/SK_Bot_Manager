from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from bot.container import Container


class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, container: Container) -> None:
        self._container = container

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self._container.session_factory() as session:
            data["session"] = session
            data["container"] = self._container
            data["user_service"] = self._container.user_service(session)
            data["client_service"] = self._container.client_service(session)
            data["region_service"] = self._container.region_service(session)
            data["stand_service"] = self._container.stand_service(session)
            data["visit_service"] = self._container.visit_service(session)
            data["brand_service"] = self._container.brand_service(session)
            data["sale_service"] = self._container.sale_service(session)
            data["reserve_service"] = self._container.reserve_service(session)
            data["task_service"] = self._container.task_service(session)
            data["visit_task_type_service"] = self._container.visit_task_type_service(
                session
            )
            data["storage_service"] = self._container.storage_service
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise
