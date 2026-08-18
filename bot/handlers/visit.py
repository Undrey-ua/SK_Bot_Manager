import asyncio
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
    visit_cities_keyboard,
    visit_clients_keyboard,
    visit_potential_clients_keyboard,
    visit_regions_keyboard,
    visit_scope_keyboard,
)
from bot.services.client import ClientService
from bot.services.region import RegionService
from bot.services.storage import StorageService
from bot.services.visit import VisitService
from bot.services.visit_task_type import VisitTaskTypeService
from bot.states.visit import VisitStates
from config.work_scope import default_visit_type, is_dual_scope
from database.models import VISIT_TYPE_LABELS, User, VisitType
from visit_task_labels import visit_task_label

logger = logging.getLogger(__name__)
router = Router(name="visit")

_potential_create_locks: dict[int, asyncio.Lock] = {}
_potential_create_locks_guard = asyncio.Lock()


async def _claim_potential_client_create(manager_id: int, state: FSMContext) -> bool:
    """Лише один апдейт створює потенційного клієнта (альбом / кілька фото)."""
    async with _potential_create_locks_guard:
        lock = _potential_create_locks.get(manager_id)
        if lock is None:
            lock = asyncio.Lock()
            _potential_create_locks[manager_id] = lock
    async with lock:
        data = await state.get_data()
        if data.get("client_id") or data.get("potential_creating"):
            return False
        await state.update_data(potential_creating=True)
        return True


async def _release_potential_client_create(state: FSMContext) -> None:
    await state.update_data(potential_creating=False)


async def _active_task_choices(
    visit_task_type_service: VisitTaskTypeService,
) -> list[tuple[str, str]]:
    rows = await visit_task_type_service.list_active()
    return [(row.code, row.label) for row in rows]


def _tasks_text(selected: list[str]) -> str:
    return ", ".join(visit_task_label(t) for t in selected) if selected else "—"


def _visit_is_pvc(data: dict) -> bool:
    return data.get("visit_type") == VisitType.PVH.value


def _visit_title(data: dict) -> str:
    vt = data.get("visit_type")
    if not vt:
        return "➕ <b>Новий візит</b>"
    try:
        return f"➕ <b>Новий візит</b> · {VISIT_TYPE_LABELS[VisitType(vt)]}"
    except ValueError:
        return "➕ <b>Новий візит</b>"


def _client_query_kwargs(data: dict) -> dict:
    kwargs: dict = {"is_pvc": _visit_is_pvc(data)}
    city = data.get("city")
    if city:
        kwargs["city"] = city
    return kwargs


def _regions_back_kwargs(user: User) -> dict:
    if is_dual_scope(user):
        return {"back_callback": "visit:back:scope", "back_label": "◀️ Тип візиту"}
    return {"back_callback": "menu:main", "back_label": "◀️ Меню"}


def _clients_back_kwargs(user: User) -> dict:
    if is_dual_scope(user):
        return {"back_callback": "visit:back:city", "back_label": "◀️ Міста"}
    return {"back_callback": "visit:back:regions", "back_label": "◀️ Області"}


