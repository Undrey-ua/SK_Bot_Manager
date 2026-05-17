from aiogram.fsm.state import State, StatesGroup


class VisitStates(StatesGroup):
    select_client = State()
    select_visit_type = State()
    select_tasks = State()
    enter_comment = State()
    upload_photos = State()
