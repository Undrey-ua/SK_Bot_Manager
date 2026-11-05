import logging
from datetime import date

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.inline import back_to_menu_keyboard
from bot.keyboards.tasks import (
    WEEKDAYS_UA,
    task_actions_keyboard,
    task_assignees_keyboard,
    tasks_hub_keyboard,
    tasks_list_keyboard,
    weekday_pick_keyboard,
)
from bot.notifications.task_assign import notify_task_assigned
from bot.services.task import TaskService
from bot.services.user import UserService
from bot.states.tasks import TaskStates
from bot.utils.roles import is_leader
from database.models import MANAGER_TASK_KIND_LABELS, ManagerTaskKind, Task, User

logger = logging.getLogger(__name__)
router = Router(name="tasks")


def _hub_title(user: User) -> str:
    if is_leader(user):
        return "📝 <b>Задачі</b>"
    return "📝 <b>Мої завдання</b>"


def _hub_markup(user: User):
    return tasks_hub_keyboard(for_leader=is_leader(user))


async def _create_leader_tasks(
    *,
    db_user: User,
    data: dict,
    title: str,
    deadline: date | None,
    weekday: int | None,
    comment: str | None,
    task_service: TaskService,
    user_service: UserService,
) -> list[tuple[Task, User]]:
    raw_ids = data.get("assignee_ids") or []
    try:
        wanted = {int(item) for item in raw_ids}
    except (TypeError, ValueError):
        return []
    managers = [manager for manager in await user_service.list_regional_managers() if manager.id in wanted]
    created: list[tuple[Task, User]] = []
    for manager in managers:
        task = await task_service.create(
            assignee_id=manager.id,
            created_by_id=db_user.id,
            title=title,
            deadline=deadline,
            weekday=weekday,
            comment=comment,
        )
        created.append((task, manager))
    return created


async def _notify_assignees(bot: Bot, created: list[tuple[Task, User]], creator: User) -> None:
    for task, assignee in created:
        try:
            await notify_task_assigned(
                bot_token=bot.token,
                task=task,
                assignee=assignee,
                creator=creator,
            )
        except Exception:
            logger.exception("Failed to notify assignee about task #%s", task.id)


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
async def tasks_hub(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await state.clear()
    await callback.message.edit_text(_hub_title(db_user), reply_markup=_hub_markup(db_user))


@router.callback_query(F.data.startswith("tasks:list:"))
async def tasks_list(callback: CallbackQuery, db_user: User, task_service: TaskService) -> None:
    await callback.answer()
    if callback.message is None:
        return
    raw = callback.data.split(":")[-1]
    weekday = None if raw == "all" else int(raw)
    tasks = await task_service.list_for_user(db_user.id, weekday=weekday)
    if not tasks:
        await callback.message.edit_text("📝 Немає задач.", reply_markup=_hub_markup(db_user))
        return
    await callback.message.edit_text("📝 <b>Список задач</b>\n\nОберіть:", reply_markup=tasks_list_keyboard(tasks))


@router.callback_query(F.data == "tasks:new")
async def tasks_new(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    user_service: UserService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await state.clear()
    if is_leader(db_user):
        managers = await user_service.list_regional_managers()
        if not managers:
            await callback.message.edit_text(
                "Немає менеджерів, яким можна призначити задачу.",
                reply_markup=_hub_markup(db_user),
            )
            return
        await state.set_state(TaskStates.pick_assignee)
        await callback.message.edit_text(
            "Оберіть менеджера:",
            reply_markup=task_assignees_keyboard(managers),
        )
        return
    await state.set_state(TaskStates.enter_title)
    await callback.message.edit_text("Введіть текст задачі:")


@router.callback_query(TaskStates.pick_assignee, F.data.startswith("tasks:assignee:"))
async def tasks_pick_assignee(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    user_service: UserService,
) -> None:
    if callback.message is None:
        await callback.answer()
        return
    if not is_leader(db_user):
        await callback.answer("Немає доступу", show_alert=True)
        return
    managers = await user_service.list_regional_managers()
    raw = (callback.data or "").split(":")[-1]
    if raw == "all":
        assignee_ids = [manager.id for manager in managers]
        if not assignee_ids:
            await callback.answer()
            await callback.message.edit_text(
                "Немає менеджерів, яким можна призначити задачу.",
                reply_markup=_hub_markup(db_user),
            )
            await state.clear()
            return
        await state.update_data(assignee_ids=assignee_ids, assign_all=True)
    else:
        try:
            manager_id = int(raw)
        except ValueError:
            await callback.answer("Менеджера не знайдено", show_alert=True)
            return
        if manager_id not in {manager.id for manager in managers}:
            await callback.answer("Менеджера не знайдено", show_alert=True)
            return
        await state.update_data(assignee_ids=[manager_id], assign_all=False)
    await callback.answer()
    await state.set_state(TaskStates.enter_title)
    await callback.message.edit_text("Введіть опис задачі:")


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
    bot: Bot,
    db_user: User,
    task_service: TaskService,
    user_service: UserService,
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
    if is_leader(db_user):
        created = await _create_leader_tasks(
            db_user=db_user,
            data=data,
            title=title,
            deadline=deadline,
            weekday=weekday,
            comment=comment,
            task_service=task_service,
            user_service=user_service,
        )
        if not created:
            await message.answer(
                "Не вдалося визначити менеджера. Почніть спочатку.",
                reply_markup=_hub_markup(db_user),
            )
            await state.clear()
            return
        await state.clear()
        lines = "\n".join(f"• {assignee.name} — #{task.id}" for task, assignee in created)
        prefix = "всім менеджерам" if data.get("assign_all") else "менеджеру"
        await message.answer(
            f"✅ Задачу додано {prefix}:\n{lines}",
            reply_markup=_hub_markup(db_user),
        )
        await _notify_assignees(bot, created, db_user)
        return
    task = await task_service.create(
        assignee_id=db_user.id,
        created_by_id=db_user.id,
        title=title,
        deadline=deadline,
        weekday=weekday,
        comment=comment,
    )
    await state.clear()
    await message.answer(f"✅ Задачу #{task.id} додано.", reply_markup=_hub_markup(db_user))


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
    await callback.message.edit_text("✅ Задачу відмічено як виконану.", reply_markup=_hub_markup(db_user))


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
    await message.answer("⏩ Дедлайн оновлено.", reply_markup=_hub_markup(db_user))

