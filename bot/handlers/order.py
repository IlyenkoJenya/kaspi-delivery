import asyncio
import re

from aiogram import Bot, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.agent.delivery_session import KaspiDeliverySession
from bot.keyboards.inline import phone_confirm_keyboard, review_keyboard
from bot.services.report import log_delivery, log_phone_update, log_review
from bot.services.review import generate_review
from bot.states.order_states import OrderFlow

order_router = Router()

# user_id → active Playwright session
active_sessions: dict[int, KaspiDeliverySession] = {}

SMS_CODE_RE = re.compile(r"^\d{4}$")


# ── /start ────────────────────────────────────────────────────────────────────

@order_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    session = active_sessions.pop(user_id, None)
    if session:
        session.cancel()
    await state.clear()
    await state.set_state(OrderFlow.waiting_order_id)
    await message.answer("Введите номер заказа Kaspi:")


# ── Ввод order_id ─────────────────────────────────────────────────────────────

@order_router.message(OrderFlow.waiting_order_id)
async def handle_order_id(message: Message, state: FSMContext, bot: Bot) -> None:
    order_id = message.text.strip()
    user_id = message.from_user.id
    chat_id = message.chat.id

    async def notify(text: str) -> None:
        await bot.send_message(chat_id, text)

    session = KaspiDeliverySession(user_id, notify)
    active_sessions[user_id] = session

    await message.answer(
        "🔄 Подключаюсь к Kaspi и получаю данные заказа...\n"
        "Это займёт ~30 секунд. Можно ввести /cancel для отмены."
    )
    await session.start(order_id)

    try:
        order_info = await asyncio.wait_for(session.order_info_queue.get(), timeout=120)
    except asyncio.TimeoutError:
        active_sessions.pop(user_id, None)
        await state.clear()
        await message.answer("⏰ Таймаут подключения к Kaspi. Попробуйте снова (/start).")
        return

    if order_info is None:
        active_sessions.pop(user_id, None)
        await state.clear()
        await message.answer(
            "❌ Заказ не найден или ошибка подключения.\n"
            "Проверьте номер заказа и попробуйте снова (/start)."
        )
        return

    await state.update_data(
        order_id=order_id,
        product=order_info["product"],
        client_name=order_info.get("client_name", ""),
        client_phone=order_info.get("phone", ""),
    )

    info_text = (
        f"📦 Заказ #{order_id}\n"
        f"🛍 Товар: {order_info['product']}\n"
        f"👤 Клиент: {order_info['client_name']}"
    )

    if order_info.get("error") == "no_deliver_btn":
        active_sessions.pop(user_id, None)
        await state.clear()
        await message.answer(
            f"{info_text}\n\n"
            "⚠️ Кнопка 'Выдать заказ' недоступна.\n"
            "Возможно заказ уже выдан или имеет другой статус."
        )
        return

    if order_info.get("has_phone", True):
        await state.set_state(OrderFlow.waiting_code)
        await message.answer(
            f"{info_text}\n\n"
            "📲 SMS с кодом отправлен клиенту!\n"
            "Введите 4-значный код из SMS клиента:"
        )
    else:
        await state.set_state(OrderFlow.waiting_phone)
        await message.answer(
            f"{info_text}\n\n"
            "📵 Телефон клиента не указан.\n"
            "Введите номер телефона клиента:"
        )


# ── Ввод SMS-кода (Path A) ────────────────────────────────────────────────────

@order_router.message(OrderFlow.waiting_code)
async def handle_code(message: Message, state: FSMContext, bot: Bot) -> None:
    code = message.text.strip()
    user_id = message.from_user.id

    if not SMS_CODE_RE.match(code):
        await message.answer("❗ Код должен быть ровно 4 цифры. Попробуйте ещё раз:")
        return

    session = active_sessions.get(user_id)
    if not session:
        await state.clear()
        await message.answer("❌ Сессия не найдена. Начните заново: /start")
        return

    await session.sms_code_queue.put(code)

    data = await state.get_data()
    if data.get("awaiting_delivery"):
        await message.answer("⏳ Проверяю код...")
        return

    await state.update_data(awaiting_delivery=True)
    await message.answer("⏳ Ввожу код в Kaspi, подтверждаю выдачу...")

    try:
        success = await asyncio.wait_for(session.delivery_done_queue.get(), timeout=1_000)
    except asyncio.TimeoutError:
        active_sessions.pop(user_id, None)
        await state.clear()
        await message.answer("⏰ Таймаут. Проверьте статус заказа вручную.")
        return

    active_sessions.pop(user_id, None)

    if not success:
        await state.clear()
        await message.answer(
            "❌ Не удалось подтвердить выдачу.\n"
            "Проверьте вручную: https://kaspi.kz/mc/#/orders-new?status=DELIVERY"
        )
        return

    await _on_delivery_success(message, state)


