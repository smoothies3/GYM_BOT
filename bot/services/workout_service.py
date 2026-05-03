import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.exercise import Exercise
from bot.models.workout import PlanExercise, WorkoutPlan, WorkoutSession
from bot.models.user import User

DAY_KEYS = ["A", "B", "C", "D", "E"]


async def find_plan(
    session: AsyncSession, goal: str, fitness_level: str, days_per_week: int
) -> WorkoutPlan | None:
    """Finds the best matching active plan. Falls back by relaxing constraints."""
    # Exact match
    result = await session.execute(
        select(WorkoutPlan).where(
            WorkoutPlan.goal == goal,
            WorkoutPlan.level == fitness_level,
            WorkoutPlan.days_per_week == days_per_week,
            WorkoutPlan.is_active == True,  # noqa: E712
        )
    )
    plan = result.scalar_one_or_none()
    if plan:
        return plan

    # Relax days constraint — pick closest
    result = await session.execute(
        select(WorkoutPlan).where(
            WorkoutPlan.goal == goal,
            WorkoutPlan.level == fitness_level,
            WorkoutPlan.is_active == True,  # noqa: E712
        )
    )
    plans = list(result.scalars().all())
    if plans:
        return min(plans, key=lambda p: abs(p.days_per_week - days_per_week))

    # Relax level constraint
    result = await session.execute(
        select(WorkoutPlan).where(
            WorkoutPlan.goal == goal,
            WorkoutPlan.is_active == True,  # noqa: E712
        )
    )
    plans = list(result.scalars().all())
    if plans:
        return min(plans, key=lambda p: abs(p.days_per_week - days_per_week))

    # Return any active plan
    result = await session.execute(
        select(WorkoutPlan).where(WorkoutPlan.is_active == True)  # noqa: E712
    )
    return result.scalars().first()


async def get_plan_exercises(
    session: AsyncSession, plan_id: uuid.UUID, day_key: str
) -> list[PlanExercise]:
    result = await session.execute(
        select(PlanExercise)
        .where(PlanExercise.plan_id == plan_id, PlanExercise.day_key == day_key)
        .order_by(PlanExercise.position)
    )
    return list(result.scalars().all())


async def get_exercise(session: AsyncSession, exercise_id: uuid.UUID) -> Exercise | None:
    result = await session.execute(select(Exercise).where(Exercise.id == exercise_id))
    return result.scalar_one_or_none()


async def get_exercise_alternatives(
    session: AsyncSession, exercise: Exercise, limit: int = 5
) -> list[Exercise]:
    """
    Returns alternatives sorted so different-equipment options come first.
    Combines explicit alternative_ids with a DB search for same muscle group + different equipment.
    """
    # Step 1: explicit alternatives from alternative_ids
    explicit: list[Exercise] = []
    if exercise.alternative_ids:
        ids = [uuid.UUID(eid) for eid in exercise.alternative_ids]
        result = await session.execute(
            select(Exercise).where(Exercise.id.in_(ids), Exercise.is_active == True)  # noqa: E712
        )
        explicit = list(result.scalars().all())

    # Step 2: same muscle group, different equipment (DB-wide)
    result = await session.execute(
        select(Exercise).where(
            Exercise.muscle_group == exercise.muscle_group,
            Exercise.equipment != exercise.equipment,
            Exercise.id != exercise.id,
            Exercise.is_active == True,  # noqa: E712
        )
    )
    diff_equip = list(result.scalars().all())

    # Merge: different-equipment first, same-equipment last
    explicit_ids = {ex.id for ex in explicit}
    explicit_diff = [ex for ex in explicit if ex.equipment != exercise.equipment]
    explicit_same = [ex for ex in explicit if ex.equipment == exercise.equipment]
    extra_diff = [ex for ex in diff_equip if ex.id not in explicit_ids]

    return (explicit_diff + extra_diff + explicit_same)[:limit]


async def get_active_session(
    session: AsyncSession, user_id: uuid.UUID
) -> WorkoutSession | None:
    result = await session.execute(
        select(WorkoutSession).where(
            WorkoutSession.user_id == user_id,
            WorkoutSession.status == "active",
        )
    )
    return result.scalar_one_or_none()


def _next_day_key(completed_sessions_count: int, days_per_week: int) -> str:
    """Rotates through A/B/C/D/E based on completed sessions."""
    return DAY_KEYS[completed_sessions_count % days_per_week]


async def create_session(
    session: AsyncSession, user: User, plan: WorkoutPlan
) -> WorkoutSession:
    from sqlalchemy import func
    count_result = await session.execute(
        select(func.count()).select_from(WorkoutSession).where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.status == "finished",
        )
    )
    finished_count = count_result.scalar_one()
    day_key = _next_day_key(finished_count, plan.days_per_week)

    ws = WorkoutSession(
        user_id=user.id,
        plan_id=plan.id,
        day_key=day_key,
        current_ex_index=0,
        status="active",
        started_at=datetime.now(timezone.utc),
    )
    session.add(ws)
    await session.commit()
    await session.refresh(ws)
    return ws


async def advance_session(session: AsyncSession, ws: WorkoutSession) -> WorkoutSession:
    ws.current_ex_index += 1
    await session.commit()
    await session.refresh(ws)
    return ws


async def finish_session(
    session: AsyncSession,
    ws: WorkoutSession,
    total_volume_kg: int,
    xp_earned: int,
) -> WorkoutSession:
    ws.status = "finished"
    ws.finished_at = datetime.now(timezone.utc)
    ws.total_volume_kg = total_volume_kg
    ws.xp_earned = xp_earned
    if ws.started_at:
        delta = ws.finished_at - ws.started_at.replace(tzinfo=timezone.utc)
        ws.duration_min = int(delta.total_seconds() / 60)
    await session.commit()
    await session.refresh(ws)
    return ws


async def abandon_session(session: AsyncSession, ws: WorkoutSession) -> None:
    ws.status = "abandoned"
    ws.finished_at = datetime.now(timezone.utc)
    await session.commit()
