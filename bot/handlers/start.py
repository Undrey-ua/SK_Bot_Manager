from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from bot.keyboards.inline import main_menu_keyboard
from bot.utils.formatting import user_first_name
from bot.utils.messages import edit_or_replace_text
from database.models import User

logger = logging.getLogger(__name__)
router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, db_user: User | None) -> None:
    logger.info("/start from telegram_id=%s", message.from_user.id if message.from_user else None)
    if db_user is None:
        await message.answer(
            "👋 Вітаємо!\n\n"
            "Ваш Telegram ID ще не активовано.\n"
            "Надішліть адміністратору свій ID:\n"
            f"<code>{message.from_user.id if message.from_user else '—'}</code>"
        )
        return

    name = user_first_name(db_user.name)
    await message.answer(
        f"👋 Привіт, <b>{name}</b>!\n\n"
        "CRM для регіональних менеджерів.\n"
        "Оберіть дію в меню:",
        reply_markup=main_menu_keyboard(db_user),
    )


@router.callback_query(F.data == "menu:main")
async def show_main_menu(callback: CallbackQuery, db_user: User) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await edit_or_replace_text(
        callback.message,
        f"🏠 Головне меню\n\nПривіт, <b>{user_first_name(db_user.name)}</b>!",
        reply_markup=main_menu_keyboard(db_user),
    )
