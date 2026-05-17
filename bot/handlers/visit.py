import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.inline import (
    back_to_menu_keyboard,
    clients_keyboard,
    main_menu_keyboard,
    photos_keyboard,
    tasks_keyboard,
    visit_type_keyboard,
)
from bot.services.client import ClientService
from bot.services.storage import StorageService
from bot.services.visit import VisitService
from bot.states.visit import VisitStates
from database.models import (
    TASK_LABELS,
    VISIT_TYPE_LABELS,
    TaskType,
    User,
    VisitType,
)

logger = logging.getLogger(__name__)
router = Router(name="visit")


@router.callback_query(F.data == "visit:new")
async def start_visit(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    client_service: ClientService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    clients = await client_service.list_by_manager(db_user.id)
    if not clients:
        await callback.message.edit_text(
            "Неможливо створити візит — немає клієнтів.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await state.clear()
    await state.set_state(VisitStates.select_client)
    await callback.message.edit_text(
        "➕ <b>Новий візит</b>\n\nОберіть клієнта:",
        reply_markup=clients_keyboard(clients),
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
    await callback.message.edit_text(
        f"Клієнт: <b>{client.name}</b>\n\nОберіть тип візиту:",
        reply_markup=visit_type_keyboard(),
    )


@router.callback_query(
    VisitStates.select_visit_type,
    F.data.startswith("visit:type:"),
)
async def select_visit_type(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return

    visit_type = callback.data.split(":")[-1]
    await state.update_data(visit_type=visit_type, selected_tasks=[])
    await state.set_state(VisitStates.select_tasks)
    await callback.message.edit_text(
        f"Тип: <b>{VISIT_TYPE_LABELS[VisitType(visit_type)]}</b>\n\n"
        "Оберіть задачі (можна кілька):",
        reply_markup=tasks_keyboard(set()),
    )


@router.callback_query(
    VisitStates.select_tasks,
    F.data.startswith("visit:task:"),
)
async def toggle_task(callback: CallbackQuery, state: FSMContext) -> None:
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
    await callback.message.edit_reply_markup(
        reply_markup=tasks_keyboard(selected),
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

    tasks_text = ", ".join(TASK_LABELS[TaskType(t)] for t in selected)
    await state.set_state(VisitStates.enter_comment)
    await callback.message.edit_text(
        f"Задачі: {tasks_text}\n\n"
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
        "📷 Надішліть фото візиту.\n"
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
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    data = await state.get_data()
    photo_urls: list[str] = data.get("photo_urls", [])
    if not photo_urls:
        await callback.answer("Додайте хоча б одне фото", show_alert=True)
        return

    visit = await visit_service.create_visit(
        manager_id=db_user.id,
        client_id=data["client_id"],
        visit_type=data["visit_type"],
        comment=data.get("comment"),
        tasks=data.get("selected_tasks", []),
        photo_urls=photo_urls,
    )

    await state.clear()
    visit_label = VISIT_TYPE_LABELS[VisitType(data["visit_type"])]
    await callback.message.edit_text(
        f"✅ <b>Візит #{visit.id} збережено</b>\n\n"
        f"Клієнт: {data['client_name']}\n"
        f"Тип: {visit_label}\n"
        f"Фото: {len(photo_urls)}",
        reply_markup=back_to_menu_keyboard(),
    )
    logger.info("Visit %s created by user %s", visit.id, db_user.id)


# --- navigation back ---

@router.callback_query(F.data == "visit:back:client")
async def back_to_client(callback: CallbackQuery, state: FSMContext, db_user: User, client_service: ClientService) -> None:
    await callback.answer()
    if callback.message is None:
        return
    clients = await client_service.list_by_manager(db_user.id)
    await state.set_state(VisitStates.select_client)
    await callback.message.edit_text(
        "➕ <b>Новий візит</b>\n\nОберіть клієнта:",
        reply_markup=clients_keyboard(clients),
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
    tasks_text = ", ".join(TASK_LABELS[TaskType(t)] for t in selected)
    await state.set_state(VisitStates.enter_comment)
    await callback.message.edit_text(
        f"Задачі: {tasks_text}\n\n"
        "Введіть коментар до візиту (або «-» щоб пропустити):",
    )
