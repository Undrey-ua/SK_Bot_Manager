import logging
from datetime import date
from decimal import Decimal, InvalidOperation

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.inline import back_to_menu_keyboard, main_menu_keyboard
from bot.notifications.reserve_broadcast import broadcast_new_reserve
from bot.keyboards.reserves import (
    reserve_owner_actions_keyboard,
    reserve_view_keyboard,
    reserves_clients_keyboard,
    reserves_hub_keyboard,
    reserves_list_keyboard,
    reserves_regions_keyboard,
)
from bot.services.client import ClientService
from bot.services.region import RegionService
from bot.services.reserve import ReserveService
from bot.services.user import UserService
from bot.services.brand import BrandService
from bot.states.reserve import ReserveStates
from bot.utils.roles import effective_manager_id
from database.models import User

logger = logging.getLogger(__name__)
router = Router(name="reserves")


def _reserve_text(r) -> str:
    return (
        f"📦 <b>Резерв #{r.id}</b>\n\n"
        f"Менеджер: {r.manager.name}\n"
        f"Область: {r.region.name}\n"
        f"Клієнт: {r.client.name}\n"
        f"Матеріал: {r.material}\n"
        f"Кількість: {r.quantity} кв. м\n"
        f"Діє до: {r.expires_at.strftime('%Y-%m-%d %H:%M')} UTC"
    )


