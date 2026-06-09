from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from bot.container import build_container
from bot.handlers import setup_routers
from bot.jobs import notifications_loop
from bot.middlewares import (
    AuthMiddleware,
    DbSessionMiddleware,
    LoggingMiddleware,
    RoleGuardMiddleware,
)
from config.settings import get_settings
from database.models import Base
from utils.logging import setup_logging

logger = logging.getLogger(__name__)


async def init_db(container) -> None:
    async with container.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with container.session_factory() as session:
        stand_service = container.stand_service(session)
        await stand_service.seed_defaults()
        await session.commit()

    logger.info("Database tables verified")


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    container = build_container(settings)
    await init_db(container)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.update.middleware(LoggingMiddleware())
    dp.update.middleware(DbSessionMiddleware(container))
    dp.update.middleware(AuthMiddleware())
    dp.update.middleware(RoleGuardMiddleware())
    dp.include_router(setup_routers())

    notify_task = asyncio.create_task(notifications_loop(bot, container))

    @dp.errors()
    async def on_error(event: ErrorEvent) -> None:
        logger.exception("Unhandled error", exc_info=event.exception)
        update = event.update
        if update.callback_query:
            try:
                await update.callback_query.answer(
                    "Сталася помилка. Спробуйте ще раз.",
                    show_alert=True,
                )
            except Exception:
                pass

    me = await bot.get_me()
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Bot starting as @%s (id=%s)...", me.username, me.id)
    try:
        await dp.start_polling(bot)
    finally:
        notify_task.cancel()
        await container.engine.dispose()
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
