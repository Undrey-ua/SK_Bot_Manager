from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.utils.roles import is_sales_manager
from database.models import VISIT_TYPE_LABELS, Client, ManagerRegion, User, VisitType


def main_menu_keyboard(user: User | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if user is not None and is_sales_manager(user):
        builder.row(
            InlineKeyboardButton(text="💰 Додати продаж", callback_data="sale:new"),
            InlineKeyboardButton(text="📦 Резерви", callback_data="reserve:hub"),
        )
        return builder.as_markup()

    builder.row(
        InlineKeyboardButton(text="👤 Клієнти", callback_data="clients:hub"),
        InlineKeyboardButton(text="➕ Новий візит", callback_data="visit:new"),
    )
    builder.row(
        InlineKeyboardButton(text="💰 Додати продаж", callback_data="sale:new"),
        InlineKeyboardButton(text="📦 Резерви", callback_data="reserve:hub"),
    )
    builder.row(
        InlineKeyboardButton(text="📝 Мої завдання", callback_data="tasks:hub"),
    )
    return builder.as_markup()


def visit_regions_keyboard(regions: list[ManagerRegion]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for region in regions:
        builder.row(
            InlineKeyboardButton(
                text=region.name,
                callback_data=f"visit:pick_region:{region.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="◀️ Меню", callback_data="menu:main"))
    return builder.as_markup()


def visit_clients_keyboard(clients: list[Client]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for client in clients:
        builder.row(
            InlineKeyboardButton(
                text=client.name[:60],
                callback_data=f"visit:client:{client.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="◀️ Області", callback_data="visit:back:regions"))
    builder.row(InlineKeyboardButton(text="◀️ Меню", callback_data="menu:main"))
    return builder.as_markup()


def visit_type_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for visit_type in VisitType:
        builder.row(
            InlineKeyboardButton(
                text=VISIT_TYPE_LABELS[visit_type],
                callback_data=f"visit:type:{visit_type.value}",
            )
        )
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="visit:back:client"))
    return builder.as_markup()


def tasks_keyboard(
    selected: set[str],
    task_types: list[tuple[str, str]],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for code, label in task_types:
        checked = "✅" if code in selected else "⬜"
        builder.row(
            InlineKeyboardButton(
                text=f"{checked} {label}",
                callback_data=f"visit:task:{code}",
            )
        )
    builder.row(
        InlineKeyboardButton(text="➡️ Далі", callback_data="visit:tasks:done"),
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="visit:back:type"),
    )
    return builder.as_markup()


def photos_keyboard(photo_count: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    finish_label = (
        f"✅ Завершити ({photo_count} фото)"
        if photo_count
        else "✅ Завершити без фото"
    )
    builder.row(
        InlineKeyboardButton(
            text=finish_label,
            callback_data="visit:photos:done",
        )
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="visit:back:comment"),
    )
    return builder.as_markup()


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🏠 Головне меню", callback_data="menu:main"))
    return builder.as_markup()
