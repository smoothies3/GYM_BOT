import asyncio
import random
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.common import main_menu_kb
from bot.phrases import p
from bot.services.media_service import send_exercise_media
from bot.keyboards.workout import (
    alternatives_kb,
    effort_kb,
    exercise_card_kb,
    rest_timer_kb,
    workout_summary_kb,
)
from bot.services import gamification as gam
from bot.services.progress_service import get_or_init_progress, log_set, update_progress
from bot.services.user_service import get_or_create_user, update_user
from bot.services.workout_service import (
    abandon_session,
    create_session,
    find_plan,
    get_active_session,
    get_exercise,
    get_exercise_alternatives,
    get_plan_exercises,
)
from bot.states.fsm import WorkoutFSM

router = Router()

REST_SECONDS = 90

EFFORT_LABELS = {"easy": "😴 Легко", "on_point": "💪 В точку", "hard": "🔥 Тяжело"}


_AVATAR_NAMES = {1: "Новичок", 5: "Ходок", 10: "Бегун", 25: "Атлет", 50: "Профи", 100: "Элита", 250: "Легенда"}


def _avatar_name(level: int) -> str:
    for threshold in sorted(_AVATAR_NAMES.keys(), reverse=True):
        if level >= threshold:
            return _AVATAR_NAMES[threshold]
    return "Новичок"


def _ex_text(plan_ex, exercise, pw, position: int = 0, total: int = 0) -> str:
    weight_display = f"{pw.recommended_kg:.1f}" if exercise.equipment != "bodyweight" else "0"
    lines: list[str] = []

    if position and total and position == total:
        lines += [p("exercise_card_last"), ""]

    if position and total:
        lines.append(p(
            "exercise_card_intro",
            position=position, total=total,
            exercise=exercise.name,
            sets=plan_ex.sets,
            reps_min=plan_ex.reps_min, reps_max=plan_ex.reps_max,
            weight=weight_display,
        ))
    else:
        weight_str = f"{pw.recommended_kg:.1f} кг" if exercise.equipment != "bodyweight" else "без веса"
        lines.append(
            f"<b>{exercise.name}</b>\n"
            f"📋 {plan_ex.sets} подхода × {plan_ex.reps_min}–{plan_ex.reps_max} повторений\n"
            f"⚖️ Вес: <b>{weight_str}</b>"
        )

    if exercise.description:
        lines += ["", exercise.description]
    if random.random() < 0.6:
        lines += ["", p("exercise_card_tip")]
    if exercise.media_url:
        lines.append(f'\n<a href="{exercise.media_url}">▶ Смотреть технику</a>')
    return "\n".join(lines)


async def _workout_start_text(session: AsyncSession, user, day_key: str) -> str:
    """Choose the right greeting phrase based on user state."""
    from bot.models.workout import WorkoutSession as WS
    count_result = await session.execute(
        select(func.count()).select_from(WS).where(
            WS.user_id == user.id, WS.status == "finished"
        )
    )
    total_workouts = count_result.scalar_one()
    name = user.first_name or "Бро"

    if total_workouts == 0:
        return p("workout_start_first_ever", name=name)

    last_result = await session.execute(
        select(WS.finished_at).where(
            WS.user_id == user.id, WS.status == "finished"
        ).order_by(WS.finished_at.desc()).limit(1)
    )
    last_finished = last_result.scalar_one_or_none()

    weeks_since_last = 0
    if last_finished:
        if last_finished.tzinfo is None:
            last_finished = last_finished.replace(tzinfo=timezone.utc)
        weeks_since_last = (datetime.now(timezone.utc) - last_finished).days // 7

    if weeks_since_last >= 3:
        return p("workout_start_comeback_3w_plus", name=name)
    if weeks_since_last == 2:
        return p("workout_start_comeback_2w", name=name)
    if weeks_since_last == 1:
        return p("workout_start_comeback_1w", name=name)

    streak = user.streak_weeks
    if streak == 12:
        return p("workout_start_streak_12w", name=name)
    if streak == 8:
        return p("workout_start_streak_8w", name=name)
    if streak == 4:
        return p("workout_start_streak_4w", name=name)

    if user.current_week_workouts == 0:
        return p("workout_start_first_of_week", name=name)

    return p("workout_start_regular", name=name, day_key=day_key, workout_count=total_workouts)


