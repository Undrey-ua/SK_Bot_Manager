from aiogram.fsm.state import State, StatesGroup


class AdminStandStates(StatesGroup):
    add_name = State()