async def _show_clients_picker(
    message,
    state: FSMContext,
    db_user: User,
    client_service: ClientService,
    *,
    region_id: int,
    region_name: str,
) -> None:
    data = await state.get_data()
    clients = await client_service.list_by_manager_and_region(
        db_user.id,
        region_id,
        exclude_potential=True,
        **_client_query_kwargs(data),
    )
    await state.set_state(VisitStates.select_client)
    city = data.get("city")
    city_line = f"\nМісто: <b>{city}</b>" if city else ""
    subtitle = (
        f"Область: <b>{region_name}</b>{city_line}\n\nОберіть клієнта:"
        if clients
        else (
            f"Область: <b>{region_name}</b>{city_line}\n\n"
            "Оберіть клієнта або «Потенційний клієнт»:"
        )
    )
    await message.edit_text(
        f"{_visit_title(data)}\n\n{subtitle}",
        reply_markup=visit_clients_keyboard(clients, **_clients_back_kwargs(db_user)),
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
    data = await state.get_data()
    potentials = await client_service.list_by_manager_and_region(
        db_user.id,
        region_id,
        potential_only=True,
        **_client_query_kwargs(data),
    )
    await state.set_state(VisitStates.select_potential_client)
    subtitle = (
        "Оберіть потенційного клієнта або натисніть «Новий»:"
        if potentials
        else "Поки немає потенційних клієнтів. Натисніть «Новий»:"
    )
    await message.edit_text(
        f"{_visit_title(data)}\n\n"
        f"Область: <b>{region_name}</b>\n"
        f"⭐ <b>Потенційні клієнти</b>\n\n{subtitle}",
        reply_markup=visit_potential_clients_keyboard(potentials),
    )


async def _show_regions(
    message,
    state: FSMContext,
    db_user: User,
    region_service: RegionService,
) -> None:
    regions = await region_service.list_by_manager(db_user.id)
    data = await state.get_data()
    await state.set_state(VisitStates.select_region)
    await message.edit_text(
        f"{_visit_title(data)}\n\nОберіть область:",
        reply_markup=visit_regions_keyboard(regions, **_regions_back_kwargs(db_user)),
    )


async def _show_cities(
    message,
    state: FSMContext,
    db_user: User,
    client_service: ClientService,
) -> None:
    data = await state.get_data()
    region_id = int(data["region_id"])
    cities = await client_service.list_cities_for_region(
        db_user.id,
        region_id,
        is_pvc=None,
    )
    await state.update_data(city_options=cities, city=None)
    await state.set_state(VisitStates.select_city)
    await message.edit_text(
        f"{_visit_title(data)}\n\n"
        f"Область: <b>{data.get('region_name', '')}</b>\n\n"
        "Оберіть місто:",
        reply_markup=visit_cities_keyboard(cities),
    )


async def _continue_after_client(
    target: CallbackQuery | Message,
    state: FSMContext,
    visit_task_type_service: VisitTaskTypeService,
) -> None:
    data = await state.get_data()
    if not data.get("visit_type"):
        await state.update_data(visit_type=VisitType.STAND.value)
        data = await state.get_data()
    if data.get("is_potential"):
        await state.set_state(VisitStates.enter_comment)
        text = "Введіть коментар до візиту (або «-» щоб пропустити):"
        if isinstance(target, CallbackQuery) and target.message:
            await target.message.edit_text(text)
        elif isinstance(target, Message):
            await target.answer(text)
        return

    task_choices = await _active_task_choices(visit_task_type_service)
    if not task_choices:
        if isinstance(target, CallbackQuery):
            await target.answer(
                "Немає доступних задач візиту. Зверніться до адміністратора.",
                show_alert=True,
            )
        return

    await state.update_data(selected_tasks=[])
    await state.set_state(VisitStates.select_tasks)
    text = "Оберіть задачі (можна кілька):"
    markup = tasks_keyboard(set(), task_choices)
    if isinstance(target, CallbackQuery) and target.message:
        await target.message.edit_text(text, reply_markup=markup)
    elif isinstance(target, Message):
        await target.answer(text, reply_markup=markup)


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
    if is_dual_scope(db_user):
        await state.set_state(VisitStates.select_visit_type)
        await callback.message.edit_text(
            "➕ <b>Новий візит</b>\n\nОберіть тип візиту:",
            reply_markup=visit_scope_keyboard(),
        )
        return

    await state.update_data(visit_type=default_visit_type(db_user))
    await _show_regions(callback.message, state, db_user, region_service)


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

    await state.update_data(region_id=region_id, region_name=region.name, city=None)
    if is_dual_scope(db_user):
        await _show_cities(callback.message, state, db_user, client_service)
        return
    await _show_clients_picker(
        callback.message,
        state,
        db_user,
        client_service,
        region_id=region_id,
        region_name=region.name,
    )


@router.callback_query(
    VisitStates.select_visit_type,
    F.data.startswith("visit:scope:"),
)
async def pick_visit_scope(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    region_service: RegionService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    visit_type = callback.data.split(":")[-1]
    if visit_type not in {v.value for v in VisitType}:
        await callback.answer("Невірний тип візиту", show_alert=True)
        return
    await state.update_data(visit_type=visit_type, selected_tasks=[])
    await _show_regions(callback.message, state, db_user, region_service)


@router.callback_query(
    VisitStates.select_city,
    F.data.startswith("visit:pick_city:"),
)
async def pick_city(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    client_service: ClientService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    data = await state.get_data()
    token = callback.data.split(":")[-1]
    if token == "all":
        city = None
    else:
        options: list[str] = data.get("city_options") or []
        try:
            city = options[int(token)]
        except (ValueError, IndexError):
            await callback.answer("Місто не знайдено", show_alert=True)
            return
    await state.update_data(city=city)
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


@router.callback_query(VisitStates.select_city, F.data == "visit:city:custom")
async def start_custom_city(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await state.set_state(VisitStates.enter_city)
    await callback.message.edit_text("Введіть назву міста:")


@router.message(VisitStates.enter_city, F.text)
async def enter_custom_city(
    message: Message,
    state: FSMContext,
    db_user: User,
    client_service: ClientService,
) -> None:
    city = message.text.strip()
    if not city:
        await message.answer("Введіть назву міста:")
        return
    await state.update_data(city=city)
    data = await state.get_data()
    region_id = data.get("region_id")
    region_name = data.get("region_name", "")
    if not region_id:
        await message.answer("Спочатку оберіть область.")
        return
    clients = await client_service.list_by_manager_and_region(
        db_user.id,
        int(region_id),
        exclude_potential=True,
        **_client_query_kwargs(data),
    )
    await state.set_state(VisitStates.select_client)
    city_line = f"\nМісто: <b>{city}</b>"
    subtitle = (
        f"Область: <b>{region_name}</b>{city_line}\n\nОберіть клієнта:"
        if clients
        else (
            f"Область: <b>{region_name}</b>{city_line}\n\n"
            "Оберіть клієнта або «Потенційний клієнт»:"
        )
    )
    await message.answer(
        f"{_visit_title(data)}\n\n{subtitle}",
        reply_markup=visit_clients_keyboard(clients, **_clients_back_kwargs(db_user)),
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
    await state.update_data(
        potential_photo_url=None,
        potential_creating=False,
        is_potential=True,
    )
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
    visit_task_type_service: VisitTaskTypeService,
) -> None:
    data = await state.get_data()
    if data.get("client_id"):
        return

    try:
        client = await client_service.create_potential(
            manager_id=db_user.id,
            region_id=int(data["region_id"]),
            name=data["potential_name"],
            address=data["potential_address"],
            photo_url=data.get("potential_photo_url"),
            city=data.get("city"),
            is_pvc=_visit_is_pvc(data),
        )
    except Exception:
        await _release_potential_client_create(state)
        logger.exception("Failed to create potential client for manager %s", db_user.id)
        error_text = "Не вдалося зберегти клієнта. Спробуйте ще раз."
        if isinstance(target, CallbackQuery):
            if target.message:
                await target.message.answer(error_text)
        else:
            await target.answer(error_text)
        return

    await state.update_data(
        client_id=client.id,
        client_name=client.name,
        is_potential=True,
        potential_creating=True,
    )
    await _continue_after_client(target, state, visit_task_type_service)


@router.message(VisitStates.potential_photo, F.photo)
async def potential_photo(
    message: Message,
    state: FSMContext,
    bot: Bot,
    db_user: User,
    client_service: ClientService,
    storage_service: StorageService,
    visit_task_type_service: VisitTaskTypeService,
) -> None:
    if not await _claim_potential_client_create(db_user.id, state):
        return

    try:
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
            message, state, db_user, client_service, visit_task_type_service
        )
    except Exception:
        logger.exception("Failed to upload potential client photo")
        await message.answer("Не вдалося завантажити фото. Спробуйте ще раз.")
    finally:
        data = await state.get_data()
        if not data.get("client_id"):
            await _release_potential_client_create(state)


@router.callback_query(
    VisitStates.potential_photo,
    F.data == "visit:potential:skip_photo",
)
async def potential_skip_photo(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    client_service: ClientService,
    visit_task_type_service: VisitTaskTypeService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    if not await _claim_potential_client_create(db_user.id, state):
        return
    try:
        await _finish_potential_and_select_type(
            callback, state, db_user, client_service, visit_task_type_service
        )
    finally:
        data = await state.get_data()
        if not data.get("client_id"):
            await _release_potential_client_create(state)


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
    visit_task_type_service: VisitTaskTypeService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    client_id = int(callback.data.split(":")[-1])
    client = await client_service.get_by_id(client_id)
    if client is None or client.manager_id != db_user.id:
        await callback.answer("Клієнт не знайдений", show_alert=True)
        return
    data = await state.get_data()
    if client.is_pvc != _visit_is_pvc(data):
        await callback.answer("Цей клієнт з іншої бази", show_alert=True)
        return

    await state.update_data(
        client_id=client_id,
        client_name=client.name,
        is_potential=client.is_potential,
    )
    await _continue_after_client(callback, state, visit_task_type_service)


@router.callback_query(
    VisitStates.select_visit_type,
    F.data.startswith("visit:type:"),
)
async def select_visit_type_legacy(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    region_service: RegionService,
) -> None:
    """Старі кнопки «тип візиту» після клієнта — тепер тип обирається на старті."""
    await callback.answer()
    if callback.message is None:
        return
    data = await state.get_data()
    if data.get("client_id"):
        return
    visit_type = callback.data.split(":")[-1]
    if visit_type not in {v.value for v in VisitType}:
        return
    await state.update_data(visit_type=visit_type, selected_tasks=[])
    await _show_regions(callback.message, state, db_user, region_service)


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
    if not selected_tasks and not data.get("is_potential"):
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
    await _show_regions(callback.message, state, db_user, region_service)


@router.callback_query(F.data == "visit:back:scope")
async def back_to_scope(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await state.set_state(VisitStates.select_visit_type)
    await callback.message.edit_text(
        "➕ <b>Новий візит</b>\n\nОберіть тип візиту:",
        reply_markup=visit_scope_keyboard(),
    )


@router.callback_query(F.data == "visit:back:city")
async def back_to_city(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    client_service: ClientService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    data = await state.get_data()
    if not data.get("region_id"):
        await callback.answer("Спочатку оберіть область", show_alert=True)
        return
    await _show_cities(callback.message, state, db_user, client_service)


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
async def back_to_type(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    client_service: ClientService,
) -> None:
    await back_to_client(callback, state, db_user, client_service)


@router.callback_query(F.data == "visit:back:comment")
async def back_to_comment(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return
    data = await state.get_data()
    await state.set_state(VisitStates.enter_comment)
    if data.get("is_potential"):
        await callback.message.edit_text(
            "Введіть коментар до візиту (або «-» щоб пропустити):",
        )
        return
    selected: list[str] = data.get("selected_tasks", [])
    await callback.message.edit_text(
        f"Задачі: {_tasks_text(selected)}\n\n"
        "Введіть коментар до візиту (або «-» щоб пропустити):",
    )
