from aiogram.fsm.state import State, StatesGroup


class ReserveStates(StatesGroup):
    select_region = State()
    select_client = State()
    enter_material = State()
    enter_quantity = State()

