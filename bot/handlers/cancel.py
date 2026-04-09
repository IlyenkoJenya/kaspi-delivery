from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

cancel_router = Router()

CANCEL_MSG = "🚫 Действие отменено. Введите /start чтобы начать заново."


@cancel_router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    from bot.handlers.order import active_sessions
    user_id = message.from_user.id
    session = active_sessions.pop(user_id, None)
    if session:
        session.cancel()
    await state.clear()
    await message.answer(CANCEL_MSG)


@cancel_router.callback_query(lambda c: c.data == "cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    from bot.handlers.order import active_sessions
    user_id = callback.from_user.id
    session = active_sessions.pop(user_id, None)
    if session:
        session.cancel()
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(CANCEL_MSG)
    await callback.answer()
