from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.log import Subscription
from bot.models.user import User

PLANS = {
    "month":   {"months": 1,  "amount_kopecks": 29900,  "label": "1 месяц"},
    "quarter": {"months": 3,  "amount_kopecks": 76200,  "label": "3 месяца"},
    "year":    {"months": 12, "amount_kopecks": 286800, "label": "1 год"},
}


def get_plan(key: str) -> dict | None:
    return PLANS.get(key)


async def activate_subscription(
    session: AsyncSession,
    user: User,
    plan_key: str,
    provider_payment_id: str,
) -> Subscription:
    plan = PLANS[plan_key]
    now = datetime.now(timezone.utc)

    # Extend from current expiry if still active
    base = user.sub_expires_at if (user.is_subscribed and user.sub_expires_at and user.sub_expires_at > now) else now
    expires_at = base + timedelta(days=30 * plan["months"])

    sub = Subscription(
        user_id=user.id,
        status="active",
        provider_payment_id=provider_payment_id,
        amount_kopecks=plan["amount_kopecks"],
        started_at=now,
        expires_at=expires_at,
    )
    session.add(sub)

    user.is_subscribed = True
    user.sub_expires_at = expires_at

    await session.commit()
    await session.refresh(sub)
    return sub
