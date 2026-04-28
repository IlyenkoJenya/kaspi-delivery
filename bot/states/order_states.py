from aiogram.fsm.state import State, StatesGroup


class OrderFlow(StatesGroup):
    waiting_order_id = State()
    waiting_sms_code = State()
    waiting_phone_confirm = State()
    waiting_phone_update = State()
    waiting_review_decision = State()
