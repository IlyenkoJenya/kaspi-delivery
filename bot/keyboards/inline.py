from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def phone_confirm_keyboard() -> InlineKeyboardMarkup:
    """'Is the phone current?' keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да, знаем", callback_data="phone_ok"),
                InlineKeyboardButton(text="Нет, не знаем", callback_data="phone_changed"),
            ]
        ]
    )


def review_keyboard() -> InlineKeyboardMarkup:
    """'Generate review?' keyboard — no Cancel button."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да", callback_data="review_yes"),
                InlineKeyboardButton(text="Нет", callback_data="review_no"),
            ]
        ]
    )
