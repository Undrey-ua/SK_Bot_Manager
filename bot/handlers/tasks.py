import logging
from datetime import date, datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.inline import back_to_menu_keyboard
from bot.keyboards.tasks import (
    WEEKDAYS_UA,
    task_actions_keyboard,
    tasks_hub_keyboard,
    tasks_list_keyboard,
    weekday_pick_keyboard,
)
from bot.services.task import TaskService
from bot.states.tasks import TaskStates
from database.models import MANAGER_TASK_KIND_LABELS, ManagerTaskKind, User

logger = logging.getLogger(__name__)
router = Router(name="tasks")


def _task_text(t) -> str:
    dl = t.deadline.isoformat() if t.deadline else "—"
    wd = WEEKDAYS_UA[t.weekday] if t.weekday is not None else "—"
    creator = t.created_by.name if t.created_by else "—"
    try:
        kind_label = MANAGER_TASK_KIND_LABELS[ManagerTaskKind(t.kind)]
    except (ValueError, KeyError, AttributeError):
        kind_label = MANAGER_TASK_KIND_LABELS[ManagerTaskKind.GENERAL]
    return (
        f"📝 <b>Задача #{t.id}</b>\n\n"
        f"{t.title}\n\n"
        f"Тип: {kind_label}\n"
        f"Дедлайн: {dl}\n"
        f"День нагадування: {wd}\n"
        f"Від: {creator}\n"
        f"Коментар: {t.comment or '—'}"
    )


