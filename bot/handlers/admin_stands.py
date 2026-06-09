from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.clients import admin_stands_keyboard
from bot.services.stand import StandService
from bot.states.admin import AdminStandStates
from bot.utils.formatting import format_stand_list
from bot.utils.roles import can_manage_stand_catalog
from database.models import User

router = Router(name="admin_stands")


def _require_admin(user: User) -> bool:
    return can_manage_stand_catalog(user)


@router.callback_query(F.data == "admin:stands")
async def admin_stands_list(
    callback: CallbackQuery,
    db_user: User,
    stand_service: StandService,
) -> None:
    if not _require_admin(db_user):
        await callback.answer("Лише для адміністратора", show_alert=True)
        return
    await callback.answer()
    if callback.message is None:
        return

    stands = await stand_service.list_all()
    await callback.message.edit_text(
        "🏷 <b>Каталог стендів</b>\n\n"
        f"{format_stand_list(stands, active_only=False)}\n\n"
        "Натисніть стенд, щоб увімкнути/вимкнути.",
        reply_markup=admin_stands_keyboard(stands),
    )


@router.callback_query(F.data == "admin:stand:add")
async def admin_stand_add_start(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
) -> None:
    if not _require_admin(db_user):
        await callback.answer("Лише для адміністратора", show_alert=True)
        return
    await callback.answer()
    await state.set_state(AdminStandStates.add_name)
    if callback.message:
        await callback.message.answer("Введіть назву нового стенду:")


@router.message(AdminStandStates.add_name, F.text)
async def admin_stand_add_name(
    message: Message,
    state: FSMContext,
    db_user: User,
    stand_service: StandService,
) -> None:
    if not _require_admin(db_user):
        return

    name = message.text.strip()
    if not name:
        await message.answer("Назва не може бути порожньою.")
        return

    from sqlalchemy.exc import IntegrityError

    try:
        await stand_service.create(name)
    except IntegrityError:
        await message.answer("Такий стенд вже існує.")
        return

    await state.clear()
    stands = await stand_service.list_all()
    await message.answer(
        f"✅ Стенд <b>{name}</b> додано.",
        reply_markup=admin_stands_keyboard(stands),
    )


@router.callback_query(F.data.startswith("admin:stand:toggle:"))
async def admin_stand_toggle(
    callback: CallbackQuery,
    db_user: User,
    stand_service: StandService,
) -> None:
    if not _require_admin(db_user):
        await callback.answer("Лише для адміністратора", show_alert=True)
        return
    await callback.answer()
    if callback.message is None:
        return

    stand_id = int(callback.data.split(":")[-1])
    stand = await stand_service.list_all()
    current = next((s for s in stand if s.id == stand_id), None)
    if current is None:
        await callback.answer("Стенд не знайдений", show_alert=True)
        return

    await stand_service.set_active(stand_id, not current.is_active)
    stands = await stand_service.list_all()
    await callback.message.edit_text(
        "🏷 <b>Каталог стендів</b>\n\n"
        f"{format_stand_list(stands, active_only=False)}\n\n"
        "Натисніть стенд, щоб увімкнути/вимкнути.",
        reply_markup=admin_stands_keyboard(stands),
    )