# ── Ввод телефона (Path B: нет телефона в заказе) ─────────────────────────────

@order_router.message(OrderFlow.waiting_phone)
async def handle_phone(message: Message, state: FSMContext, bot: Bot) -> None:
    phone = message.text.strip()
    user_id = message.from_user.id

    session = active_sessions.get(user_id)
    if not session:
        await state.clear()
        await message.answer("❌ Сессия не найдена. Начните заново: /start")
        return

    await message.answer(f"📞 Телефон {phone} получен. Подтверждаю заказ...")
    await session.phone_queue.put(phone)

    try:
        success = await asyncio.wait_for(session.delivery_done_queue.get(), timeout=120)
    except asyncio.TimeoutError:
        active_sessions.pop(user_id, None)
        await state.clear()
        await message.answer("⏰ Таймаут. Проверьте статус заказа вручную.")
        return

    active_sessions.pop(user_id, None)

    if not success:
        await state.clear()
        await message.answer(
            "❌ Не удалось подтвердить выдачу.\n"
            "Проверьте вручную: https://kaspi.kz/mc/#/orders-new?status=DELIVERY"
        )
        return

    await state.update_data(client_phone=phone)
    await _on_delivery_success(message, state)


# ── Проверка актуальности телефона ────────────────────────────────────────────

@order_router.callback_query(OrderFlow.waiting_phone_confirm, lambda c: c.data == "phone_ok")
async def cb_phone_ok(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await _ask_for_review(callback.message, state)


@order_router.callback_query(OrderFlow.waiting_phone_confirm, lambda c: c.data == "phone_changed")
async def cb_phone_changed(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await state.set_state(OrderFlow.waiting_phone_update)
    await callback.message.answer("📞 Введите актуальный номер телефона клиента:")


@order_router.message(OrderFlow.waiting_phone_update)
async def handle_phone_update(message: Message, state: FSMContext) -> None:
    new_phone = message.text.strip()
    data = await state.get_data()
    order_id = data.get("order_id", "")
    await state.update_data(client_phone=new_phone)
    log_phone_update(order_id, new_phone)
    await message.answer(f"✅ Номер {new_phone} сохранён.")
    await _ask_for_review(message, state)


# ── Генерация отзыва ──────────────────────────────────────────────────────────

@order_router.callback_query(OrderFlow.waiting_review_decision, lambda c: c.data == "review_yes")
async def cb_review_yes(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    product = data.get("product", "товар")
    order_id = data.get("order_id", "")
    user_id = callback.from_user.id

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("✍️ Генерирую отзывы, подождите...")

    try:
        reviews = await generate_review(product)
        await callback.message.answer(reviews)
        user = callback.from_user
        username = f"@{user.username}" if user.username else user.full_name
        log_review(order_id, product, username)
    except Exception as e:
        await callback.message.answer(f"⚠️ Не удалось сгенерировать отзыв: {e}")

    await state.clear()
    await callback.answer()


@order_router.callback_query(OrderFlow.waiting_review_decision, lambda c: c.data == "review_no")
async def cb_review_no(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("✅ Выдача завершена.")
    await callback.answer()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _on_delivery_success(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    user = message.from_user if hasattr(message, "from_user") else None
    username = f"@{user.username}" if (user and user.username) else (user.full_name if user else "")
    log_delivery(
        order_id=data.get("order_id", ""),
        product=data.get("product", ""),
        client_name=data.get("client_name", ""),
        username=username,
    )
    await _ask_phone_confirm(message, state)


async def _ask_phone_confirm(message: Message, state: FSMContext) -> None:
    await state.set_state(OrderFlow.waiting_phone_confirm)
    await message.answer(
        "🎉 Заказ выдан!\n\nЗнаем реальный номер клиента?",
        reply_markup=phone_confirm_keyboard(),
    )


async def _ask_for_review(message: Message, state: FSMContext) -> None:
    await state.set_state(OrderFlow.waiting_review_decision)
    await message.answer(
        "Сгенерировать варианты отзыва для клиента?",
        reply_markup=review_keyboard(),
    )
