from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.clients import clients_filter_regions_keyboard, clients_hub_keyboard
from bot.services.region import RegionService
from bot.states.client import ClientFormStates
from bot.states.region import RegionAddStates
from database.models import User

router = Router(name="regions")


@router.callback_query(F.data == "regions:list")
async def list_regions(
    callback: CallbackQuery,
    db_user: User,
    region_service: RegionService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    regions = await region_service.list_by_manager(db_user.id)
    if not regions:
        await callback.message.edit_text(
            "🗺 <b>Мої області</b>\n\nПоки немає областей. Додайте першу.",
            reply_markup=clients_hub_keyboard(db_user),
        )
        return

    await callback.message.edit_text(
        "🗺 <b>Мої області</b>\n\nОберіть область:",
        reply_markup=clients_filter_regions_keyboard(regions, source="regions"),
    )


@router.callback_query(F.data == "region:add")
async def region_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(RegionAddStates.name)
    await state.update_data(after_region="regions_list")
    if callback.message:
        await callback.message.edit_text("Введіть назву області:")


@router.callback_query(F.data == "client:region:new")
async def region_add_from_client_form(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(RegionAddStates.name)
    await state.update_data(after_region="client_form")
    if callback.message:
        await callback.message.answer("Введіть назву нової області:")


@router.message(RegionAddStates.name, F.text)
async def region_add_name(
    message: Message,
    state: FSMContext,
    db_user: User,
    region_service: RegionService,
) -> None:
    name = message.text.strip()
    if not name:
        await message.answer("Назва не може бути порожньою.")
        return

    from sqlalchemy.exc import IntegrityError

    try:
        region = await region_service.create(db_user.id, name)
    except IntegrityError:
        await message.answer("Таку область вже додано.")
        return

    data = await state.get_data()
    after = data.get("after_region", "regions_list")
    await state.update_data(
        region_id=region.id,
        region_name=region.name,
        after_region=None,
    )

    if after == "client_form":
        await state.set_state(ClientFormStates.address)
        await message.answer(
            f"Область <b>{region.name}</b> додано.\n\nВведіть адресу:",
        )
        return

    await state.clear()
    regions = await region_service.list_by_manager(db_user.id)
    await message.answer(
        f"✅ Область <b>{region.name}</b> додана.\n\nОберіть область:",
        reply_markup=clients_filter_regions_keyboard(regions, source="regions"),
    )

