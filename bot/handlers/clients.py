from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.keyboards.clients import (
    client_card_keyboard,
    client_list_keyboard,
    clients_filter_regions_keyboard,
    clients_hub_keyboard,
)
from bot.services.client import ClientService
from bot.services.region import RegionService
from bot.utils.formatting import format_client_card
from database.models import User

router = Router(name="clients")


@router.callback_query(F.data == "clients:hub")
async def clients_hub(callback: CallbackQuery, db_user: User) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await callback.message.edit_text(
        "👤 <b>Клієнти</b>\n\nОберіть дію:",
        reply_markup=clients_hub_keyboard(db_user),
    )


@router.callback_query(F.data == "clients:list")
async def list_clients_pick_region(
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
            "🗺 Спочатку додайте область:\n"
            "👤 Клієнти → 🗺 Мої області → ➕ Нова область",
            reply_markup=clients_hub_keyboard(db_user),
        )
        return

    await callback.message.edit_text(
        "📋 <b>Список клієнтів</b>\n\nОберіть область:",
        reply_markup=clients_filter_regions_keyboard(regions, source="list"),
    )


@router.callback_query(F.data.startswith("clients:show:"))
async def list_clients_by_region(
    callback: CallbackQuery,
    db_user: User,
    client_service: ClientService,
    region_service: RegionService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    parts = callback.data.split(":")
    region_id = int(parts[2])
    source = parts[3] if len(parts) > 3 else "list"

    region = await region_service.get_by_id(region_id)
    if region is None or region.manager_id != db_user.id:
        await callback.answer("Область не знайдена", show_alert=True)
        return

    all_regions = await region_service.list_by_manager(db_user.id)
    clients = await client_service.list_by_manager_and_region(db_user.id, region_id)
    if not clients:
        empty_title = (
            "🗺 <b>Мої області</b>" if source == "regions" else "📋 <b>Список клієнтів</b>"
        )
        await callback.message.edit_text(
            f"{empty_title}\n\n<b>{region.name}</b> — поки немає клієнтів.",
            reply_markup=clients_filter_regions_keyboard(all_regions, source=source),
        )
        return

    await callback.message.edit_text(
        f"<b>{region.name}</b>\n\nОберіть клієнта:",
        reply_markup=client_list_keyboard(clients, region_id, source=source),
    )


@router.callback_query(F.data.startswith("client:view:"))
async def view_client(
    callback: CallbackQuery,
    db_user: User,
    client_service: ClientService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    parts = callback.data.split(":")
    client_id = int(parts[2])
    region_id = int(parts[3]) if len(parts) > 3 else None
    source = parts[4] if len(parts) > 4 else "list"

    client = await client_service.get_by_id(client_id)
    if client is None or client.manager_id != db_user.id:
        await callback.answer("Клієнт не знайдений", show_alert=True)
        return

    if region_id is None:
        region_id = client.region_id

    await callback.message.edit_text(
        format_client_card(client),
        reply_markup=client_card_keyboard(client.id, region_id, source=source),
    )
