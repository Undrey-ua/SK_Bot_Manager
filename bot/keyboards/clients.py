from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.utils.roles import can_manage_stand_catalog, is_sales_manager
from database.models import Client, ManagerRegion, Stand, User


def clients_hub_keyboard(user: User) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📋 Список клієнтів", callback_data="clients:list"),
    )
    builder.row(
        InlineKeyboardButton(text="➕ Новий клієнт", callback_data="client:add"),
    )
    builder.row(
        InlineKeyboardButton(text="🗺 Мої області", callback_data="regions:list"),
    )
    if can_manage_stand_catalog(user):
        builder.row(
            InlineKeyboardButton(text="🏷 Каталог стендів", callback_data="admin:stands"),
        )
    builder.row(InlineKeyboardButton(text="◀️ Меню", callback_data="menu:main"))
    return builder.as_markup()


def clients_filter_regions_keyboard(
    regions: list[ManagerRegion],
    *,
    source: str = "list",
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for region in regions:
        builder.row(
            InlineKeyboardButton(
                text=region.name,
                callback_data=f"clients:show:{region.id}:{source}",
            )
        )
    back = "regions:list" if source == "regions" else "clients:list"
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data=back))
    builder.row(InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main"))
    return builder.as_markup()


def client_list_keyboard(
    clients: list[Client],
    region_id: int,
    *,
    source: str = "list",
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for client in clients:
        prefix = "⭐ " if client.is_potential else ""
        builder.row(
            InlineKeyboardButton(
                text=f"{prefix}{client.name[:58]}",
                callback_data=f"client:view:{client.id}:{region_id}:{source}",
            )
        )
    back = "regions:list" if source == "regions" else "clients:list"
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data=back))
    return builder.as_markup()


def client_card_keyboard(
    client_id: int,
    region_id: int,
    *,
    source: str = "list",
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✏️ Редагувати",
            callback_data=f"client:edit:{client_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="◀️ До списку",
            callback_data=f"clients:show:{region_id}:{source}",
        )
    )
    builder.row(InlineKeyboardButton(text="👤 Клієнти", callback_data="clients:hub"))
    return builder.as_markup()


def region_pick_keyboard(
    regions: list[ManagerRegion],
    *,
    back_callback: str = "clients:hub",
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for region in regions:
        builder.row(
            InlineKeyboardButton(
                text=region.name,
                callback_data=f"client:region:{region.id}",
            )
        )
    builder.row(
        InlineKeyboardButton(text="➕ Нова область", callback_data="client:region:new"),
    )
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data=back_callback))
    return builder.as_markup()


def stands_toggle_keyboard(
    stands: list[Stand],
    selected: set[int],
    *,
    back_callback: str = "client:back:comment",
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for stand in stands:
        checked = "✅" if stand.id in selected else "⬜"
        builder.row(
            InlineKeyboardButton(
                text=f"{checked} {stand.name}",
                callback_data=f"client:stand:{stand.id}",
            )
        )
    builder.row(
        InlineKeyboardButton(text="➡️ Далі", callback_data="client:stands:done"),
    )
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data=back_callback))
    return builder.as_markup()


def client_form_confirm_keyboard(*, edit: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    save_data = "client:save:edit" if edit else "client:save:new"
    builder.row(InlineKeyboardButton(text="✅ Зберегти", callback_data=save_data))
    builder.row(InlineKeyboardButton(text="◀️ Скасувати", callback_data="clients:hub"))
    return builder.as_markup()


def admin_stands_keyboard(stands: list[Stand]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for stand in stands:
        mark = "✅" if stand.is_active else "⬜"
        builder.row(
            InlineKeyboardButton(
                text=f"{mark} {stand.name}",
                callback_data=f"admin:stand:toggle:{stand.id}",
            )
        )
    builder.row(
        InlineKeyboardButton(text="➕ Додати стенд", callback_data="admin:stand:add"),
    )
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="clients:hub"))
    return builder.as_markup()