async def _plan_preview_text(session: AsyncSession, plan_id, day_key: str, plan_name: str) -> str:
    plan_exercises = await get_plan_exercises(session, plan_id, day_key)
    lines = []
    total_sets = 0
    muscles: set[str] = set()
    for i, pe in enumerate(plan_exercises, 1):
        ex = await get_exercise(session, pe.exercise_id)
        lines.append(f"{i}. {ex.name}  {pe.sets}×{pe.reps_min}–{pe.reps_max}")
        total_sets += pe.sets
        muscles.add(ex.muscle_group.capitalize())
    est_lo = total_sets * 2
    est_hi = total_sets * 3
    muscle_str = ", ".join(sorted(muscles))
    return (
        f"<b>Тренировка на сегодня</b>\n\n"
        f"<b>{len(plan_exercises)} упражнений</b>\n"
        + "\n".join(lines)
        + f"\n\n🎯 {muscle_str}\n"
        f"💪 Подходов: {total_sets}\n"
        f"⏱ Время: {est_lo}–{est_hi} мин"
    )


async def _show_exercise(call_or_msg, state: FSMContext, session: AsyncSession, user):
    """Always sends a NEW message — previous cards stay in chat."""
    data = await state.get_data()
    plan_id = data["plan_id"]
    day_key = data["day_key"]
    ex_index = data["ex_index"]

    plan_exercises = await get_plan_exercises(session, plan_id, day_key)

    if ex_index >= len(plan_exercises):
        await _finish_workout(call_or_msg, state, session, user)
        return

    plan_ex = plan_exercises[ex_index]
    exercise = await get_exercise(session, plan_ex.exercise_id)
    pw = await get_or_init_progress(session, user.id, exercise, user.fitness_level)
    alternatives = await get_exercise_alternatives(session, exercise)
    has_alt = len(alternatives) > 0

    await state.update_data(
        current_ex_id=str(exercise.id),
        current_plan_ex_sets=plan_ex.sets,
        current_plan_ex_reps_min=plan_ex.reps_min,
        current_plan_ex_reps_max=plan_ex.reps_max,
        current_weight_kg=pw.recommended_kg,
        has_alternatives=has_alt,
        was_replaced=False,
    )

    # Send video/GIF if available (silently skipped if no file)
    chat_id = call_or_msg.from_user.id if isinstance(call_or_msg, CallbackQuery) else call_or_msg.chat.id
    await send_exercise_media(call_or_msg.bot, chat_id, exercise.name)

    text = _ex_text(plan_ex, exercise, pw, position=ex_index + 1, total=len(plan_exercises))

    # Send as a brand-new message so history accumulates
    if isinstance(call_or_msg, CallbackQuery):
        await call_or_msg.message.answer(text, reply_markup=exercise_card_kb(has_alt), parse_mode="HTML")
        await call_or_msg.answer()
    else:
        await call_or_msg.answer(text, reply_markup=exercise_card_kb(has_alt), parse_mode="HTML")

    await state.set_state(WorkoutFSM.exercise_card)


