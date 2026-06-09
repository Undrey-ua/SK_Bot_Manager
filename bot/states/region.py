from aiogram.fsm.state import State, StatesGroup


class RegionAddStates(StatesGroup):
    name = State()