@router.callback_query(F.data == "tasks:hub")
async def tasks_hub(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await state.clear()
    await callback.message.edit_text("📝 <b>Мої завдання</b>", reply_markup=tasks_hub_keyboard())


@router.callback_query(F.data.startswith("tasks:list:"))
async def tasks_list(callback: CallbackQuery, db_user: User, task_service: TaskService) -> None:
    await callback.answer()
    if callback.message is None:
        return
    raw = callback.data.split(":")[-1]
    weekday = None if raw == "all" else int(raw)
    tasks = await task_service.list_for_user(db_user.id, weekday=weekday)
    if not tasks:
        await callback.message.edit_text("📝 Немає задач.", reply_markup=tasks_hub_keyboard())
        return
    await callback.message.edit_text("📝 <b>Список задач</b>\n\nОберіть:", reply_markup=tasks_list_keyboard(tasks))


@router.callback_query(F.data == "tasks:new")
async def tasks_new(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await state.clear()
    await state.set_state(TaskStates.enter_title)
    await callback.message.edit_text("Введіть текст задачі:")


@router.message(TaskStates.enter_title, F.text)
async def tasks_enter_title(message: Message, state: FSMContext) -> None:
    title = message.text.strip()
    if not title:
        await message.answer("Введіть текст задачі.")
        return
    await state.update_data(title=title)
    await state.set_state(TaskStates.pick_weekday)
    await message.answer("Обрати день нагадування (необовʼязково):", reply_markup=weekday_pick_keyboard())


@router.callback_query(TaskStates.pick_weekday, F.data.startswith("tasks:weekday:"))
async def tasks_pick_weekday(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return
    raw = callback.data.split(":")[-1]
    if raw == "skip":
        await state.update_data(weekday=None)
    else:
        await state.update_data(weekday=int(raw))
    await state.set_state(TaskStates.enter_deadline)
    await callback.message.edit_text(
        "Введіть дедлайн у форматі <code>YYYY-MM-DD</code> або «-» щоб пропустити:",
    )


@router.message(TaskStates.enter_deadline, F.text)
async def tasks_enter_deadline(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    deadline = None
    if raw != "-":
        try:
            deadline = date.fromisoformat(raw)
        except ValueError:
            await message.answer("Невірний формат. Приклад: 2026-05-26 або «-»")
            return
    await state.update_data(deadline=deadline.isoformat() if deadline else None)
    await state.set_state(TaskStates.enter_comment)
    await message.answer("Коментар (необовʼязково) або «-»:")


@router.message(TaskStates.enter_comment, F.text)
async def tasks_enter_comment(
    message: Message,
    state: FSMContext,
    db_user: User,
    task_service: TaskService,
) -> None:
    comment = message.text.strip()
    if comment == "-":
        comment = None
    data = await state.get_data()
    title = data.get("title")
    if not title:
        await message.answer("Дані втрачено.", reply_markup=back_to_menu_keyboard())
        await state.clear()
        return
    deadline = date.fromisoformat(data["deadline"]) if data.get("deadline") else None
    weekday = data.get("weekday")
    task = await task_service.create(
        assignee_id=db_user.id,
        created_by_id=db_user.id,
        title=title,
        deadline=deadline,
        weekday=weekday,
        comment=comment,
    )
    await state.clear()
    await message.answer(f"✅ Задачу #{task.id} додано.", reply_markup=tasks_hub_keyboard())


@router.callback_query(F.data.startswith("tasks:show:"))
async def task_show(callback: CallbackQuery, db_user: User, task_service: TaskService) -> None:
    await callback.answer()
    if callback.message is None:
        return
    tid = int(callback.data.split(":")[-1])
    t = await task_service.get_by_id(tid)
    if t is None or t.assignee_id != db_user.id:
        await callback.answer("Задачу не знайдено", show_alert=True)
        return
    is_overdue = bool(t.deadline and t.deadline < date.today() and t.completed_at is None)
    await callback.message.edit_text(_task_text(t), reply_markup=task_actions_keyboard(t.id, is_overdue=is_overdue))


@router.callback_query(F.data.startswith("tasks:done:"))
async def task_done(callback: CallbackQuery, db_user: User, task_service: TaskService) -> None:
    await callback.answer()
    if callback.message is None:
        return
    tid = int(callback.data.split(":")[-1])
    t = await task_service.get_by_id(tid)
    if t is None or t.assignee_id != db_user.id:
        await callback.answer("Задачу не знайдено", show_alert=True)
        return
    await task_service.complete(tid)
    await callback.message.edit_text("✅ Задачу відмічено як виконану.", reply_markup=tasks_hub_keyboard())


@router.callback_query(F.data.startswith("tasks:extend:"))
async def task_extend_start(callback: CallbackQuery, state: FSMContext, db_user: User, task_service: TaskService) -> None:
    await callback.answer()
    if callback.message is None:
        return
    tid = int(callback.data.split(":")[-1])
    t = await task_service.get_by_id(tid)
    if t is None or t.assignee_id != db_user.id:
        await callback.answer("Задачу не знайдено", show_alert=True)
        return
    await state.clear()
    await state.update_data(task_id=tid)
    await state.set_state(TaskStates.extend_deadline)
    await callback.message.edit_text(
        "Введіть новий дедлайн <code>YYYY-MM-DD</code> (можна додати коментар після пробілу):\n"
        "Напр: <code>2026-06-10</code> або <code>2026-06-10 перенесли через відпустку</code>"
    )


@router.message(TaskStates.extend_deadline, F.text)
async def task_extend_apply(message: Message, state: FSMContext, db_user: User, task_service: TaskService) -> None:
    data = await state.get_data()
    tid = data.get("task_id")
    if not tid:
        await message.answer("Дані втрачено.", reply_markup=back_to_menu_keyboard())
        await state.clear()
        return
    parts = message.text.strip().split(" ", 1)
    try:
        new_deadline = date.fromisoformat(parts[0])
    except ValueError:
        await message.answer("Невірний формат. Приклад: 2026-06-10")
        return
    comment = parts[1].strip() if len(parts) > 1 else None
    t = await task_service.get_by_id(int(tid))
    if t is None or t.assignee_id != db_user.id:
        await message.answer("Задачу не знайдено.")
        await state.clear()
        return
    await task_service.set_deadline(int(tid), new_deadline, comment)
    await state.clear()
    await message.answer("⏩ Дедлайн оновлено.", reply_markup=tasks_hub_keyboard())

