from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.clients import (
    client_card_keyboard,
    client_form_confirm_keyboard,
    region_pick_keyboard,
    stands_toggle_keyboard,
)
from bot.services.client import ClientService
from bot.services.region import RegionService
from bot.services.stand import StandService
from bot.states.client import ClientFormStates
from bot.utils.formatting import format_client_card, stand_names
from database.models import User
from web.client_geo import _city_from_comment

router = Router(name="client_form")


def _preview(data: dict) -> str:
    stands = ", ".join(data.get("stand_names", [])) or "—"
    city = data.get("city") or "—"
    comment = data.get("comment") or "—"
    return (
        "<b>Перевірте дані:</b>\n\n"
        f"Назва: {data.get('name', '—')}\n"
        f"Область: {data.get('region_name', '—')}\n"
        f"Адреса: {data.get('address', '—')}\n"
        f"Місто: {city}\n"
        f"Коментар: {comment}\n"
        f"Стенди: {stands}"
    )


def _comment_for_form(client) -> str | None:
    """Коментар для редагування без legacy «Місто: …»."""
    from web.client_geo import client_display_comment

    text = client_display_comment(client)
    return None if text == "—" else text


@router.callback_query(F.data == "client:add")
async def add_client_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await state.set_state(ClientFormStates.name)
    if callback.message:
        await callback.message.edit_text("➕ <b>Новий клієнт</b>\n\nВведіть назву:")


@router.callback_query(F.data.startswith("client:edit:"))
async def edit_client_start(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    client_service: ClientService,
) -> None:
    await callback.answer()
    client_id = int(callback.data.split(":")[-1])
    client = await client_service.get_by_id(client_id)
    if client is None or client.manager_id != db_user.id:
        await callback.answer("Клієнт не знайдений", show_alert=True)
        return

    await state.clear()
    await state.update_data(
        edit_client_id=client.id,
        name=client.name,
        region_id=client.region_id,
        region_name=client.region.name if client.region else "",
        address=client.address,
        city=client.city or _city_from_comment(client.comment),
        comment=_comment_for_form(client),
        stand_ids=[link.stand_id for link in client.stand_links],
        stand_names=stand_names(client),
    )
    await state.set_state(ClientFormStates.name)
    if callback.message:
        await callback.message.edit_text(
            f"✏️ <b>Редагування</b>\n\n"
            f"Поточна назва: <b>{client.name}</b>\n\n"
            "Введіть нову назву (або ту саму):",
        )


@router.message(ClientFormStates.name, F.text)
async def form_name(
    message: Message,
    state: FSMContext,
    db_user: User,
    region_service: RegionService,
) -> None:
    await state.update_data(name=message.text.strip())
    regions = await region_service.list_by_manager(db_user.id)
    if not regions:
        await message.answer(
            "Спочатку додайте область: 👤 Клієнти → 🗺 Мої області → ➕ Нова область",
        )
        await state.clear()
        return

    await state.set_state(ClientFormStates.region)
    await message.answer(
        "Оберіть область:",
        reply_markup=region_pick_keyboard(regions, back_callback="clients:hub"),
    )


