"""
Seed script: populates exercises, plans, plan_exercises, and badges.

Usage (from project root):
    python -m data.seed
"""
import asyncio
import json
import uuid
from pathlib import Path

from sqlalchemy import select

from bot.database import async_session_factory
from bot.models.exercise import Exercise
from bot.models.log import Badge
from bot.models.workout import PlanExercise, WorkoutPlan

DATA_DIR = Path(__file__).parent


async def seed_exercises(session) -> dict[str, Exercise]:
    raw = json.loads((DATA_DIR / "exercises.json").read_text(encoding="utf-8"))
    name_map: dict[str, Exercise] = {}

    for item in raw:
        result = await session.execute(
            select(Exercise).where(Exercise.name == item["name"])
        )
        ex = result.scalar_one_or_none()
        if not ex:
            ex = Exercise(
                name=item["name"],
                muscle_group=item["muscle_group"],
                equipment=item["equipment"],
                difficulty=item["difficulty"],
                description=item.get("description", ""),
                tips=item.get("tips", ""),
                alternative_ids=[],  # filled in second pass
                is_active=True,
            )
            session.add(ex)
        name_map[item["name"]] = (ex, item.get("alternatives", []))

    await session.commit()

    # Refresh all to get IDs
    for name in list(name_map.keys()):
        ex, _ = name_map[name]
        await session.refresh(ex)

    # Second pass: wire alternative_ids
    for name, (ex, alt_names) in name_map.items():
        ids = []
        for alt_name in alt_names:
            if alt_name in name_map:
                alt_ex, _ = name_map[alt_name]
                ids.append(str(alt_ex.id))
        ex.alternative_ids = ids

    await session.commit()
    print(f"  Exercises: {len(name_map)} seeded")
    return {name: ex for name, (ex, _) in name_map.items()}


async def seed_plans(session, ex_map: dict[str, Exercise]) -> None:
    raw = json.loads((DATA_DIR / "plans.json").read_text(encoding="utf-8"))

    for plan_data in raw:
        result = await session.execute(
            select(WorkoutPlan).where(WorkoutPlan.name == plan_data["name"])
        )
        plan = result.scalar_one_or_none()
        if not plan:
            plan = WorkoutPlan(
                name=plan_data["name"],
                goal=plan_data["goal"],
                level=plan_data["level"],
                days_per_week=plan_data["days_per_week"],
                is_active=True,
            )
            session.add(plan)
            await session.commit()
            await session.refresh(plan)

        # Clear existing plan_exercises for idempotency
        existing = await session.execute(
            select(PlanExercise).where(PlanExercise.plan_id == plan.id)
        )
        for pe in existing.scalars().all():
            await session.delete(pe)
        await session.commit()

        for day_key, exercises in plan_data["days"].items():
            for pos, ex_data in enumerate(exercises):
                ex_name = ex_data["exercise"]
                exercise = ex_map.get(ex_name)
                if not exercise:
                    print(f"  WARNING: exercise not found: {ex_name!r}")
                    continue
                pe = PlanExercise(
                    plan_id=plan.id,
                    exercise_id=exercise.id,
                    day_key=day_key,
                    position=pos,
                    sets=ex_data["sets"],
                    reps_min=ex_data["reps_min"],
                    reps_max=ex_data["reps_max"],
                )
                session.add(pe)

        await session.commit()

    print(f"  Plans: {len(raw)} seeded")


async def seed_badges(session) -> None:
    raw = json.loads((DATA_DIR / "badges.json").read_text(encoding="utf-8"))
    for item in raw:
        result = await session.execute(select(Badge).where(Badge.code == item["code"]))
        badge = result.scalar_one_or_none()
        if not badge:
            badge = Badge(
                code=item["code"],
                name=item["name"],
                description=item["description"],
                icon=item["icon"],
                condition_type=item["condition_type"],
                condition_value=item["condition_value"],
            )
            session.add(badge)
    await session.commit()
    print(f"  Badges: {len(raw)} seeded")


async def main() -> None:
    print("Seeding database...")
    async with async_session_factory() as session:
        ex_map = await seed_exercises(session)
        await seed_plans(session, ex_map)
        await seed_badges(session)
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
