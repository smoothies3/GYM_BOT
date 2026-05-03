import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config import settings
from bot.database import async_session_factory
from bot.handlers import admin, payments, profile, start, workout
from bot.middlewares.auth import SubscriptionMiddleware
from bot.middlewares.db import DbSessionMiddleware
from bot.middlewares.throttling import ThrottlingMiddleware

logger = logging.getLogger(__name__)


async def send_renewal_reminders(bot: Bot, days: int) -> None:
    """Notify users whose subscription expires in `days` days."""
    from bot.services.user_service import get_users_expiring_soon
    async with async_session_factory() as session:
        users = await get_users_expiring_soon(session, days)
        for user in users:
            try:
                from bot.phrases import p
                key = "subscription_expiring_1d" if days == 1 else "subscription_expiring_3d"
                await bot.send_message(user.telegram_id, p(key))
            except Exception as e:
                logger.warning("Failed to send reminder to %s: %s", user.telegram_id, e)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=MemoryStorage())

    # Middlewares (order matters: db first, then throttle, then auth)
    dp.update.outer_middleware(DbSessionMiddleware())
    dp.message.outer_middleware(ThrottlingMiddleware())
    dp.update.outer_middleware(SubscriptionMiddleware())

    # Routers
    dp.include_router(start.router)
    dp.include_router(workout.router)
    dp.include_router(payments.router)
    dp.include_router(profile.router)
    dp.include_router(admin.router)

    # Scheduler
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(send_renewal_reminders, "cron", hour=10, args=[bot, 3])
    scheduler.add_job(send_renewal_reminders, "cron", hour=10, args=[bot, 1])
    scheduler.start()

    from aiogram.types import BotCommand, BotCommandScopeDefault
    await bot.set_my_commands(
        [
            BotCommand(command="start",   description="🏠 Главное меню"),
            BotCommand(command="workout", description="💪 Начать тренировку"),
            BotCommand(command="profile", description="👤 Мой профиль"),
            BotCommand(command="stats",   description="📊 Статистика"),
            BotCommand(command="shop",    description="🏪 Магазин"),
        ],
        scope=BotCommandScopeDefault(),
    )

    logger.info("GymBot started")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
