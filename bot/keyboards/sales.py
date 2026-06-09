from datetime import date

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.utils.client_brands import brand_button_label
from bot.utils.dates import UK_MONTHS
from database.models import Brand, Client, ManagerRegion


def sale_regions_keyboard(regions: list[ManagerRegion]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for region in regions:
        builder.row(
            InlineKeyboardButton(
                text=region.name,
                callback_data=f"sale:pick_region:{region.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="◀️ Меню", callback_data="menu:main"))
    return builder.as_markup()


def sale_clients_keyboard(clients: list[Client]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for client in clients:
        builder.row(
            InlineKeyboardButton(
                text=client.name[:60],
                callback_data=f"sale:client:{client.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="◀️ Області", callback_data="sale:back:regions"))
    builder.row(InlineKeyboardButton(text="◀️ Меню", callback_data="menu:main"))
    return builder.as_markup()


def sale_brands_keyboard(brands: list[Brand]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for brand in brands:
        builder.row(
            InlineKeyboardButton(
                text=brand_button_label(brand)[:60],
                callback_data=f"sale:brand:{brand.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="sale:back:client"))
    return builder.as_markup()


def _months_available(year: int, *, today: date | None = None) -> list[tuple[int, str]]:
    today = today or date.today()
    if year > today.year:
        return []
    if year < today.year:
        return UK_MONTHS
    return [(m, label) for m, label in UK_MONTHS if m <= today.month]


def sale_period_keyboard(year: int, *, today: date | None = None) -> InlineKeyboardMarkup:
    today = today or date.today()
    builder = InlineKeyboardBuilder()
    months = _months_available(year, today=today)
    row: list[InlineKeyboardButton] = []
    for month_num, label in months:
        row.append(
            InlineKeyboardButton(
                text=label[:12],
                callback_data=f"sale:period:{year}:{month_num}",
            )
        )
        if len(row) == 3:
            builder.row(*row)
            row = []
    if row:
        builder.row(*row)

    nav: list[InlineKeyboardButton] = []
    if year > today.year - 5:
        nav.append(
            InlineKeyboardButton(text=f"◀ {year - 1}", callback_data=f"sale:year:{year - 1}")
        )
    nav.append(InlineKeyboardButton(text=str(year), callback_data="sale:year:noop"))
    if year < today.year:
        nav.append(
            InlineKeyboardButton(text=f"{year + 1} ▶", callback_data=f"sale:year:{year + 1}")
        )
    builder.row(*nav)
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="sale:back:comment"))
    return builder.as_markup()


def sale_skip_comment_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⏭ Без коментаря", callback_data="sale:comment:skip")
    )
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="sale:back:quantity"))
    builder.row(InlineKeyboardButton(text="◀️ До брендів", callback_data="sale:back:brand"))
    return builder.as_markup()
