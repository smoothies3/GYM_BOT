from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    SuccessfulPayment,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.keyboards.common import main_menu_kb, subscribe_kb
from bot.services.gamification import _grant_badge
from bot.services.payment_service import PLANS, activate_subscription
from bot.services.user_service import get_or_create_user

router = Router()


@router.callback_query(F.data.startswith("sub:"))
async def send_invoice(call: CallbackQuery, session: AsyncSession):
    plan_key = call.data.split(":")[1]
    plan = PLANS.get(plan_key)
    if not plan:
        await call.answer("Тариф не найден", show_alert=True)
        return

    await call.bot.send_invoice(
        chat_id=call.from_user.id,
        title=f"GymBot — подписка на {plan['label']}",
        description="Неограниченный доступ ко всем тренировкам и программам",
        payload=f"sub:{plan_key}",
        provider_token=settings.PAYMENT_PROVIDER_TOKEN,
        currency="RUB",
        prices=[LabeledPrice(label=f"Подписка {plan['label']}", amount=plan["amount_kopecks"])],
        start_parameter=f"sub_{plan_key}",
    )
    await call.answer()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    # Must always answer within 10 seconds — never block in middleware
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message, session: AsyncSession):
    payment: SuccessfulPayment = message.successful_payment
    payload = payment.invoice_payload  # "sub:month" / "sub:quarter" / "sub:year"
    plan_key = payload.split(":")[1]

    user = await get_or_create_user(session, message.from_user)
    sub = await activate_subscription(
        session, user, plan_key, payment.telegram_payment_charge_id
    )

    # subscriber badge
    await _grant_badge(session, user, "subscriber")

    plan = PLANS[plan_key]
    await message.answer(
        f"✅ Подписка активирована!\n\n"
        f"Тариф: {plan['label']}\n"
        f"Действует до: {sub.expires_at.strftime('%d.%m.%Y')}",
        reply_markup=main_menu_kb(),
    )


@router.callback_query(F.data == "menu:profile")
async def show_profile_from_payment(call: CallbackQuery, session: AsyncSession):
    # Delegate to profile handler via callback
    from bot.handlers.profile import show_profile
    await show_profile(call, session)
