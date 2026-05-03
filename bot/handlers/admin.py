from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.user import User
from bot.models.workout import WorkoutSession

router = Router()


def admin_only(handler):
    async def wrapper(message: Message, session: AsyncSession, **kwargs):
        db_user: User | None = kwargs.get("db_user")
        if not db_user or not db_user.is_admin:
            return
        return await handler(message, session, **kwargs)
    wrapper.__name__ = handler.__name__
    return wrapper


@router.message(Command("stats"))
@admin_only
async def cmd_stats(message: Message, session: AsyncSession, **kwargs):
    total_users = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    subscribed = (
        await session.execute(
            select(func.count()).select_from(User).where(User.is_subscribed == True)  # noqa: E712
        )
    ).scalar_one()
    total_ws = (
        await session.execute(
            select(func.count()).select_from(WorkoutSession).where(
                WorkoutSession.status == "finished"
            )
        )
    ).scalar_one()

    await message.answer(
        f"📊 <b>Статистика GymBot</b>\n\n"
        f"Пользователей: {total_users}\n"
        f"Подписчиков: {subscribed}\n"
        f"Тренировок завершено: {total_ws}",
        parse_mode="HTML",
    )


@router.message(Command("broadcast"))
@admin_only
async def cmd_broadcast(message: Message, session: AsyncSession, **kwargs):
    text = message.text.removeprefix("/broadcast").strip()
    if not text:
        await message.answer("Использование: /broadcast <текст>")
        return

    users_result = await session.execute(select(User.telegram_id))
    user_ids = [row[0] for row in users_result.all()]

    sent, failed = 0, 0
    for tg_id in user_ids:
        try:
            await message.bot.send_message(tg_id, text)
            sent += 1
        except Exception:
            failed += 1

    await message.answer(f"Рассылка: ✅ {sent} / ❌ {failed}")


@router.message(Command("grant_sub"))
@admin_only
async def cmd_grant_sub(message: Message, session: AsyncSession, **kwargs):
    """Usage: /grant_sub <telegram_id> <days>"""
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("Использование: /grant_sub <telegram_id> <days>")
        return

    tg_id, days = int(parts[1]), int(parts[2])
    from bot.services.user_service import get_user_by_telegram_id
    user = await get_user_by_telegram_id(session, tg_id)
    if not user:
        await message.answer("Пользователь не найден")
        return

    from datetime import datetime, timedelta, timezone
    user.is_subscribed = True
    user.sub_expires_at = datetime.now(timezone.utc) + timedelta(days=days)
    await session.commit()
    await message.answer(f"✅ Подписка выдана пользователю {tg_id} на {days} дней")
