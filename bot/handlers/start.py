from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.common import main_menu_kb, main_reply_kb, remove_reply_kb
from bot.keyboards.onboarding import days_kb, gender_kb, goal_kb, level_kb
from bot.phrases import p
from bot.services.gamification import check_and_grant_badges
from bot.services.user_service import get_or_create_user, update_user
from bot.services.workout_service import get_active_session
from bot.states.fsm import OnboardingFSM, WorkoutFSM

router = Router()

AVATAR = {1: "🧍", 5: "🚶", 10: "🏃", 25: "🏋️", 50: "💪", 100: "🦁", 250: "⚡"}


def avatar_emoji(level: int) -> str:
    for threshold in sorted(AVATAR.keys(), reverse=True):
        if level >= threshold:
            return AVATAR[threshold]
    return "🧍"


def _active_workout_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="▶️ Продолжить тренировку", callback_data="workout:resume")
    b.button(text="❌ Завершить тренировку", callback_data="workout:abort")
    b.adjust(1)
    return b.as_markup()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, session: AsyncSession):
    user = await get_or_create_user(session, message.from_user)

    # Already onboarded
    if user.fitness_level and user.goal and user.gender:
        # Check for active workout — don't interrupt it silently
        current_state = await state.get_state()
        active = await get_active_session(session, user.id)
        if active or current_state in (
            WorkoutFSM.exercise_card,
            WorkoutFSM.rating_effort,
            WorkoutFSM.rest_timer,
            WorkoutFSM.replacing,
        ):
            await message.answer(
                "⚠️ У тебя идёт тренировка. Продолжить или завершить?",
                reply_markup=_active_workout_kb(),
            )
            return

        emoji = avatar_emoji(user.level)
        await message.answer(
            f"{emoji} Привет, {user.first_name}!\n\n"
            f"Уровень {user.level} · {user.xp_total} XP · {user.fitcoin_balance} FC\n"
            f"Стрик: {user.streak_weeks} нед.",
            reply_markup=main_reply_kb(),
        )
        return

    await state.clear()
    await message.answer(p("onboarding_welcome", name=message.from_user.first_name))
    await message.answer(p("onboarding_ask_gender"), reply_markup=gender_kb())
    await state.set_state(OnboardingFSM.gender)


@router.callback_query(OnboardingFSM.gender, F.data.startswith("ob_gender:"))
async def ob_gender(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    gender = call.data.split(":")[1]
    await state.update_data(gender=gender)
    await call.message.edit_text(p("onboarding_ask_goal"), reply_markup=goal_kb())
    await state.set_state(OnboardingFSM.goal)
    await call.answer()


@router.callback_query(OnboardingFSM.goal, F.data.startswith("ob_goal:"))
async def ob_goal(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    goal = call.data.split(":")[1]
    await state.update_data(goal=goal)
    await call.message.edit_text(p("onboarding_ask_level"), reply_markup=level_kb())
    await state.set_state(OnboardingFSM.level)
    await call.answer()


@router.callback_query(OnboardingFSM.level, F.data.startswith("ob_level:"))
async def ob_level(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    level = call.data.split(":")[1]
    await state.update_data(fitness_level=level)
    await call.message.edit_text(p("onboarding_ask_days"), reply_markup=days_kb())
    await state.set_state(OnboardingFSM.days)
    await call.answer()


@router.callback_query(OnboardingFSM.days, F.data.startswith("ob_days:"))
async def ob_days(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    days = int(call.data.split(":")[1])
    data = await state.get_data()
    await state.clear()

    user = await get_or_create_user(session, call.from_user)
    await update_user(
        session,
        user,
        gender=data["gender"],
        goal=data["goal"],
        fitness_level=data["fitness_level"],
        days_per_week=days,
    )

    # Grant onboarding badge
    from bot.models.log import Badge, UserBadge
    from sqlalchemy import select
    badge_result = await session.execute(select(Badge).where(Badge.code == "onboarded"))
    badge = badge_result.scalar_one_or_none()
    if badge:
        from bot.services.gamification import _has_badge
        if not await _has_badge(session, user, "onboarded"):
            session.add(UserBadge(user_id=user.id, badge_id=badge.id))
            await session.commit()

    await call.message.edit_text(p("onboarding_done"), reply_markup=main_menu_kb())
    await call.answer()


# ── Main menu navigation ─────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:main")
async def menu_main(call: CallbackQuery, session: AsyncSession):
    user = await get_or_create_user(session, call.from_user)
    emoji = avatar_emoji(user.level)
    await call.message.answer(
        f"{emoji} {user.first_name}\n\n"
        f"Уровень {user.level} · {user.xp_total} XP · {user.fitcoin_balance} FC\n"
        f"Стрик: {user.streak_weeks} нед.",
        reply_markup=main_reply_kb(),
    )
    await call.answer()


# ── Reply keyboard button handlers ───────────────────────────────────────────

@router.message(F.text == "💪 Тренировка")
async def reply_workout(message: Message, state: FSMContext, session: AsyncSession):
    from aiogram.types import CallbackQuery as CQ
    # Delegate to the workout handler by simulating the menu:workout flow
    user = await get_or_create_user(session, message.from_user)
    current_state = await state.get_state()
    if current_state in (
        WorkoutFSM.exercise_card,
        WorkoutFSM.rating_effort,
        WorkoutFSM.rest_timer,
        WorkoutFSM.replacing,
    ):
        await message.answer(
            "⚠️ У тебя идёт тренировка. Продолжить или завершить?",
            reply_markup=_active_workout_kb(),
        )
        return
    # Forward to workout start — import here to avoid circular
    from bot.handlers.workout import start_workout_from_message
    await start_workout_from_message(message, state, session, user)


@router.message(F.text == "👤 Профиль")
async def reply_profile(message: Message, session: AsyncSession):
    from bot.handlers.profile import show_profile_message
    await show_profile_message(message, session)


@router.message(F.text == "🏪 Магазин")
async def reply_shop(message: Message, session: AsyncSession):
    from bot.handlers.profile import show_shop_message
    await show_shop_message(message, session)


@router.message(F.text == "📊 Статистика")
async def reply_stats(message: Message, session: AsyncSession):
    from bot.handlers.profile import show_stats_message
    await show_stats_message(message, session)


# ── Slash commands (Telegram command menu) ────────────────────────────────────

@router.message(Command("workout"))
async def cmd_workout(message: Message, state: FSMContext, session: AsyncSession):
    user = await get_or_create_user(session, message.from_user)
    current_state = await state.get_state()
    if current_state in (
        WorkoutFSM.exercise_card,
        WorkoutFSM.rating_effort,
        WorkoutFSM.rest_timer,
        WorkoutFSM.replacing,
    ):
        await message.answer(
            "⚠️ У тебя идёт тренировка. Продолжить или завершить?",
            reply_markup=_active_workout_kb(),
        )
        return
    from bot.handlers.workout import start_workout_from_message
    await start_workout_from_message(message, state, session, user)


@router.message(Command("profile"))
async def cmd_profile(message: Message, session: AsyncSession):
    from bot.handlers.profile import show_profile_message
    await show_profile_message(message, session)


@router.message(Command("stats"))
async def cmd_stats(message: Message, session: AsyncSession):
    from bot.handlers.profile import show_stats_message
    await show_stats_message(message, session)


@router.message(Command("shop"))
async def cmd_shop(message: Message, session: AsyncSession):
    from bot.handlers.profile import show_shop_message
    await show_shop_message(message, session)
