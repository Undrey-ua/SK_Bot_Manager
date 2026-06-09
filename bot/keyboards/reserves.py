from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.models import Client, ManagerRegion, Reserve


def reserves_hub_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Додати резерв", callback_data="reserve:new"))
    builder.row(InlineKeyboardButton(text="📋 Активні резерви", callback_data="reserve:list"))
    builder.row(InlineKeyboardButton(text="◀️ Меню", callback_data="menu:main"))
    return builder.as_markup()


def reserves_regions_keyboard(regions: list[ManagerRegion]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for region in regions:
        builder.row(
            InlineKeyboardButton(
                text=region.name,
                callback_data=f"reserve:pick_region:{region.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="reserve:hub"))
    return builder.as_markup()


def reserves_clients_keyboard(clients: list[Client]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for client in clients:
        builder.row(
            InlineKeyboardButton(
                text=client.name[:60],
                callback_data=f"reserve:client:{client.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="◀️ Області", callback_data="reserve:back:regions"))
    return builder.as_markup()


def reserves_list_keyboard(items: list[Reserve]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for r in items[:50]:
        builder.row(
            InlineKeyboardButton(
                text=f"#{r.id} {r.client.name[:32]} · {r.material[:18]}",
                callback_data=f"reserve:show:{r.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="reserve:hub"))
    return builder.as_markup()


def reserve_owner_actions_keyboard(reserve_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔁 Продовжити на 7 днів", callback_data=f"reserve:extend:{reserve_id}"))
    builder.row(InlineKeyboardButton(text="❌ Скасувати", callback_data=f"reserve:cancel:{reserve_id}"))
    builder.row(InlineKeyboardButton(text="💰 Продаж", callback_data=f"reserve:sale:{reserve_id}"))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="reserve:list"))
    return builder.as_markup()


def reserve_view_keyboard(reserve_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="reserve:list"))
    return builder.as_markup()

