import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.log import Badge, FitcoinTransaction, UserBadge
from bot.models.user import User
from bot.models.workout import WorkoutSession

# ── XP ─────────────────────────────────────────────────────────────────────

STREAK_MULTIPLIERS = [
    (30, 2.0),
    (14, 1.5),
    (7, 1.25),
    (3, 1.1),
    (0, 1.0),
]


def calc_xp(
    total_volume_kg: int,
    on_point_count: int,
    hard_count: int,
    streak_weeks: int,
    current_week_workouts: int,
    days_per_week: int,
) -> int:
    base_xp = 50
    volume_bonus = (total_volume_kg // 1000) * 10
    effort_bonus = on_point_count * 5 + hard_count * 3

    multiplier = 1.0
    for threshold, mult in STREAK_MULTIPLIERS:
        if streak_weeks >= threshold:
            multiplier = mult
            break

    xp = (base_xp + volume_bonus + effort_bonus) * multiplier

    if current_week_workouts > days_per_week:
        xp *= 1.5

    return int(xp)


def xp_for_level(n: int) -> int:
    return int(100 * (1.15 ** n))


def calc_level(xp_total: int) -> int:
    level = 1
    while xp_total >= xp_for_level(level):
        xp_total -= xp_for_level(level)
        level += 1
    return level


async def add_xp(session: AsyncSession, user: User, xp: int) -> tuple[User, bool]:
    """Returns (user, leveled_up)."""
    user.xp_total += xp
    new_level = calc_level(user.xp_total)
    leveled_up = new_level > user.level
    if leveled_up:
        user.level = new_level
    await session.commit()
    return user, leveled_up


# ── Fitcoin ─────────────────────────────────────────────────────────────────

FITCOIN_RATES = {
    "workout_complete": 100,
    "on_point_per_ex": 5,
    "streak_bonus": 50,
    "overachieve_bonus": 75,
    "new_badge": 200,
    "first_workout_week": 30,
}


def level_up_fitcoin(new_level: int) -> int:
    """FC reward for reaching new_level. Scales from 50 to 2000."""
    return min(2000, 50 + (new_level - 1) * 15)


async def add_fitcoin(
    session: AsyncSession,
    user: User,
    amount: int,
    reason: str,
    ref_id: uuid.UUID | None = None,
) -> None:
    tx = FitcoinTransaction(user_id=user.id, amount=amount, reason=reason, ref_id=ref_id)
    session.add(tx)
    user.fitcoin_balance += amount
    user.fitcoin_total_earned += max(0, amount)
    await session.commit()


async def spend_fitcoin(
    session: AsyncSession, user: User, amount: int, reason: str
) -> bool:
    if user.fitcoin_balance < amount:
        return False
    tx = FitcoinTransaction(user_id=user.id, amount=-amount, reason=reason)
    session.add(tx)
    user.fitcoin_balance -= amount
    await session.commit()
    return True


# ── Weekly streak ────────────────────────────────────────────────────────────

MSK_OFFSET = timedelta(hours=3)


def _monday_msk(dt: datetime) -> date:
    msk = dt + MSK_OFFSET
    return (msk - timedelta(days=msk.weekday())).date()


async def update_streak(session: AsyncSession, user: User) -> User:
    now = datetime.now(timezone.utc)
    current_monday = _monday_msk(now)

    if user.week_started_at is None or user.week_started_at < current_monday:
        # New week started
        if user.week_started_at is not None:
            # Check if previous week goal was met
            if user.current_week_workouts < (user.days_per_week or 3):
                user.streak_weeks = 0  # reset streak
        user.week_started_at = current_monday
        user.current_week_workouts = 0

    user.current_week_workouts += 1

    # Week complete?
    if user.current_week_workouts == (user.days_per_week or 3):
        user.streak_weeks += 1

    await session.commit()
    return user


# ── Badges ───────────────────────────────────────────────────────────────────

async def _has_badge(session: AsyncSession, user: User, code: str) -> bool:
    result = await session.execute(
        select(UserBadge)
        .join(Badge, Badge.id == UserBadge.badge_id)
        .where(UserBadge.user_id == user.id, Badge.code == code)
    )
    return result.scalar_one_or_none() is not None


async def _grant_badge(
    session: AsyncSession, user: User, code: str
) -> Badge | None:
    result = await session.execute(select(Badge).where(Badge.code == code))
    badge = result.scalar_one_or_none()
    if not badge:
        return None
    if await _has_badge(session, user, code):
        return None
    ub = UserBadge(user_id=user.id, badge_id=badge.id)
    session.add(ub)
    await session.commit()
    return badge


async def check_and_grant_badges(
    session: AsyncSession,
    user: User,
    ws: WorkoutSession,
    on_point_count: int,
    was_replaced_count: int,
) -> list[Badge]:
    earned: list[Badge] = []

    # Total finished workouts
    count_result = await session.execute(
        select(func.count()).select_from(WorkoutSession).where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.status == "finished",
        )
    )
    total_workouts = count_result.scalar_one()

    checks = [
        ("first_workout", total_workouts >= 1),
        ("workouts_10", total_workouts >= 10),
        ("workouts_25", total_workouts >= 25),
        ("workouts_50", total_workouts >= 50),
        ("workouts_100", total_workouts >= 100),
        ("streak_4w", user.streak_weeks >= 4),
        ("streak_8w", user.streak_weeks >= 8),
        ("streak_12w", user.streak_weeks >= 12),
        ("volume_50k", user.fitcoin_total_earned >= 0 and ws.total_volume_kg is not None and ws.total_volume_kg >= 50_000),
        ("volume_200k", ws.total_volume_kg is not None and ws.total_volume_kg >= 200_000),
        ("volume_10k_session", ws.total_volume_kg is not None and ws.total_volume_kg >= 10_000),
        ("on_point_master", on_point_count >= 5),
    ]

    for code, condition in checks:
        if condition:
            badge = await _grant_badge(session, user, code)
            if badge:
                earned.append(badge)

    # adaptive badge requires lifetime replace count — check separately
    from bot.models.log import ExerciseLog
    replace_result = await session.execute(
        select(func.count()).select_from(ExerciseLog).where(
            ExerciseLog.user_id == user.id,
            ExerciseLog.was_replaced == True,  # noqa: E712
        )
    )
    total_replaced = replace_result.scalar_one()
    if total_replaced >= 10:
        badge = await _grant_badge(session, user, "adaptive")
        if badge:
            earned.append(badge)

    return earned


