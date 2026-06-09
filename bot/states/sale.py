from aiogram.fsm.state import State, StatesGroup


class SaleStates(StatesGroup):
    select_period = State()
    select_region = State()
    select_client = State()
    select_brand = State()
    enter_quantity = State()
    enter_comment = State()
