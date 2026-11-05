from aiogram.fsm.state import State, StatesGroup


class TaskStates(StatesGroup):
    pick_assignee = State()
    enter_title = State()
    pick_weekday = State()
    enter_deadline = State()
    enter_comment = State()
    extend_deadline = State()

