from aiogram.types import (
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_reply_kb() -> ReplyKeyboardMarkup:
    """Persistent bottom keyboard shown in the main menu."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💪 Тренировка"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="🏪 Магазин"), KeyboardButton(text="📊 Статистика")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def remove_reply_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def main_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="💪 Начать тренировку", callback_data="menu:workout")
    b.button(text="👤 Профиль", callback_data="menu:profile")
    b.button(text="🏪 Магазин", callback_data="menu:shop")
    b.adjust(1)
    return b.as_markup()


def subscribe_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="💳 Подписка на 1 месяц — 299 ₽", callback_data="sub:month")
    b.button(text="💳 Подписка на 3 месяца — 762 ₽", callback_data="sub:quarter")
    b.button(text="💳 Подписка на год — 2868 ₽", callback_data="sub:year")
    b.adjust(1)
    return b.as_markup()


def back_to_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🏠 Главное меню", callback_data="menu:main")
    b.adjust(1)
    return b.as_markup()