async def post_workout_rewards(
    session: AsyncSession,
    user: User,
    ws: WorkoutSession,
    on_point_count: int,
    is_first_of_week: bool,
    leveled_up: bool,
) -> dict:
    """Grant all Fitcoin rewards after a finished workout. Returns reward summary."""
    rewards: dict[str, int] = {}

    await add_fitcoin(session, user, FITCOIN_RATES["workout_complete"], "workout", ws.id)
    rewards["workout_complete"] = FITCOIN_RATES["workout_complete"]

    if on_point_count:
        fc = on_point_count * FITCOIN_RATES["on_point_per_ex"]
        await add_fitcoin(session, user, fc, "on_point", ws.id)
        rewards["on_point"] = fc

    if is_first_of_week:
        await add_fitcoin(session, user, FITCOIN_RATES["first_workout_week"], "first_workout_week", ws.id)
        rewards["first_workout_week"] = FITCOIN_RATES["first_workout_week"]

    if user.current_week_workouts == (user.days_per_week or 3):
        await add_fitcoin(session, user, FITCOIN_RATES["streak_bonus"], "streak_bonus", ws.id)
        rewards["streak_bonus"] = FITCOIN_RATES["streak_bonus"]

    if user.current_week_workouts > (user.days_per_week or 3):
        await add_fitcoin(session, user, FITCOIN_RATES["overachieve_bonus"], "overachieve", ws.id)
        rewards["overachieve_bonus"] = FITCOIN_RATES["overachieve_bonus"]

    if leveled_up:
        fc = level_up_fitcoin(user.level)
        await add_fitcoin(session, user, fc, "level_up")
        rewards["level_up"] = fc

    return rewards