async def _finish_workout(call_or_msg, state: FSMContext, session: AsyncSession, user):
    data = await state.get_data()
    ws_id = data["ws_id"]

    from bot.models.workout import WorkoutSession
    result = await session.execute(select(WorkoutSession).where(WorkoutSession.id == ws_id))
    ws = result.scalar_one_or_none()
    if not ws:
        await state.clear()
        return

    on_point_count = data.get("on_point_count", 0)
    hard_count = data.get("hard_count", 0)
    total_volume = data.get("total_volume_kg", 0)
    was_replaced_count = data.get("was_replaced_count", 0)
    is_first_of_week = user.current_week_workouts == 0

    user = await gam.update_streak(session, user)

    xp = gam.calc_xp(
        total_volume_kg=total_volume,
        on_point_count=on_point_count,
        hard_count=hard_count,
        streak_weeks=user.streak_weeks,
        current_week_workouts=user.current_week_workouts,
        days_per_week=user.days_per_week or 3,
    )

    from bot.services.workout_service import finish_session
    ws = await finish_session(session, ws, total_volume, xp)
    user, leveled_up = await gam.add_xp(session, user, xp)

    if not user.trial_used:
        await update_user(session, user, trial_used=True)

    badges = await gam.check_and_grant_badges(session, user, ws, on_point_count, was_replaced_count)
    rewards = await gam.post_workout_rewards(session, user, ws, on_point_count, is_first_of_week, leveled_up)

    count_result = await session.execute(
        select(func.count()).select_from(WorkoutSession).where(
            WorkoutSession.user_id == user.id, WorkoutSession.status == "finished"
        )
    )
    total_workouts = count_result.scalar_one()

    total_fc = sum(rewards.values())
    finish_text = p(
        "workout_finish_regular",
        volume_kg=total_volume,
        duration_min=ws.duration_min or 0,
        xp=xp,
        fc=total_fc,
        workout_count=total_workouts,
    )

    from bot.keyboards.common import main_reply_kb
    from bot.handlers.start import avatar_emoji
    send = call_or_msg.message if isinstance(call_or_msg, CallbackQuery) else call_or_msg
    await send.answer(finish_text, reply_markup=main_reply_kb())

    if "first_workout_week" in rewards:
        await send.answer(p("workout_finish_first_of_week_bonus", fc=rewards["first_workout_week"]))
    if "overachieve_bonus" in rewards:
        await send.answer(p("workout_finish_overachieve", fc=rewards["overachieve_bonus"]))

    if leveled_up:
        await send.answer(p(
            "level_up",
            old_level=user.level - 1,
            new_level=user.level,
            avatar=avatar_emoji(user.level),
            avatar_name=_avatar_name(user.level),
            fc=rewards.get("level_up", 0),
        ))

    for badge in badges:
        await gam.add_fitcoin(session, user, 200, "new_badge", badge.id)
        await send.answer(p("badge_earned", badge_icon=badge.icon, badge_name=badge.name, fc=200))

    await send.answer("Что дальше?", reply_markup=workout_summary_kb())

    await state.clear()
    if isinstance(call_or_msg, CallbackQuery):
        await call_or_msg.answer()


# ── Resume / abort active session ────────────────────────────────────────────

async def _resume_session(call_or_msg, state: FSMContext, session: AsyncSession, user, active):
    """Restore FSM state from DB session and re-send the current exercise card."""
    plan_exercises = await get_plan_exercises(session, active.plan_id, active.day_key)
    ex_index = active.current_ex_index

    await state.update_data(
        ws_id=active.id,
        plan_id=active.plan_id,
        day_key=active.day_key,
        ex_index=ex_index,
        on_point_count=0,
        hard_count=0,
        total_volume_kg=active.total_volume_kg,
        was_replaced_count=0,
    )

    if ex_index >= len(plan_exercises):
        await _finish_workout(call_or_msg, state, session, user)
        return

    plan_ex = plan_exercises[ex_index]
    exercise = await get_exercise(session, plan_ex.exercise_id)
    pw = await get_or_init_progress(session, user.id, exercise, user.fitness_level)
    alternatives = await get_exercise_alternatives(session, exercise)
    has_alt = len(alternatives) > 0

    await state.update_data(
        current_ex_id=str(exercise.id),
        current_plan_ex_sets=plan_ex.sets,
        current_plan_ex_reps_min=plan_ex.reps_min,
        current_plan_ex_reps_max=plan_ex.reps_max,
        current_weight_kg=pw.recommended_kg,
        has_alternatives=has_alt,
        was_replaced=False,
    )

    text = p("workout_resume") + "\n\n" + _ex_text(
        plan_ex, exercise, pw,
        position=ex_index + 1, total=len(plan_exercises),
    )
    send = call_or_msg.message if isinstance(call_or_msg, CallbackQuery) else call_or_msg
    await send.answer(text, reply_markup=exercise_card_kb(has_alt), parse_mode="HTML")
    await state.set_state(WorkoutFSM.exercise_card)
    if isinstance(call_or_msg, CallbackQuery):
        await call_or_msg.answer()


