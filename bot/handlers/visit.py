import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.inline import (
    back_to_menu_keyboard,
    main_menu_keyboard,
    photos_keyboard,
    potential_photo_keyboard,
    tasks_keyboard,
    visit_clients_keyboard,
    visit_potential_clients_keyboard,
    visit_regions_keyboard,
    visit_type_keyboard,
)
from bot.services.client import ClientService
from bot.services.region import RegionService
from bot.services.storage import StorageService
from bot.services.visit import VisitService
from bot.services.visit_task_type import VisitTaskTypeService
from bot.states.visit import VisitStates
from database.models import VISIT_TYPE_LABELS, User, VisitType
from visit_task_labels import visit_task_label

logger = logging.getLogger(__name__)
router = Router(name="visit")


async def _active_task_choices(
    visit_task_type_service: VisitTaskTypeService,
) -> list[tuple[str, str]]:
    rows = await visit_task_type_service.list_active()
    return [(row.code, row.label) for row in rows]


def _tasks_text(selected: list[str]) -> str:
    return ", ".join(visit_task_label(t) for t in selected) if selected else "—"


async def _show_clients_picker(
    message,
    state: FSMContext,
    db_user: User,
    client_service: ClientService,
    *,
    region_id: int,
    region_name: str,
) -> None:
    clients = await client_service.list_by_manager_and_region(
        db_user.id,
        region_id,
        exclude_potential=True,
    )
    await state.set_state(VisitStates.select_client)
    subtitle = (
        f"Область: <b>{region_name}</b>\n\nОберіть клієнта:"
        if clients
        else f"Область: <b>{region_name}</b>\n\nОберіть клієнта або «Потенційний клієнт»:"
    )
    await message.edit_text(
        f"➕ <b>Новий візит</b>\n\n{subtitle}",
        reply_markup=visit_clients_keyboard(clients),
    )


async def _show_potential_clients_picker(
    message,
    state: FSMContext,
    db_user: User,
    client_service: ClientService,
    *,
    region_id: int,
    region_name: str,
) -> None:
    potentials = await client_service.list_by_manager_and_region(
        db_user.id,
        region_id,
        potential_only=True,
    )
    await state.set_state(VisitStates.select_potential_client)
    subtitle = (
        "Оберіть потенційного клієнта або натисніть «Новий»:"
        if potentials
        else "Поки немає потенційних клієнтів. Натисніть «Новий»:"
    )
    await message.edit_text(
        f"➕ <b>Новий візит</b>\n\n"
        f"Область: <b>{region_name}</b>\n"
        f"⭐ <b>Потенційні клієнти</b>\n\n{subtitle}",
        reply_markup=visit_potential_clients_keyboard(potentials),
    )


