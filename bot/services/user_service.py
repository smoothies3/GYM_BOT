import uuid
from datetime import datetime, timezone

from aiogram.types import User as TgUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.user import User


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def get_or_create_user(session: AsyncSession, tg_user: TgUser) -> User:
    user = await get_user_by_telegram_id(session, tg_user.id)
    if not user:
        user = User(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def update_user(session: AsyncSession, user: User, **kwargs) -> User:
    for key, value in kwargs.items():
        setattr(user, key, value)
    await session.commit()
    await session.refresh(user)
    return user


async def sync_expired_subscription(session: AsyncSession, user: User) -> None:
    user.is_subscribed = False
    await session.commit()


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_all_subscribed_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User).where(User.is_subscribed == True))  # noqa: E712
    return list(result.scalars().all())


async def get_users_expiring_soon(session: AsyncSession, days: int) -> list[User]:
    """Returns subscribed users whose subscription expires within `days` days."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    threshold = now + timedelta(days=days)
    result = await session.execute(
        select(User).where(
            User.is_subscribed == True,  # noqa: E712
            User.sub_expires_at <= threshold,
            User.sub_expires_at > now,
        )
    )
    return list(result.scalars().all())
