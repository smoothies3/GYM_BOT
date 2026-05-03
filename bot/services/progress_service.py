"""
RPE-based progressive overload (Rate of Perceived Exertion).

Science basis:
  - easy   (RPE ≤7): could do more reps → increase load
  - on_point (RPE 8): right stimulus    → keep load
  - hard   (RPE ≥9): too heavy         → decrease load

Load increments follow equipment physics:
  barbell 2.5 kg (smallest standard plate pair = 2×1.25 kg)
  dumbbell 2.0 kg (standard dumbbell rack steps)
  machine  5.0 kg (typical weight stack plate)
  cable    2.5 kg (weight stack)
  bodyweight 0 kg

Starting weights are evidence-based estimates per muscle group + equipment + fitness level.
"""
import math
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.exercise import Exercise
from bot.models.log import ExerciseLog, ProgressWeight

# ── Equipment step sizes (kg) ─────────────────────────────────────────────────
PROGRESSION_STEP: dict[str, float] = {
    "barbell": 2.5,
    "dumbbell": 2.0,
    "machine": 5.0,
    "cable": 2.5,
    "bodyweight": 0.0,
}

# ── Minimum safe weights per equipment ───────────────────────────────────────
# barbell min = empty bar (20 kg), dumbbell min = lightest pair
MIN_WEIGHTS: dict[str, float] = {
    "barbell": 20.0,
    "dumbbell": 2.0,
    "machine": 10.0,
    "cable": 5.0,
    "bodyweight": 0.0,
}

# ── Starting weights: (muscle_group, equipment) → {fitness_level: kg} ────────
# Derived from beginner program standards (e.g. Starting Strength, NSCA guidelines)
_START: dict[tuple[str, str], dict[str, float]] = {
    # CHEST
    ("chest", "barbell"):    {"beginner": 20.0, "mid": 40.0, "adv": 60.0},
    ("chest", "dumbbell"):   {"beginner": 10.0, "mid": 18.0, "adv": 28.0},
    ("chest", "machine"):    {"beginner": 30.0, "mid": 50.0, "adv": 70.0},
    ("chest", "cable"):      {"beginner": 10.0, "mid": 20.0, "adv": 30.0},
    ("chest", "bodyweight"): {"beginner": 0.0,  "mid": 0.0,  "adv": 0.0},
    # BACK
    ("back", "barbell"):     {"beginner": 30.0, "mid": 60.0, "adv": 90.0},
    ("back", "dumbbell"):    {"beginner": 10.0, "mid": 20.0, "adv": 32.0},
    ("back", "cable"):       {"beginner": 20.0, "mid": 35.0, "adv": 55.0},
    ("back", "bodyweight"):  {"beginner": 0.0,  "mid": 0.0,  "adv": 0.0},
    # SHOULDERS
    ("shoulders", "barbell"):   {"beginner": 20.0, "mid": 30.0, "adv": 50.0},
    ("shoulders", "dumbbell"):  {"beginner": 6.0,  "mid": 12.0, "adv": 20.0},
    ("shoulders", "machine"):   {"beginner": 20.0, "mid": 35.0, "adv": 50.0},
    ("shoulders", "cable"):     {"beginner": 5.0,  "mid": 10.0, "adv": 17.5},
    # LEGS
    ("legs", "barbell"):    {"beginner": 30.0, "mid": 60.0, "adv": 100.0},
    ("legs", "dumbbell"):   {"beginner": 12.0, "mid": 22.0, "adv": 36.0},
    ("legs", "machine"):    {"beginner": 40.0, "mid": 70.0, "adv": 110.0},
    ("legs", "bodyweight"): {"beginner": 0.0,  "mid": 0.0,  "adv": 0.0},
    # BICEPS
    ("biceps", "barbell"):  {"beginner": 10.0, "mid": 20.0, "adv": 32.5},
    ("biceps", "dumbbell"): {"beginner": 6.0,  "mid": 12.0, "adv": 18.0},
    ("biceps", "cable"):    {"beginner": 10.0, "mid": 17.5, "adv": 27.5},
    # TRICEPS
    ("triceps", "barbell"):    {"beginner": 10.0, "mid": 20.0, "adv": 30.0},
    ("triceps", "dumbbell"):   {"beginner": 6.0,  "mid": 12.0, "adv": 18.0},
    ("triceps", "cable"):      {"beginner": 10.0, "mid": 17.5, "adv": 27.5},
    ("triceps", "bodyweight"): {"beginner": 0.0,  "mid": 0.0,  "adv": 0.0},
    # CORE
    ("core", "bodyweight"): {"beginner": 0.0, "mid": 0.0, "adv": 0.0},
}

