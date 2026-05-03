from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def gender_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="👨 Мужской", callback_data="ob_gender:male")
    b.button(text="👩 Женский", callback_data="ob_gender:female")
    b.adjust(2)
    return b.as_markup()


def goal_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="💪 Набор массы", callback_data="ob_goal:mass")
    b.button(text="🔥 Похудение", callback_data="ob_goal:cut")
    b.button(text="✨ Тонус и форма", callback_data="ob_goal:tone")
    b.adjust(1)
    return b.as_markup()


def level_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🌱 Новичок (до 6 мес)", callback_data="ob_level:beginner")
    b.button(text="🏃 Средний (6 мес — 2 года)", callback_data="ob_level:mid")
    b.button(text="🏋️ Продвинутый (2+ года)", callback_data="ob_level:adv")
    b.adjust(1)
    return b.as_markup()


def days_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="2 дня", callback_data="ob_days:2")
    b.button(text="3 дня", callback_data="ob_days:3")
    b.button(text="4 дня", callback_data="ob_days:4")
    b.button(text="5 дней", callback_data="ob_days:5")
    b.adjust(2)
    return b.as_markup()
