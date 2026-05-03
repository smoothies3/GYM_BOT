import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

RATE_LIMIT = 0.5  # seconds between allowed messages per user
_last_call: dict[int, float] = {}


class ThrottlingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        user_id = event.from_user.id if event.from_user else None
        if not user_id:
            return await handler(event, data)

        now = time.monotonic()
        last = _last_call.get(user_id, 0.0)
        if now - last < RATE_LIMIT:
            return  # silently drop

        _last_call[user_id] = now
        return await handler(event, data)