@router.callback_query(F.data == "reserve:hub")
async def reserves_hub(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await state.clear()
    await callback.message.edit_text(
        "📦 <b>Резерви</b>\n\nОберіть дію:",
        reply_markup=reserves_hub_keyboard(),
    )


@router.callback_query(F.data == "reserve:list")
async def reserves_list(
    callback: CallbackQuery,
    reserve_service: ReserveService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    items = await reserve_service.list_active()
    if not items:
        await callback.message.edit_text(
            "📦 <b>Резерви</b>\n\nНемає активних резервів.",
            reply_markup=reserves_hub_keyboard(),
        )
        return
    await callback.message.edit_text(
        "📦 <b>Активні резерви</b>\n\nОберіть резерв:",
        reply_markup=reserves_list_keyboard(items),
    )


@router.callback_query(F.data.startswith("reserve:show:"))
async def reserve_show(callback: CallbackQuery, db_user: User, reserve_service: ReserveService) -> None:
    await callback.answer()
    if callback.message is None:
        return
    reserve_id = int(callback.data.split(":")[-1])
    r = await reserve_service.get_by_id(reserve_id)
    if r is None:
        await callback.message.edit_text("Резерв не знайдено.", reply_markup=reserves_hub_keyboard())
        return
    if r.manager_id == effective_manager_id(db_user):
        kb = reserve_owner_actions_keyboard(r.id)
    else:
        kb = reserve_view_keyboard(r.id)
    await callback.message.edit_text(_reserve_text(r), reply_markup=kb)


@router.callback_query(F.data == "reserve:new")
async def reserve_new(
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
            "📦 <b>Додати резерв</b>\n\nСпочатку додайте область: 👤 Клієнти → 🗺 Мої області",
            reply_markup=main_menu_keyboard(db_user),
        )
        return
    await state.clear()
    await state.set_state(ReserveStates.select_region)
    await callback.message.edit_text(
        "📦 <b>Додати резерв</b>\n\nОберіть область:",
        reply_markup=reserves_regions_keyboard(regions),
    )


@router.callback_query(ReserveStates.select_region, F.data.startswith("reserve:pick_region:"))
async def reserve_pick_region(
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
    if region is None or region.manager_id != effective_manager_id(db_user):
        await callback.answer("Область не знайдена", show_alert=True)
        return
    clients = await client_service.list_by_manager_and_region(effective_manager_id(db_user), region_id)
    if not clients:
        await callback.message.edit_text(
            f"<b>{region.name}</b> — немає клієнтів. Оберіть іншу область:",
            reply_markup=reserves_regions_keyboard(await region_service.list_by_manager(effective_manager_id(db_user))),
        )
        return
    await state.update_data(region_id=region.id, region_name=region.name)
    await state.set_state(ReserveStates.select_client)
    await callback.message.edit_text(
        f"Область: <b>{region.name}</b>\n\nОберіть клієнта:",
        reply_markup=reserves_clients_keyboard(clients),
    )


@router.callback_query(F.data == "reserve:back:regions")
async def reserve_back_regions(callback: CallbackQuery, state: FSMContext, db_user: User, region_service: RegionService) -> None:
    await callback.answer()
    if callback.message is None:
        return
    regions = await region_service.list_by_manager(effective_manager_id(db_user))
    await state.set_state(ReserveStates.select_region)
    await callback.message.edit_text("📦 <b>Додати резерв</b>\n\nОберіть область:", reply_markup=reserves_regions_keyboard(regions))


@router.callback_query(ReserveStates.select_client, F.data.startswith("reserve:client:"))
async def reserve_pick_client(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    client_service: ClientService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    client_id = int(callback.data.split(":")[-1])
    client = await client_service.get_by_id(client_id)
    if client is None or client.manager_id != effective_manager_id(db_user):
        await callback.answer("Клієнта не знайдено", show_alert=True)
        return
    await state.update_data(client_id=client.id, client_name=client.name)
    await state.set_state(ReserveStates.enter_material)
    await callback.message.edit_text(
        f"Клієнт: <b>{client.name}</b>\n\nВведіть матеріал (довільний текст):",
    )


@router.message(ReserveStates.enter_material, F.text)
async def reserve_material(message: Message, state: FSMContext) -> None:
    material = message.text.strip()
    if not material:
        await message.answer("Введіть матеріал текстом.")
        return
    await state.update_data(material=material)
    await state.set_state(ReserveStates.enter_quantity)
    await message.answer("Введіть кількість (кв. м), наприклад <code>12.5</code>:")


@router.message(ReserveStates.enter_quantity, F.text)
async def reserve_quantity(
    message: Message,
    state: FSMContext,
    bot: Bot,
    db_user: User,
    reserve_service: ReserveService,
    user_service: UserService,
) -> None:
    raw = message.text.strip().replace(",", ".")
    try:
        qty = Decimal(raw)
        if qty <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer("Введіть додатне число, наприклад 10 або 12.5")
        return

    data = await state.get_data()
    for key in ("region_id", "client_id", "material"):
        if not data.get(key):
            await message.answer("Дані втрачено. Почніть спочатку.", reply_markup=back_to_menu_keyboard())
            await state.clear()
            return

    try:
        reserve = await reserve_service.create(
            manager_id=effective_manager_id(db_user),
            region_id=int(data["region_id"]),
            client_id=int(data["client_id"]),
            material=data["material"],
            quantity=qty,
            created_by_id=db_user.id,
        )
    except Exception:
        logger.exception("Failed to create reserve")
        await message.answer("❌ Не вдалося створити резерв. Спробуйте ще раз.")
        return

    await state.clear()
    await message.answer(
        f"✅ <b>Резерв #{reserve.id} створено</b>\n\n"
        f"Матеріал: {reserve.material}\n"
        f"Кількість: {reserve.quantity} кв. м",
        reply_markup=back_to_menu_keyboard(),
    )
    try:
        users = await user_service.list_all()
        await broadcast_new_reserve(
            bot_token=bot.token,
            users=users,
            reserve_id=reserve.id,
            manager_name=db_user.name,
            client_name=str(data.get("client_name") or ""),
            region_name=str(data.get("region_name") or ""),
            material=str(data.get("material") or reserve.material),
            quantity=qty,
            expires_at=reserve.expires_at,
        )
    except Exception:
        # Важливо: нотифікації не повинні відміняти транзакцію створення резерву
        logger.exception("Reserve broadcast failed")


@router.callback_query(F.data.startswith("reserve:cancel:"))
async def reserve_cancel(callback: CallbackQuery, db_user: User, reserve_service: ReserveService) -> None:
    await callback.answer()
    if callback.message is None:
        return
    rid = int(callback.data.split(":")[-1])
    r = await reserve_service.get_by_id(rid)
    if r is None:
        await callback.message.edit_text("Резерв не знайдено.", reply_markup=reserves_hub_keyboard())
        return
    if r.manager_id != effective_manager_id(db_user):
        await callback.answer("Скасувати може лише той, хто поставив резерв.", show_alert=True)
        return
    await reserve_service.cancel(rid)
    await callback.message.edit_text("❌ Резерв скасовано.", reply_markup=reserves_hub_keyboard())


@router.callback_query(F.data.startswith("reserve:extend:"))
async def reserve_extend(callback: CallbackQuery, db_user: User, reserve_service: ReserveService) -> None:
    await callback.answer()
    if callback.message is None:
        return
    rid = int(callback.data.split(":")[-1])
    r = await reserve_service.get_by_id(rid)
    if r is None:
        await callback.message.edit_text("Резерв не знайдено.", reply_markup=reserves_hub_keyboard())
        return
    if r.manager_id != effective_manager_id(db_user):
        await callback.answer("Продовжити може лише той, хто поставив резерв.", show_alert=True)
        return
    r2 = await reserve_service.extend(rid)
    await callback.message.edit_text(
        f"🔁 Резерв продовжено до {r2.expires_at.strftime('%Y-%m-%d %H:%M')} UTC",
        reply_markup=reserves_hub_keyboard(),
    )


# Продаж із резерву: мінімально — вибір бренда з каталогу брендів + уточнення кількості (передзаповнено).
@router.callback_query(F.data.startswith("reserve:sale:"))
async def reserve_sale_start(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    reserve_service: ReserveService,
    brand_service: BrandService,
    client_service: ClientService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    rid = int(callback.data.split(":")[-1])
    r = await reserve_service.get_by_id(rid)
    if r is None:
        await callback.message.edit_text("Резерв не знайдено.", reply_markup=reserves_hub_keyboard())
        return
    if r.manager_id != effective_manager_id(db_user):
        await callback.answer("Продаж доступний лише автору резерву.", show_alert=True)
        return
    client = await client_service.get_by_id(r.client_id)
    if client is None:
        await callback.message.edit_text("Клієнта не знайдено.", reply_markup=reserves_hub_keyboard())
        return
    brands = await brand_service.brands_for_client_stands(client)
    if not brands:
        await callback.message.edit_text(
            f"💰 <b>Продаж із резерву</b>\n\n"
            f"У клієнта <b>{client.name}</b> немає стендів і свотчів із відомими брендами.",
            reply_markup=reserves_hub_keyboard(),
        )
        return
    from bot.keyboards.sales import sale_brands_keyboard
    from bot.utils.client_brands import brands_from_stands, brands_from_swatches

    all_brands = await brand_service.list_active()
    stand_brand_ids = {b.id for b in brands_from_stands(client, all_brands)}
    swatch_brand_ids = {b.id for b in brands_from_swatches(client, all_brands)}

    await state.clear()
    await state.update_data(
        from_reserve=True,
        reserve_id=r.id,
        client_id=r.client_id,
        client_name=r.client.name,
        reserve_qty=str(r.quantity),
        allowed_brand_ids=[b.id for b in brands],
        stand_brand_ids=list(stand_brand_ids),
        swatch_brand_ids=list(swatch_brand_ids),
    )
    await state.set_state("reserve_sale:brand")
    hint = "за стендами клієнта"
    if swatch_brand_ids and not stand_brand_ids:
        hint = "за свотчами клієнта"
    elif swatch_brand_ids:
        hint = "за стендами та свотчами клієнта"
    await callback.message.edit_text(
        f"💰 <b>Продаж із резерву</b>\n\n"
        f"Клієнт: <b>{r.client.name}</b>\n\n"
        f"Оберіть торгову марку ({hint}):",
        reply_markup=sale_brands_keyboard(brands),
    )


@router.callback_query(StateFilter("reserve_sale:brand"), F.data.startswith("sale:brand:"))
async def reserve_sale_pick_brand(
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

    await state.update_data(brand_id=brand_id, brand_name=brand_button_label(brand))
    await state.set_state("reserve_sale:qty")
    data = await state.get_data()
    await callback.message.edit_text(
        f"Введіть кількість (кв. м). Поточний резерв: <b>{data.get('reserve_qty')}</b>",
    )


@router.message(StateFilter("reserve_sale:qty"), F.text)
async def reserve_sale_qty(message: Message, state: FSMContext) -> None:
    raw = message.text.strip().replace(",", ".")
    try:
        qty = Decimal(raw)
        if qty <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer("Введіть додатне число.")
        return
    await state.update_data(quantity=str(qty), comment=None, period_year=date.today().year)
    from bot.keyboards.sales import sale_period_keyboard
    from bot.states.sale import SaleStates

    await state.set_state(SaleStates.select_period)
    await message.answer(
        "💰 <b>Період продажу</b>\n\n"
        f"Оберіть місяць (<b>{date.today().year}</b> рік):",
        reply_markup=sale_period_keyboard(date.today().year),
    )