@router.callback_query(ClientFormStates.region, F.data.startswith("client:region:"))
async def form_region(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
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

    await state.update_data(region_id=region.id, region_name=region.name)
    await state.set_state(ClientFormStates.address)

    data = await state.get_data()
    prompt = "Введіть адресу:"
    if data.get("address"):
        prompt = f"Поточна: {data['address']}\n\nВведіть адресу:"
    await callback.message.edit_text(prompt)


@router.message(ClientFormStates.address, F.text)
async def form_address(message: Message, state: FSMContext) -> None:
    await state.update_data(address=message.text.strip())
    await state.set_state(ClientFormStates.city)
    data = await state.get_data()
    hint = "Введіть місто (або «-» щоб пропустити):"
    if data.get("city"):
        hint = f"Поточне: {data['city']}\n\n{hint}"
    await message.answer(hint)


@router.message(ClientFormStates.city, F.text)
async def form_city(message: Message, state: FSMContext) -> None:
    city = message.text.strip()
    if city == "-":
        city = None
    await state.update_data(city=city)
    await state.set_state(ClientFormStates.comment)
    data = await state.get_data()
    hint = "Введіть коментар (або «-» щоб пропустити):"
    if data.get("comment"):
        hint = f"Поточний: {data['comment']}\n\n{hint}"
    await message.answer(hint)


@router.message(ClientFormStates.comment, F.text)
async def form_comment(
    message: Message,
    state: FSMContext,
    stand_service: StandService,
) -> None:
    comment = message.text.strip()
    if comment == "-":
        comment = None
    await state.update_data(comment=comment)

    stands = await stand_service.list_active()
    if not stands:
        await message.answer("Каталог стендів порожній. Зверніться до адміністратора.")
        await state.clear()
        return

    data = await state.get_data()
    selected = set(data.get("stand_ids", []))
    await state.set_state(ClientFormStates.stands)
    await message.answer(
        "Оберіть стенди (можна кілька):",
        reply_markup=stands_toggle_keyboard(
            stands,
            selected,
            back_callback="client:back:comment",
        ),
    )


@router.callback_query(ClientFormStates.stands, F.data.startswith("client:stand:"))
async def toggle_stand(
    callback: CallbackQuery,
    state: FSMContext,
    stand_service: StandService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    stand_id = int(callback.data.split(":")[-1])
    data = await state.get_data()
    selected: set[int] = set(data.get("stand_ids", []))
    if stand_id in selected:
        selected.discard(stand_id)
    else:
        selected.add(stand_id)

    stands = await stand_service.list_active()
    id_to_name = {s.id: s.name for s in stands}
    await state.update_data(
        stand_ids=list(selected),
        stand_names=[id_to_name[sid] for sid in sorted(selected) if sid in id_to_name],
    )
    await callback.message.edit_reply_markup(
        reply_markup=stands_toggle_keyboard(
            stands,
            selected,
            back_callback="client:back:comment",
        ),
    )


@router.callback_query(ClientFormStates.stands, F.data == "client:stands:done")
async def stands_done(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return

    data = await state.get_data()
    if not data.get("stand_ids"):
        await callback.answer("Оберіть хоча б один стенд", show_alert=True)
        return

    edit = data.get("edit_client_id") is not None
    await callback.message.edit_text(
        _preview(data),
        reply_markup=client_form_confirm_keyboard(edit=edit),
    )


@router.callback_query(F.data.in_({"client:save:new", "client:save:edit"}))
async def save_client(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    client_service: ClientService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    data = await state.get_data()
    required = ("name", "region_id", "address", "stand_ids")
    if not all(data.get(key) for key in required):
        await callback.answer("Заповніть усі обовʼязкові поля", show_alert=True)
        return

    if callback.data == "client:save:edit":
        client = await client_service.update(
            client_id=data["edit_client_id"],
            manager_id=db_user.id,
            region_id=data["region_id"],
            name=data["name"],
            address=data["address"],
            comment=data.get("comment"),
            city=data.get("city"),
            stand_ids=data["stand_ids"],
        )
    else:
        client = await client_service.create(
            manager_id=db_user.id,
            region_id=data["region_id"],
            name=data["name"],
            address=data["address"],
            city=data.get("city"),
            comment=data.get("comment"),
            stand_ids=data["stand_ids"],
        )

    await state.clear()
    if client is None:
        await callback.message.edit_text("Не вдалося зберегти клієнта.")
        return

    region_id = client.region_id or int(data["region_id"])
    source = data.get("card_source", "list")
    await callback.message.edit_text(
        "✅ Збережено\n\n" + format_client_card(client),
        reply_markup=client_card_keyboard(client.id, region_id, source=source),
    )


@router.callback_query(F.data == "client:back:city")
async def back_to_city(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await state.set_state(ClientFormStates.city)
    await callback.message.edit_text("Введіть місто (або «-» щоб пропустити):")


@router.callback_query(F.data == "client:back:comment")
async def back_to_comment(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await state.set_state(ClientFormStates.comment)
    await callback.message.edit_text("Введіть коментар (або «-» щоб пропустити):")
