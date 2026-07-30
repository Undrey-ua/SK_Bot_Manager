from aiogram.fsm.state import State, StatesGroup


class VisitStates(StatesGroup):
    select_region = State()
    select_client = State()
    select_potential_client = State()
    potential_name = State()
    potential_address = State()
    potential_photo = State()
    select_visit_type = State()
    select_tasks = State()
    enter_comment = State()
    upload_photos = State()
