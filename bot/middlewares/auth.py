from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.common import subscribe_kb
from bot.services.user_service import get_user_by_telegram_id, sync_expired_subscription


class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # pre_checkout_query MUST always pass — blocking it breaks payments
        if isinstance(event, PreCheckoutQuery):
            return await handler(event, data)

        session: AsyncSession | None = data.get("session")
        if not session:
            return await handler(event, data)

        from_user = getattr(event, "from_user", None)
        if not from_user:
            return await handler(event, data)

        user = await get_user_by_telegram_id(session, from_user.id)
        if not user:
            return await handler(event, data)

        # Expire subscription if needed
        if user.is_subscribed and user.sub_expires_at:
            if user.sub_expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
                await sync_expired_subscription(session, user)

        data["db_user"] = user

        # Allow admins unconditionally
        if user.is_admin:
            return await handler(event, data)

        # Allow if subscribed
        if user.is_subscribed:
            return await handler(event, data)

        # Allow trial (first workout free)
        if not user.trial_used:
            return await handler(event, data)

        # Paywall
        text = (
            "⚡ Твой пробный доступ исчерпан.\n\n"
            "Оформи подписку, чтобы продолжить тренировки и не терять прогресс!"
        )
        if isinstance(event, Message):
            await event.answer(text, reply_markup=subscribe_kb())
        elif isinstance(event, CallbackQuery):
            await event.answer("Нужна подписка", show_alert=True)
            await event.message.answer(text, reply_markup=subscribe_kb())