_LEVEL_MAP = {"beginner": "beginner", "mid": "mid", "adv": "adv"}


def _starting_weight(exercise: Exercise, fitness_level: str | None) -> float:
    if exercise.equipment == "bodyweight":
        return 0.0
    level = _LEVEL_MAP.get(fitness_level or "beginner", "beginner")
    key = (exercise.muscle_group, exercise.equipment)
    group = _START.get(key)
    if group:
        return group.get(level, group["beginner"])
    # Fallback by equipment only
    fallback = {"barbell": 20.0, "dumbbell": 10.0, "machine": 30.0, "cable": 10.0}
    return fallback.get(exercise.equipment, 10.0)


def _round_to_step(value: float, step: float) -> float:
    if step == 0:
        return 0.0
    return round(math.floor(value / step + 0.5) * step, 2)


async def get_or_init_progress(
    session: AsyncSession,
    user_id: uuid.UUID,
    exercise: Exercise,
    fitness_level: str | None = None,
) -> ProgressWeight:
    result = await session.execute(
        select(ProgressWeight).where(
            ProgressWeight.user_id == user_id,
            ProgressWeight.exercise_id == exercise.id,
        )
    )
    pw = result.scalar_one_or_none()
    if not pw:
        start = _starting_weight(exercise, fitness_level)
        pw = ProgressWeight(
            user_id=user_id,
            exercise_id=exercise.id,
            recommended_kg=start,
            last_weight_kg=start,
            easy_streak=0,
        )
        session.add(pw)
        await session.commit()
        await session.refresh(pw)
    return pw


async def update_progress(
    session: AsyncSession,
    pw: ProgressWeight,
    exercise: Exercise,
    effort: str,
    actual_weight_kg: float,
) -> ProgressWeight:
    step = PROGRESSION_STEP.get(exercise.equipment, 0.0)
    min_kg = MIN_WEIGHTS.get(exercise.equipment, 0.0)

    if effort == "easy":
        pw.easy_streak += 1
        if pw.easy_streak >= 2:
            # Double progression: two consecutive easy sessions → bigger jump
            new_kg = actual_weight_kg + step * 2
            pw.easy_streak = 0
        else:
            new_kg = actual_weight_kg + step
    elif effort == "hard":
        pw.easy_streak = 0
        new_kg = max(min_kg, actual_weight_kg - step)
    else:  # on_point
        pw.easy_streak = 0
        new_kg = actual_weight_kg

    pw.recommended_kg = _round_to_step(new_kg, step) if step else new_kg
    pw.last_weight_kg = actual_weight_kg
    pw.last_effort = effort
    await session.commit()
    await session.refresh(pw)
    return pw


async def log_set(
    session: AsyncSession,
    session_id: uuid.UUID,
    exercise_id: uuid.UUID,
    user_id: uuid.UUID,
    set_number: int,
    weight_kg: float,
    reps: int,
    effort: str,
    was_replaced: bool = False,
) -> ExerciseLog:
    log = ExerciseLog(
        session_id=session_id,
        exercise_id=exercise_id,
        user_id=user_id,
        set_number=set_number,
        weight_kg=weight_kg,
        reps=reps,
        effort=effort,
        was_replaced=was_replaced,
    )
    session.add(log)
    await session.commit()
    return log
