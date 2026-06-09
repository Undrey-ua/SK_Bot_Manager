from aiogram.fsm.state import State, StatesGroup


class ClientFormStates(StatesGroup):
    name = State()
    region = State()
    address = State()
    city = State()
    comment = State()
    stands = State()
