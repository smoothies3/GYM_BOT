from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def exercise_card_kb(has_alternatives: bool = True) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Выполнено", callback_data="ex:done")
    if has_alternatives:
        b.button(text="🔄 Заменить", callback_data="ex:replace")
    b.button(text="🏁 Завершить тренировку", callback_data="ex:finish")
    b.adjust(2, 1)
    return b.as_markup()


def effort_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="😴 Легко", callback_data="effort:easy")
    b.button(text="💪 В точку", callback_data="effort:on_point")
    b.button(text="🔥 Тяжело", callback_data="effort:hard")
    b.adjust(3)
    return b.as_markup()


def rest_timer_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⏭ Пропустить отдых", callback_data="rest:skip")
    b.adjust(1)
    return b.as_markup()


_EQUIP_LABEL = {
    "barbell": "штанга",
    "dumbbell": "гантели",
    "machine": "тренажёр",
    "cable": "блок",
    "bodyweight": "без снаряда",
}


def alternatives_kb(alternatives: list[tuple[str, str, str]]) -> InlineKeyboardMarkup:
    """alternatives: list of (exercise_id, exercise_name, equipment)"""
    b = InlineKeyboardBuilder()
    for ex_id, name, equipment in alternatives:
        label = _EQUIP_LABEL.get(equipment, equipment)
        b.button(text=f"{name}  [{label}]", callback_data=f"alt:{ex_id}")
    b.button(text="↩ Назад", callback_data="alt:cancel")
    b.adjust(1)
    return b.as_markup()


def workout_summary_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🏠 Главное меню", callback_data="menu:main")
    b.button(text="👤 Профиль", callback_data="menu:profile")
    b.adjust(2)
    return b.as_markup()
