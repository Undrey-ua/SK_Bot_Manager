from __future__ import annotations

import logging
from decimal import Decimal

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.keyboards.inline import back_to_menu_keyboard
from database.models import User

logger = logging.getLogger(__name__)


def format_new_reserve_message(
    *,
    reserve_id: int,
    manager_name: str,
    client_name: str,
    region_name: str,
    material: str,
    quantity: Decimal,
    expires_at,
) -> str:
    return (
        f"📦 <b>Новий резерв</b>\n\n"
        f"{manager_name} поставив резерв #{reserve_id}:\n"
        f"{client_name} · {region_name}\n"
        f"{material} — {quantity} кв. м\n"
        f"Діє до: {expires_at.strftime('%Y-%m-%d %H:%M')} UTC"
    )


async def broadcast_new_reserve(
    *,
    bot_token: str,
    users: list[User],
    reserve_id: int,
    manager_name: str,
    client_name: str,
    region_name: str,
    material: str,
    quantity: Decimal,
    expires_at,
) -> None:
    if not bot_token.strip():
        return

    text = format_new_reserve_message(
        reserve_id=reserve_id,
        manager_name=manager_name,
        client_name=client_name,
        region_name=region_name,
        material=material,
        quantity=quantity,
        expires_at=expires_at,
    )
    bot = Bot(
        token=bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        for user in users:
            try:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=text,
                    reply_markup=back_to_menu_keyboard(),
                )
            except Exception:
                logger.exception("Failed to notify user %s about reserve", user.telegram_id)
    finally:
        await bot.session.close()
