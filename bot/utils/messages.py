from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, Message


async def edit_or_replace_text(
    message: Message,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> Message:
    """Редагує текст або замінює повідомлення (фото, документ тощо) новим текстом."""
    if message.text is not None:
        try:
            return await message.edit_text(text, reply_markup=reply_markup)
        except TelegramBadRequest:
            pass

    try:
        await message.delete()
    except TelegramBadRequest:
        pass

    return await message.answer(text, reply_markup=reply_markup)
