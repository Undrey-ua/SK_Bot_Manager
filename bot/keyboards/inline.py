from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.models import TASK_LABELS, VISIT_TYPE_LABELS, Client, TaskType, VisitType


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📋 Мої клієнти", callback_data="clients:list"),
    )
    builder.row(
        InlineKeyboardButton(text="➕ Новий візит", callback_data="visit:new"),
    )
    return builder.as_markup()


def clients_keyboard(clients: list[Client]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for client in clients:
        label = client.name
        if client.district:
            label = f"{client.name} ({client.district})"
        builder.row(
            InlineKeyboardButton(
                text=label,
                callback_data=f"visit:client:{client.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main"))
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


def tasks_keyboard(selected: set[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for task in TaskType:
        checked = "✅" if task.value in selected else "⬜"
        builder.row(
            InlineKeyboardButton(
                text=f"{checked} {TASK_LABELS[task]}",
                callback_data=f"visit:task:{task.value}",
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
    builder.row(
        InlineKeyboardButton(
            text=f"✅ Завершити ({photo_count} фото)",
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
