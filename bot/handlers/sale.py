import logging
from datetime import date
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.inline import back_to_menu_keyboard, main_menu_keyboard
from bot.keyboards.sales import (
    sale_brands_keyboard,
    sale_clients_keyboard,
    sale_period_keyboard,
    sale_regions_keyboard,
    sale_skip_comment_keyboard,
)
from bot.services.brand import BrandService
from bot.services.client import ClientService
from bot.services.region import RegionService
from bot.services.reserve import ReserveService
from bot.services.sale import SaleService
from bot.states.sale import SaleStates
from bot.utils.dates import UK_MONTH_BY_NUM
from bot.utils.messages import edit_or_replace_text
from bot.utils.roles import effective_manager_id
from database.models import User

logger = logging.getLogger(__name__)
router = Router(name="sale")


async def _edit_step(
    message: Message,
    text: str,
    *,
    reply_markup=None,
) -> None:
    await edit_or_replace_text(message, text, reply_markup=reply_markup)


async def _show_period_step(message: Message, state: FSMContext, *, year: int | None = None) -> None:
    data = await state.get_data()
    y = year if year is not None else int(data.get("period_year", date.today().year))
    await state.update_data(period_year=y)
    await state.set_state(SaleStates.select_period)
    await _edit_step(
        message,
        "💰 <b>Період продажу</b>\n\n"
        f"Оберіть місяць (<b>{y}</b> рік).\n"
        "Можна вказати минулі місяці поточного або минулого року.",
        reply_markup=sale_period_keyboard(y),
    )


