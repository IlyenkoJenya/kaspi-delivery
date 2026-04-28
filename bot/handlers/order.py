import asyncio
import re

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.inline import phone_confirm_keyboard, review_keyboard
from bot.services import kaspi_api
from bot.services.report import log_delivery, log_phone_update, log_review
from bot.services.review import generate_review
from bot.states.order_states import OrderFlow

order_router = Router()
MAX_SMS_ATTEMPTS = 3
_SMS_RE = re.compile(r"^\d{4}$")


@order_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(OrderFlow.waiting_order_id)
    await message.answer("Введите номер заказа Kaspi:")


@order_router.message(OrderFlow.waiting_order_id)
async def handle_order_id(message: Message, state: FSMContext) -> None:
    order_code = message.text.strip()
    await message.answer("Ищу заказ...")

    order, token = await asyncio.to_thread(kaspi_api.find_order, order_code)
    if not order:
        await message.answer("Заказ не найден. Проверьте номер и попробуйте снова.")
        return

    order_id = order["id"]
    customer = order["attributes"].get("customer", {})
    customer_name = customer.get("name") or (
        f"{customer.get('firstName', '')} {customer.get('lastName', '')}".strip()
    )

    product = await asyncio.to_thread(kaspi_api.get_order_product, order_id, token)

    ok, resp = await asyncio.to_thread(kaspi_api.send_delivery_code, order_id, order_code, token)
    if not ok:
        await message.answer(f"Ошибка при отправке кода клиенту:\n<code>{resp}</code>", parse_mode="HTML")
        return

    await state.update_data(
        order_code=order_code,
        order_id=order_id,
        token=token,
        customer_name=customer_name,
        product=product,
        sms_attempts=0,
    )
    await state.set_state(OrderFlow.waiting_sms_code)
    await message.answer(
        f"Заказ: {order_code}\n"
        f"Клиент: {customer_name}\n"
        f"Товар: {product}\n\n"
        "Код отправлен клиенту. Введите 4-значный SMS-код:"
    )


@order_router.message(OrderFlow.waiting_sms_code)
async def handle_sms_code(message: Message, state: FSMContext) -> None:
    code = message.text.strip()
    if not _SMS_RE.match(code):
        await message.answer("Код должен быть ровно 4 цифры. Попробуйте ещё раз:")
        return

    data = await state.get_data()
    attempts = data.get("sms_attempts", 0) + 1

    ok, resp = await asyncio.to_thread(
        kaspi_api.confirm_delivery,
        data["order_id"], data["order_code"], data["token"], code,
    )

    if ok:
        await _on_delivery_success(message, state, data)
        return

    if attempts >= MAX_SMS_ATTEMPTS:
        await state.clear()
        await message.answer(
            f"Превышено количество попыток ({MAX_SMS_ATTEMPTS}).\n"
            f"Ответ сервера: <code>{resp}</code>\n"
            "Начните заново: /start",
            parse_mode="HTML",
        )
        return

    await state.update_data(sms_attempts=attempts)
    await message.answer(f"Неверный код. Попытка {attempts}/{MAX_SMS_ATTEMPTS}. Попробуйте ещё раз:")


async def _on_delivery_success(message: Message, state: FSMContext, data: dict) -> None:
    user = message.from_user
    username = f"@{user.username}" if user.username else user.full_name
    log_delivery(data["order_code"], data["product"], data["customer_name"], username)
    await state.set_state(OrderFlow.waiting_phone_confirm)
    await message.answer(
        f"Заказ {data['order_code']} выдан!\n\nЗнаем реальный номер клиента?",
        reply_markup=phone_confirm_keyboard(),
    )


@order_router.callback_query(OrderFlow.waiting_phone_confirm, F.data == "phone_ok")
async def cb_phone_ok(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await _ask_for_review(callback.message, state)


@order_router.callback_query(OrderFlow.waiting_phone_confirm, F.data == "phone_changed")
async def cb_phone_changed(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await state.set_state(OrderFlow.waiting_phone_update)
    await callback.message.answer("Введите актуальный номер телефона клиента:")


@order_router.message(OrderFlow.waiting_phone_update)
async def handle_phone_update(message: Message, state: FSMContext) -> None:
    phone = message.text.strip()
    data = await state.get_data()
    log_phone_update(data["order_code"], phone)
    await message.answer(f"Номер {phone} сохранён.")
    await _ask_for_review(message, state)


async def _ask_for_review(message: Message, state: FSMContext) -> None:
    await state.set_state(OrderFlow.waiting_review_decision)
    await message.answer("Сгенерировать варианты отзыва?", reply_markup=review_keyboard())


@order_router.callback_query(OrderFlow.waiting_review_decision, F.data == "review_yes")
async def cb_review_yes(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Генерирую отзывы...")

    try:
        reviews = await generate_review(data.get("product", "товар"))
        user = callback.from_user
        username = f"@{user.username}" if user.username else user.full_name
        log_review(data["order_code"], data["product"], username)
        await callback.message.answer(reviews)
    except Exception as e:
        await callback.message.answer(f"Не удалось сгенерировать отзыв: {e}")

    await state.clear()


@order_router.callback_query(OrderFlow.waiting_review_decision, F.data == "review_no")
async def cb_review_no(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Выдача завершена.")