@router.callback_query(F.data == "workout:resume")
async def workout_resume(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    user = await get_or_create_user(session, call.from_user)
    active = await get_active_session(session, user.id)
    await call.message.edit_reply_markup(reply_markup=None)
    if active:
        await _resume_session(call, state, session, user, active)
    else:
        await call.message.answer("Активная тренировка не найдена.", reply_markup=main_menu_kb())
        await call.answer()


@router.callback_query(F.data == "workout:abort")
async def workout_abort(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    user = await get_or_create_user(session, call.from_user)
    active = await get_active_session(session, user.id)
    if active:
        await abandon_session(session, active)
    await state.clear()
    await call.message.edit_reply_markup(reply_markup=None)
    from bot.keyboards.common import main_reply_kb
    await call.message.answer(p("workout_abort"), reply_markup=main_reply_kb())
    await call.answer()


# ── Start workout ─────────────────────────────────────────────────────────────

async def start_workout_from_message(
    message: Message, state: FSMContext, session: AsyncSession, user
):
    """Start or resume workout from a Message (reply keyboard button)."""
    from bot.keyboards.common import remove_reply_kb

    if not user.fitness_level or not user.goal:
        await message.answer(p("workout_no_plan"))
        return

    active = await get_active_session(session, user.id)
    if active:
        await _resume_session(message, state, session, user, active)
        return

    plan = await find_plan(session, user.goal, user.fitness_level, user.days_per_week or 3)
    if not plan:
        await message.answer(p("workout_no_plan"), reply_markup=main_menu_kb())
        return

    ws = await create_session(session, user, plan)
    await state.update_data(
        ws_id=ws.id,
        plan_id=plan.id,
        day_key=ws.day_key,
        ex_index=0,
        on_point_count=0,
        hard_count=0,
        total_volume_kg=0,
        was_replaced_count=0,
    )
    preview = await _plan_preview_text(session, plan.id, ws.day_key, plan.name)
    start_text = await _workout_start_text(session, user, ws.day_key)
    await message.answer(start_text, reply_markup=remove_reply_kb())
    await message.answer(preview, parse_mode="HTML")
    await _show_exercise(message, state, session, user)


@router.callback_query(F.data == "menu:workout")
async def start_workout(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    user = await get_or_create_user(session, call.from_user)

    if not user.fitness_level or not user.goal:
        await call.answer(p("workout_no_plan"), show_alert=True)
        return

    active = await get_active_session(session, user.id)
    if active:
        await _resume_session(call, state, session, user, active)
        return

    plan = await find_plan(session, user.goal, user.fitness_level, user.days_per_week or 3)
    if not plan:
        await call.message.answer(p("workout_no_plan"), reply_markup=main_menu_kb())
        await call.answer()
        return

    ws = await create_session(session, user, plan)
    await state.update_data(
        ws_id=ws.id,
        plan_id=plan.id,
        day_key=ws.day_key,
        ex_index=0,
        on_point_count=0,
        hard_count=0,
        total_volume_kg=0,
        was_replaced_count=0,
    )
    preview = await _plan_preview_text(session, plan.id, ws.day_key, plan.name)
    start_text = await _workout_start_text(session, user, ws.day_key)
    await call.message.answer(preview, parse_mode="HTML")
    await call.message.answer(start_text)
    await _show_exercise(call, state, session, user)


# ── Exercise done ─────────────────────────────────────────────────────────────

@router.callback_query(WorkoutFSM.exercise_card, F.data == "ex:done")
async def ex_done(call: CallbackQuery, state: FSMContext):
    # Keep exercise card in chat — just remove its buttons
    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer(p("workout_ask_effort"), reply_markup=effort_kb())
    await state.set_state(WorkoutFSM.rating_effort)
    await call.answer()


# ── Effort rating ─────────────────────────────────────────────────────────────

@router.callback_query(WorkoutFSM.rating_effort, F.data.startswith("effort:"))
async def rate_effort(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    effort = call.data.split(":")[1]
    data = await state.get_data()
    user = await get_or_create_user(session, call.from_user)

    import uuid
    exercise = await get_exercise(session, uuid.UUID(data["current_ex_id"]))
    pw = await get_or_init_progress(session, user.id, exercise)
    weight_kg = data.get("current_weight_kg", 0.0)
    reps = data.get("current_plan_ex_reps_min", 10)
    sets = data.get("current_plan_ex_sets", 3)

    from bot.models.workout import WorkoutSession
    from sqlalchemy import select
    ws_result = await session.execute(select(WorkoutSession).where(WorkoutSession.id == data["ws_id"]))
    ws = ws_result.scalar_one()

    for s in range(1, sets + 1):
        await log_set(
            session, ws.id, exercise.id, user.id,
            set_number=s, weight_kg=weight_kg, reps=reps,
            effort=effort, was_replaced=data.get("was_replaced", False),
        )

    await update_progress(session, pw, exercise, effort, weight_kg)

    volume_delta = int(weight_kg * reps * sets)
    updates: dict = {
        "total_volume_kg": data.get("total_volume_kg", 0) + volume_delta,
        "was_replaced": False,
        "ex_index": data["ex_index"] + 1,
    }
    if effort == "on_point":
        updates["on_point_count"] = data.get("on_point_count", 0) + 1
    elif effort == "hard":
        updates["hard_count"] = data.get("hard_count", 0) + 1
    await state.update_data(**updates)

    ws.current_ex_index = updates["ex_index"]
    ws.total_volume_kg = updates["total_volume_kg"]
    await session.commit()

    # Edit effort message: show voice feedback, remove buttons
    await call.message.edit_text(p(f"effort_{effort}"), reply_markup=None)

    # New message: rest timer
    rest_msg = await call.message.answer(p("rest_start", seconds=REST_SECONDS), reply_markup=rest_timer_kb())
    await state.update_data(rest_msg_id=rest_msg.message_id)
    await state.set_state(WorkoutFSM.rest_timer)
    await call.answer()

    # Auto-advance after REST_SECONDS
    await asyncio.sleep(REST_SECONDS)
    if await state.get_state() == WorkoutFSM.rest_timer:
        try:
            await call.bot.edit_message_text(
                p("rest_end"),
                chat_id=call.from_user.id,
                message_id=rest_msg.message_id,
                reply_markup=None,
            )
        except Exception:
            pass
        await _show_exercise(call, state, session, user)


# ── Skip rest ─────────────────────────────────────────────────────────────────

@router.callback_query(WorkoutFSM.rest_timer, F.data == "rest:skip")
async def rest_skip(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    user = await get_or_create_user(session, call.from_user)
    await call.message.edit_text(p("rest_end"), reply_markup=None)
    await _show_exercise(call, state, session, user)


# ── Replace exercise ──────────────────────────────────────────────────────────

@router.callback_query(WorkoutFSM.exercise_card, F.data == "ex:replace")
async def ex_replace(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    import uuid
    exercise = await get_exercise(session, uuid.UUID(data["current_ex_id"]))
    alternatives = await get_exercise_alternatives(session, exercise)

    if not alternatives:
        await call.answer("Нет доступных замен", show_alert=True)
        return

    # Remove buttons from exercise card
    await call.message.edit_reply_markup(reply_markup=None)

    alt_list = [(str(ex.id), ex.name, ex.equipment) for ex in alternatives]
    await call.message.answer(p("replace_offer", exercise=exercise.name), reply_markup=alternatives_kb(alt_list))
    await state.set_state(WorkoutFSM.replacing)
    await call.answer()


@router.callback_query(WorkoutFSM.replacing, F.data.startswith("alt:"))
async def alt_chosen(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    value = call.data.split(":")[1]
    user = await get_or_create_user(session, call.from_user)

    if value == "cancel":
        await call.message.edit_text(p("replace_cancelled"), reply_markup=None)
        await _show_exercise(call, state, session, user)
        return

    import uuid
    new_exercise = await get_exercise(session, uuid.UUID(value))
    if not new_exercise:
        await call.answer("Упражнение не найдено", show_alert=True)
        return

    pw = await get_or_init_progress(session, user.id, new_exercise, user.fitness_level)
    data = await state.get_data()
    await state.update_data(
        current_ex_id=str(new_exercise.id),
        current_weight_kg=pw.recommended_kg,
        was_replaced=True,
        was_replaced_count=data.get("was_replaced_count", 0) + 1,
    )

    await call.message.edit_text(p("replace_done"), reply_markup=None)

    # Show new exercise card
    data = await state.get_data()
    plan_exercises = await get_plan_exercises(session, data["plan_id"], data["day_key"])
    plan_ex = plan_exercises[data["ex_index"]]

    text = _ex_text(plan_ex, new_exercise, pw)
    await call.message.answer(text, reply_markup=exercise_card_kb(False), parse_mode="HTML")
    await state.set_state(WorkoutFSM.exercise_card)
    await call.answer()


# ── Finish early ──────────────────────────────────────────────────────────────

@router.callback_query(WorkoutFSM.exercise_card, F.data == "ex:finish")
async def ex_finish_early(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    user = await get_or_create_user(session, call.from_user)
    await call.message.edit_reply_markup(reply_markup=None)
    await _finish_workout(call, state, session, user)
