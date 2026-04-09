from aiogram.fsm.state import State, StatesGroup


class OrderFlow(StatesGroup):
    waiting_order_id = State()
    waiting_code = State()
    waiting_phone = State()          # Path B: no phone in order
    waiting_phone_confirm = State()  # After delivery: "Is this phone current?"
    waiting_phone_update = State()   # After "No": enter new phone
    waiting_review_decision = State()