@router.callback_query(F.data == "sale:new")
async def start_sale(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    region_service: RegionService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    regions = await region_service.list_by_manager(effective_manager_id(db_user))
    if not regions:
        await callback.message.edit_text(
            "💰 <b>Додати продаж</b>\n\n"
            "Спочатку додайте область: 👤 Клієнти → 🗺 Мої області",
            reply_markup=main_menu_keyboard(db_user),
        )
        return

    await state.clear()
    await state.set_state(SaleStates.select_region)
    await callback.message.edit_text(
        "💰 <b>Додати продаж</b>\n\nОберіть область:",
        reply_markup=sale_regions_keyboard(regions),
    )


@router.callback_query(
    SaleStates.select_region,
    F.data.startswith("sale:pick_region:"),
)
async def pick_region(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    client_service: ClientService,
    region_service: RegionService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    region_id = int(callback.data.split(":")[-1])
    region = await region_service.get_by_id(region_id)
    if region is None or region.manager_id != db_user.id:
        await callback.answer("Область не знайдена", show_alert=True)
        return

    clients = await client_service.list_by_manager_and_region(
        db_user.id, region_id, exclude_potential=True
    )
    if not clients:
        regions = await region_service.list_by_manager(db_user.id)
        await callback.message.edit_text(
            f"💰 <b>Додати продаж</b>\n\n"
            f"<b>{region.name}</b> — немає клієнтів. Оберіть іншу область:",
            reply_markup=sale_regions_keyboard(regions),
        )
        await state.set_state(SaleStates.select_region)
        return

    await state.update_data(region_id=region_id, region_name=region.name)
    await state.set_state(SaleStates.select_client)
    await callback.message.edit_text(
        f"💰 <b>Додати продаж</b>\n\n"
        f"Область: <b>{region.name}</b>\n\nОберіть клієнта:",
        reply_markup=sale_clients_keyboard(clients),
    )


@router.callback_query(
    SaleStates.select_client,
    F.data.startswith("sale:client:"),
)
async def pick_client(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    client_service: ClientService,
    brand_service: BrandService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    client_id = int(callback.data.split(":")[-1])
    client = await client_service.get_by_id(client_id)
    if client is None or client.manager_id != db_user.id:
        await callback.answer("Клієнта не знайдено", show_alert=True)
        return

    brands = await brand_service.brands_for_client_stands(client)
    if not brands:
        data = await state.get_data()
        region_id = data.get("region_id")
        if region_id:
            clients_back = await client_service.list_by_manager_and_region(
                db_user.id,
                int(region_id),
                exclude_potential=True,
            )
            kb = sale_clients_keyboard(clients_back)
        else:
            kb = back_to_menu_keyboard()
        await _edit_step(
            callback.message,
            f"💰 <b>Додати продаж</b>\n\n"
            f"Клієнт <b>{client.name}</b> — немає стендів і свотчів.\n"
            "Додайте стенди або нарізки зразків у картці клієнта.",
            reply_markup=kb,
        )
        return

    from bot.utils.client_brands import brands_from_stands, brands_from_swatches

    all_brands = await brand_service.list_active()
    stand_brand_ids = {b.id for b in brands_from_stands(client, all_brands)}
    swatch_brand_ids = {b.id for b in brands_from_swatches(client, all_brands)}
    await state.update_data(
        client_id=client.id,
        client_name=client.name,
        allowed_brand_ids=[b.id for b in brands],
        stand_brand_ids=list(stand_brand_ids),
        swatch_brand_ids=list(swatch_brand_ids),
    )
    await state.set_state(SaleStates.select_brand)
    hint = "за стендами клієнта"
    if swatch_brand_ids and not stand_brand_ids:
        hint = "за свотчами клієнта"
    elif swatch_brand_ids:
        hint = "за стендами та свотчами клієнта"
    await _edit_step(
        callback.message,
        f"Клієнт: <b>{client.name}</b>\n\n"
        f"Оберіть торгову марку ({hint}):",
        reply_markup=sale_brands_keyboard(brands),
    )


@router.callback_query(
    SaleStates.select_brand,
    F.data.startswith("sale:brand:"),
)
async def pick_brand(
    callback: CallbackQuery,
    state: FSMContext,
    brand_service: BrandService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    brand_id = int(callback.data.split(":")[-1])
    data = await state.get_data()
    allowed = set(data.get("allowed_brand_ids") or [])
    if allowed and brand_id not in allowed:
        await callback.answer("Цей бренд недоступний для клієнта", show_alert=True)
        return

    brand = await brand_service.get_by_id(brand_id)
    if brand is None:
        await callback.answer("Бренд не знайдено", show_alert=True)
        return

    from bot.utils.client_brands import brand_button_label

    label = brand_button_label(brand)
    await state.update_data(brand_id=brand.id, brand_name=label)
    await state.set_state(SaleStates.enter_quantity)
    await _edit_step(
        callback.message,
        f"Бренд: <b>{label}</b>\n\n"
        "Введіть кількість (кв. м), наприклад <code>12.5</code>:",
    )


@router.message(SaleStates.enter_quantity, F.text)
async def enter_quantity(message: Message, state: FSMContext) -> None:
    raw = message.text.strip().replace(",", ".")
    try:
        qty = Decimal(raw)
        if qty <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer("Введіть додатне число, наприклад 10 або 12.5")
        return

    await state.update_data(quantity=str(qty))
    await state.set_state(SaleStates.enter_comment)
    await message.answer(
        "Введіть коментар (необовʼязково) або натисніть «Без коментаря»:",
        reply_markup=sale_skip_comment_keyboard(),
    )


@router.message(SaleStates.enter_comment, F.text)
async def enter_comment(
    message: Message,
    state: FSMContext,
) -> None:
    comment = message.text.strip()
    if comment == "-":
        comment = None
    await state.update_data(comment=comment)
    await state.update_data(period_year=date.today().year)
    await message.answer(
        "💰 <b>Період продажу</b>\n\n"
        f"Оберіть місяць (<b>{date.today().year}</b> рік):",
        reply_markup=sale_period_keyboard(date.today().year),
    )
    await state.set_state(SaleStates.select_period)


@router.callback_query(SaleStates.enter_comment, F.data == "sale:comment:skip")
async def skip_comment(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await state.update_data(comment=None, period_year=date.today().year)
    await _show_period_step(callback.message, state)


@router.callback_query(SaleStates.select_period, F.data.startswith("sale:year:"))
async def change_period_year(callback: CallbackQuery, state: FSMContext) -> None:
    raw = callback.data.split(":")[-1]
    if raw == "noop":
        await callback.answer()
        return
    await callback.answer()
    if callback.message is None:
        return
    year = int(raw)
    today = date.today()
    if year > today.year:
        await callback.answer("Майбутній рік недоступний", show_alert=True)
        return
    if year < today.year - 5:
        await callback.answer("Занадто давній рік", show_alert=True)
        return
    await _show_period_step(callback.message, state, year=year)


@router.callback_query(SaleStates.select_period, F.data.startswith("sale:period:"))
async def pick_period(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    sale_service: SaleService,
    reserve_service: ReserveService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    parts = callback.data.split(":")
    year = int(parts[2])
    month = int(parts[3])
    sold_at = date(year, month, 1)
    await state.update_data(period_year=year, period_month=month, sold_at=sold_at.isoformat())
    await _save_sale(
        state=state,
        db_user=db_user,
        sale_service=sale_service,
        reserve_service=reserve_service,
        reply_target=callback.message,
    )


async def _save_sale(
    *,
    state: FSMContext,
    db_user: User,
    sale_service: SaleService,
    reserve_service: ReserveService,
    reply_target: Message,
) -> None:
    data = await state.get_data()
    for key in ("client_id", "brand_id", "quantity", "sold_at"):
        if not data.get(key):
            await reply_target.answer("Дані втрачено. Почніть спочатку з меню.")
            await state.clear()
            return

    sold_at = date.fromisoformat(data["sold_at"])
    comment = data.get("comment")
    if data.get("from_reserve") and data.get("reserve_id"):
        prefix = f"Продаж з резерву #{data['reserve_id']}"
        comment = f"{prefix}\n{comment}" if comment else prefix

    brand_id = int(data["brand_id"])
    stand_ids = set(data.get("stand_brand_ids") or [])
    swatch_ids = set(data.get("swatch_brand_ids") or [])
    from_swatch = brand_id in swatch_ids and brand_id not in stand_ids

    sale = await sale_service.create(
        manager_id=db_user.id,
        client_id=int(data["client_id"]),
        brand_id=brand_id,
        quantity=Decimal(data["quantity"]),
        sold_at=sold_at,
        comment=comment,
        from_swatch=from_swatch,
    )
    if data.get("from_reserve") and data.get("reserve_id"):
        marked = await reserve_service.mark_sold(int(data["reserve_id"]))
        if marked is None:
            await reply_target.answer("Продаж збережено, але резерв не закрито. Зверніться до адміністратора.")
            await state.clear()
            return
    await state.clear()
    month_label = UK_MONTH_BY_NUM.get(sold_at.month, str(sold_at.month))
    comment_line = f"\nКоментар: {comment}" if comment else ""
    await reply_target.answer(
        f"✅ <b>Продаж #{sale.id} збережено</b>\n\n"
        f"Клієнт: {data.get('client_name', '')}\n"
        f"Бренд: {data.get('brand_name', '')}\n"
        f"Кількість: {data['quantity']} кв. м\n"
        f"Період: {month_label} {sold_at.year}"
        f"{comment_line}",
        reply_markup=back_to_menu_keyboard(),
    )
    logger.info("Sale %s created by user %s", sale.id, db_user.id)


@router.callback_query(F.data == "sale:back:regions")
async def back_regions(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    region_service: RegionService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    regions = await region_service.list_by_manager(db_user.id)
    await state.set_state(SaleStates.select_region)
    await _edit_step(
        callback.message,
        "💰 <b>Додати продаж</b>\n\nОберіть область:",
        reply_markup=sale_regions_keyboard(regions),
    )


@router.callback_query(F.data == "sale:back:client")
async def back_client(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    client_service: ClientService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    data = await state.get_data()
    region_id = data.get("region_id")
    if not region_id and data.get("client_id"):
        client = await client_service.get_by_id(int(data["client_id"]))
        if client:
            region_id = client.region_id
            if client.region:
                await state.update_data(region_name=client.region.name)
    if not region_id:
        await callback.answer("Дані втрачено. Почніть з меню.", show_alert=True)
        return
    clients = await client_service.list_by_manager_and_region(
        db_user.id,
        int(region_id),
        exclude_potential=True,
    )
    await state.set_state(SaleStates.select_client)
    await _edit_step(
        callback.message,
        f"Область: <b>{data.get('region_name', '')}</b>\n\nОберіть клієнта:",
        reply_markup=sale_clients_keyboard(clients),
    )


@router.callback_query(F.data == "sale:back:brand")
async def back_brand(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    client_service: ClientService,
    brand_service: BrandService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    data = await state.get_data()
    client_id = data.get("client_id")
    if not client_id:
        await callback.answer("Дані втрачено. Почніть з меню.", show_alert=True)
        return
    client = await client_service.get_by_id(int(client_id))
    if client is None or client.manager_id != db_user.id:
        await callback.answer("Клієнта не знайдено", show_alert=True)
        return
    brands = await brand_service.brands_for_client_stands(client)
    from bot.utils.client_brands import brands_from_stands, brands_from_swatches

    all_brands = await brand_service.list_active()
    stand_brand_ids = {b.id for b in brands_from_stands(client, all_brands)}
    swatch_brand_ids = {b.id for b in brands_from_swatches(client, all_brands)}
    await state.update_data(
        allowed_brand_ids=[b.id for b in brands],
        stand_brand_ids=list(stand_brand_ids),
        swatch_brand_ids=list(swatch_brand_ids),
    )
    await state.set_state(SaleStates.select_brand)
    hint = "за стендами клієнта"
    if swatch_brand_ids and not stand_brand_ids:
        hint = "за свотчами клієнта"
    elif swatch_brand_ids:
        hint = "за стендами та свотчами клієнта"
    await _edit_step(
        callback.message,
        f"Клієнт: <b>{client.name}</b>\n\n"
        f"Оберіть торгову марку ({hint}):",
        reply_markup=sale_brands_keyboard(brands),
    )


@router.callback_query(F.data == "sale:back:quantity")
async def back_quantity(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return
    data = await state.get_data()
    await state.set_state(SaleStates.enter_quantity)
    await _edit_step(
        callback.message,
        f"Бренд: <b>{data.get('brand_name', '')}</b>\n\n"
        "Введіть кількість (кв. м):",
    )


@router.callback_query(F.data == "sale:back:comment")
async def back_comment(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return
    data = await state.get_data()
    await state.set_state(SaleStates.enter_comment)
    await _edit_step(
        callback.message,
        f"Кількість: <b>{data.get('quantity')}</b> кв. м\n\n"
        "Введіть коментар або натисніть «Без коментаря»:",
        reply_markup=sale_skip_comment_keyboard(),
    )
