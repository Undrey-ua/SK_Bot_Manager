import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.container import build_container
from bot.handlers import setup_routers
from bot.middlewares import AuthMiddleware, DbSessionMiddleware
from config.settings import get_settings
from database.models import Base
from utils.logging import setup_logging

logger = logging.getLogger(__name__)


async def init_db(container) -> None:
    async with container.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
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

    dp.update.middleware(DbSessionMiddleware(container))
    dp.update.middleware(AuthMiddleware())
    dp.include_router(setup_routers())

    logger.info("Bot starting...")
    try:
        await dp.start_polling(bot)
    finally:
        await container.engine.dispose()
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