@router.callback_query(F.data == "visit:new")
async def start_visit(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    region_service: RegionService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    regions = await region_service.list_by_manager(db_user.id)
    if not regions:
        await callback.message.edit_text(
            "➕ <b>Новий візит</b>\n\n"
            "Спочатку додайте область: 👤 Клієнти → 🗺 Мої області",
            reply_markup=main_menu_keyboard(db_user),
        )
        return

    await state.clear()
    await state.set_state(VisitStates.select_region)
    await callback.message.edit_text(
        "➕ <b>Новий візит</b>\n\nОберіть область:",
        reply_markup=visit_regions_keyboard(regions),
    )


@router.callback_query(
    VisitStates.select_region,
    F.data.startswith("visit:pick_region:"),
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

    await state.update_data(region_id=region_id, region_name=region.name)
    await state.set_state(VisitStates.select_client)
    subtitle = (
        f"Область: <b>{region.name}</b>\n\nОберіть клієнта:"
        if clients
        else f"Область: <b>{region.name}</b>\n\nОберіть клієнта або «Потенційний клієнт»:"
    )
    await callback.message.edit_text(
        f"➕ <b>Новий візит</b>\n\n{subtitle}",
        reply_markup=visit_clients_keyboard(clients),
    )


@router.callback_query(
    VisitStates.select_client,
    F.data == "visit:potential:list",
)
async def show_potential_clients(
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
    region_name = data.get("region_name", "")
    if not region_id:
        await callback.answer("Спочатку оберіть область", show_alert=True)
        return
    await _show_potential_clients_picker(
        callback.message,
        state,
        db_user,
        client_service,
        region_id=int(region_id),
        region_name=region_name,
    )


@router.callback_query(
    VisitStates.select_potential_client,
    F.data == "visit:potential:new",
)
async def start_potential_client(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await state.update_data(potential_photo_url=None)
    await state.set_state(VisitStates.potential_name)
    await callback.message.edit_text(
        "⭐ <b>Потенційний клієнт</b>\n\nВведіть назву магазину:",
    )


@router.message(VisitStates.potential_name, F.text)
async def potential_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if not name:
        await message.answer("Введіть назву магазину:")
        return
    await state.update_data(potential_name=name)
    await state.set_state(VisitStates.potential_address)
    await message.answer("Введіть адресу:")


@router.message(VisitStates.potential_address, F.text)
async def potential_address(message: Message, state: FSMContext) -> None:
    address = message.text.strip()
    if not address:
        await message.answer("Введіть адресу:")
        return
    await state.update_data(potential_address=address)
    await state.set_state(VisitStates.potential_photo)
    await message.answer(
        "📷 Надішліть фото торгової точки (необовʼязково)\n"
        "або натисніть «Пропустити фото».",
        reply_markup=potential_photo_keyboard(),
    )


async def _finish_potential_and_select_type(
    target: CallbackQuery | Message,
    state: FSMContext,
    db_user: User,
    client_service: ClientService,
) -> None:
    data = await state.get_data()
    client = await client_service.create_potential(
        manager_id=db_user.id,
        region_id=int(data["region_id"]),
        name=data["potential_name"],
        address=data["potential_address"],
        photo_url=data.get("potential_photo_url"),
    )
    await state.update_data(client_id=client.id, client_name=client.name)
    await state.set_state(VisitStates.select_visit_type)
    text = (
        f"⭐ Потенційний клієнт: <b>{client.name}</b>\n\n"
        "Оберіть тип візиту:"
    )
    markup = visit_type_keyboard()
    if isinstance(target, CallbackQuery):
        if target.message:
            await target.message.edit_text(text, reply_markup=markup)
    else:
        await target.answer(text, reply_markup=markup)


@router.message(VisitStates.potential_photo, F.photo)
async def potential_photo(
    message: Message,
    state: FSMContext,
    bot: Bot,
    db_user: User,
    client_service: ClientService,
    storage_service: StorageService,
) -> None:
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    if file.file_path is None:
        await message.answer("Не вдалося завантажити фото. Спробуйте ще раз.")
        return
    buffer = await bot.download_file(file.file_path)
    if buffer is None:
        await message.answer("Не вдалося завантажити фото. Спробуйте ще раз.")
        return
    extension = file.file_path.rsplit(".", 1)[-1] if "." in file.file_path else "jpg"
    url = await storage_service.upload_photo(buffer.read(), extension=extension)
    await state.update_data(potential_photo_url=url)
    await _finish_potential_and_select_type(
        message, state, db_user, client_service
    )


@router.callback_query(
    VisitStates.potential_photo,
    F.data == "visit:potential:skip_photo",
)
async def potential_skip_photo(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    client_service: ClientService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await _finish_potential_and_select_type(
        callback, state, db_user, client_service
    )


@router.callback_query(
    VisitStates.select_potential_client,
    F.data.startswith("visit:client:"),
)
@router.callback_query(
    VisitStates.select_client,
    F.data.startswith("visit:client:"),
)
async def select_client(
    callback: CallbackQuery,
    state: FSMContext,
    client_service: ClientService,
    db_user: User,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    client_id = int(callback.data.split(":")[-1])
    client = await client_service.get_by_id(client_id)
    if client is None or client.manager_id != db_user.id:
        await callback.answer("Клієнт не знайдений", show_alert=True)
        return

    await state.update_data(client_id=client_id, client_name=client.name)
    await state.set_state(VisitStates.select_visit_type)
    prefix = "⭐ Потенційний клієнт" if client.is_potential else "Клієнт"
    await callback.message.edit_text(
        f"{prefix}: <b>{client.name}</b>\n\nОберіть тип візиту:",
        reply_markup=visit_type_keyboard(),
    )


@router.callback_query(
    VisitStates.select_visit_type,
    F.data.startswith("visit:type:"),
)
async def select_visit_type(
    callback: CallbackQuery,
    state: FSMContext,
    visit_task_type_service: VisitTaskTypeService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    task_choices = await _active_task_choices(visit_task_type_service)
    if not task_choices:
        await callback.answer(
            "Немає доступних задач візиту. Зверніться до адміністратора.",
            show_alert=True,
        )
        return

    visit_type = callback.data.split(":")[-1]
    await state.update_data(visit_type=visit_type, selected_tasks=[])
    await state.set_state(VisitStates.select_tasks)
    await callback.message.edit_text(
        f"Тип: <b>{VISIT_TYPE_LABELS[VisitType(visit_type)]}</b>\n\n"
        "Оберіть задачі (можна кілька):",
        reply_markup=tasks_keyboard(set(), task_choices),
    )


@router.callback_query(
    VisitStates.select_tasks,
    F.data.startswith("visit:task:"),
)
async def toggle_task(
    callback: CallbackQuery,
    state: FSMContext,
    visit_task_type_service: VisitTaskTypeService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    task = callback.data.split(":")[-1]
    data = await state.get_data()
    selected: set[str] = set(data.get("selected_tasks", []))
    if task in selected:
        selected.discard(task)
    else:
        selected.add(task)

    await state.update_data(selected_tasks=list(selected))
    task_choices = await _active_task_choices(visit_task_type_service)
    await callback.message.edit_reply_markup(
        reply_markup=tasks_keyboard(selected, task_choices),
    )


@router.callback_query(VisitStates.select_tasks, F.data == "visit:tasks:done")
async def tasks_done(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return

    data = await state.get_data()
    selected: list[str] = data.get("selected_tasks", [])
    if not selected:
        await callback.answer("Оберіть хоча б одну задачу", show_alert=True)
        return

    await state.set_state(VisitStates.enter_comment)
    await callback.message.edit_text(
        f"Задачі: {_tasks_text(selected)}\n\n"
        "Введіть коментар до візиту (або «-» щоб пропустити):",
    )


@router.message(VisitStates.enter_comment, F.text)
async def enter_comment(message: Message, state: FSMContext) -> None:
    comment = message.text.strip()
    if comment == "-":
        comment = None
    await state.update_data(comment=comment, photo_urls=[])
    await state.set_state(VisitStates.upload_photos)
    await message.answer(
        "📷 Надішліть фото візиту (необовʼязково).\n"
        "Можна кілька. Коли готово — натисніть «Завершити».",
        reply_markup=photos_keyboard(0),
    )


@router.message(VisitStates.upload_photos, F.photo)
async def upload_photo(
    message: Message,
    state: FSMContext,
    bot: Bot,
    storage_service: StorageService,
) -> None:
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    if file.file_path is None:
        await message.answer("Не вдалося завантажити фото. Спробуйте ще раз.")
        return

    buffer = await bot.download_file(file.file_path)
    if buffer is None:
        await message.answer("Не вдалося завантажити фото. Спробуйте ще раз.")
        return

    extension = file.file_path.rsplit(".", 1)[-1] if "." in file.file_path else "jpg"
    url = await storage_service.upload_photo(buffer.read(), extension=extension)

    data = await state.get_data()
    photo_urls: list[str] = data.get("photo_urls", [])
    photo_urls.append(url)
    await state.update_data(photo_urls=photo_urls)

    await message.answer(
        f"✅ Фото збережено ({len(photo_urls)}).\n"
        "Надішліть ще або натисніть «Завершити».",
        reply_markup=photos_keyboard(len(photo_urls)),
    )


@router.callback_query(VisitStates.upload_photos, F.data == "visit:photos:done")
async def finish_visit(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    visit_service: VisitService,
    visit_task_type_service: VisitTaskTypeService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    data = await state.get_data()
    photo_urls: list[str] = data.get("photo_urls", [])
    selected_tasks = await visit_task_type_service.filter_known_tasks(
        data.get("selected_tasks", [])
    )
    if not selected_tasks:
        await callback.answer("Оберіть хоча б одну задачу", show_alert=True)
        return

    visit = await visit_service.create_visit(
        manager_id=db_user.id,
        client_id=data["client_id"],
        visit_type=data["visit_type"],
        comment=data.get("comment"),
        tasks=selected_tasks,
        photo_urls=photo_urls,
    )

    await state.clear()
    visit_label = VISIT_TYPE_LABELS[VisitType(data["visit_type"])]
    photos_line = f"{len(photo_urls)} шт." if photo_urls else "без фото"
    await callback.message.edit_text(
        f"✅ <b>Візит #{visit.id} збережено</b>\n\n"
        f"Клієнт: {data['client_name']}\n"
        f"Тип: {visit_label}\n"
        f"Фото: {photos_line}",
        reply_markup=back_to_menu_keyboard(),
    )
    logger.info("Visit %s created by user %s", visit.id, db_user.id)


@router.callback_query(F.data == "visit:back:regions")
async def back_to_regions(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    region_service: RegionService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    regions = await region_service.list_by_manager(db_user.id)
    await state.set_state(VisitStates.select_region)
    await callback.message.edit_text(
        "➕ <b>Новий візит</b>\n\nОберіть область:",
        reply_markup=visit_regions_keyboard(regions),
    )


@router.callback_query(F.data == "visit:back:client")
async def back_to_client(
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
    region_name = data.get("region_name", "")
    if not region_id:
        await callback.answer("Спочатку оберіть область", show_alert=True)
        return
    await _show_clients_picker(
        callback.message,
        state,
        db_user,
        client_service,
        region_id=int(region_id),
        region_name=region_name,
    )


@router.callback_query(F.data == "visit:back:potential_list")
async def back_to_potential_list(
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
    region_name = data.get("region_name", "")
    if not region_id:
        await callback.answer("Спочатку оберіть область", show_alert=True)
        return
    await _show_potential_clients_picker(
        callback.message,
        state,
        db_user,
        client_service,
        region_id=int(region_id),
        region_name=region_name,
    )


@router.callback_query(F.data == "visit:back:type")
async def back_to_type(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return
    data = await state.get_data()
    await state.set_state(VisitStates.select_visit_type)
    await callback.message.edit_text(
        f"Клієнт: <b>{data.get('client_name', '')}</b>\n\nОберіть тип візиту:",
        reply_markup=visit_type_keyboard(),
    )


@router.callback_query(F.data == "visit:back:comment")
async def back_to_comment(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return
    data = await state.get_data()
    selected: list[str] = data.get("selected_tasks", [])
    await state.set_state(VisitStates.enter_comment)
    await callback.message.edit_text(
        f"Задачі: {_tasks_text(selected)}\n\n"
        "Введіть коментар до візиту (або «-» щоб пропустити):",
    )
