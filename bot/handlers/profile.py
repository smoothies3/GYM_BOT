from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.common import back_to_menu_kb, subscribe_kb
from bot.keyboards.common import main_menu_kb
from bot.models.log import Badge, ShopItem, UserBadge, UserPurchase
from bot.models.workout import WorkoutSession
from bot.phrases import p
from bot.services.gamification import calc_level, spend_fitcoin, xp_for_level
from bot.services.user_service import get_or_create_user

router = Router()

AVATAR = {1: "🧍", 5: "🚶", 10: "🏃", 25: "🏋️", 50: "💪", 100: "🦁", 250: "⚡"}


def avatar_emoji(level: int) -> str:
    for threshold in sorted(AVATAR.keys(), reverse=True):
        if level >= threshold:
            return AVATAR[threshold]
    return "🧍"


async def _profile_text_and_kb(session: AsyncSession, user):
    count_result = await session.execute(
        select(func.count()).select_from(WorkoutSession).where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.status == "finished",
        )
    )
    total_workouts = count_result.scalar_one()

    volume_result = await session.execute(
        select(func.sum(WorkoutSession.total_volume_kg)).where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.status == "finished",
        )
    )
    total_volume = volume_result.scalar_one() or 0

    badge_result = await session.execute(
        select(Badge).join(UserBadge, Badge.id == UserBadge.badge_id).where(
            UserBadge.user_id == user.id
        )
    )
    badges = list(badge_result.scalars().all())

    sub_status = "✅ Активна" if user.is_subscribed else "❌ Неактивна"
    sub_until = f" до {user.sub_expires_at.strftime('%d.%m.%Y')}" if user.is_subscribed and user.sub_expires_at else ""
    badge_line = " ".join(b.icon for b in badges) if badges else "пока нет"

    text = p(
        "profile_header",
        avatar=avatar_emoji(user.level),
        level=user.level,
        workout_count=total_workouts,
        volume_total_kg=total_volume,
        streak_weeks=user.streak_weeks,
        xp_total=user.xp_total,
        fitcoin_balance=user.fitcoin_balance,
    )
    text += f"\n\nПодписка: {sub_status}{sub_until}\nБейджи: {badge_line}"

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    if not user.is_subscribed:
        b.button(text="💳 Оформить подписку", callback_data="menu:subscribe")
    b.button(text="🏪 Магазин", callback_data="menu:shop")
    b.button(text="🏠 Главное меню", callback_data="menu:main")
    b.adjust(1)
    return text, b.as_markup()


async def show_profile_message(message: Message, session: AsyncSession):
    user = await get_or_create_user(session, message.from_user)
    text, kb = await _profile_text_and_kb(session, user)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


async def show_shop_message(message: Message, session: AsyncSession):
    user = await get_or_create_user(session, message.from_user)
    items_result = await session.execute(
        select(ShopItem).where(
            ShopItem.is_active == True,  # noqa: E712
            ShopItem.level_required <= user.level,
        ).order_by(ShopItem.price_fc)
    )
    items = list(items_result.scalars().all())

    if not items:
        await message.answer(
            "🏪 Магазин пуст. Повышай уровень — появятся новые предметы!",
            reply_markup=back_to_menu_kb(),
        )
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    for item in items:
        b.button(text=f"{item.name} — {item.price_fc} FC", callback_data=f"buy:{item.id}")
    b.button(text="↩ Назад", callback_data="menu:profile")
    b.adjust(1)
    await message.answer(
        f"🏪 <b>Магазин</b>\nТвой баланс: <b>{user.fitcoin_balance} FC</b>",
        reply_markup=b.as_markup(),
        parse_mode="HTML",
    )


async def show_stats_message(message: Message, session: AsyncSession):
    user = await get_or_create_user(session, message.from_user)

    count_result = await session.execute(
        select(func.count()).select_from(WorkoutSession).where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.status == "finished",
        )
    )
    total_workouts = count_result.scalar_one()

    volume_result = await session.execute(
        select(func.sum(WorkoutSession.total_volume_kg)).where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.status == "finished",
        )
    )
    total_volume = volume_result.scalar_one() or 0

    text = (
        f"📊 <b>Статистика</b>\n\n"
        f"Тренировок всего: <b>{total_workouts}</b>\n"
        f"Общий объём: <b>{total_volume} кг</b>\n"
        f"Стрик: <b>{user.streak_weeks} нед.</b>\n"
        f"XP: <b>{user.xp_total}</b>\n"
        f"Fitcoin: <b>{user.fitcoin_balance} FC</b>"
    )
    await message.answer(text, reply_markup=back_to_menu_kb(), parse_mode="HTML")


@router.callback_query(F.data == "menu:profile")
async def show_profile(call: CallbackQuery, session: AsyncSession):
    user = await get_or_create_user(session, call.from_user)
    text, kb = await _profile_text_and_kb(session, user)
    await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "menu:subscribe")
async def show_subscribe(call: CallbackQuery):
    await call.message.edit_text(
        "Выбери тариф подписки:\n\n"
        "• 1 месяц — 299 ₽\n"
        "• 3 месяца — 762 ₽ (−15%)\n"
        "• 1 год — 2 868 ₽ (−20%)",
        reply_markup=subscribe_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "menu:shop")
async def show_shop(call: CallbackQuery, session: AsyncSession):
    user = await get_or_create_user(session, call.from_user)

    items_result = await session.execute(
        select(ShopItem).where(
            ShopItem.is_active == True,  # noqa: E712
            ShopItem.level_required <= user.level,
        ).order_by(ShopItem.price_fc)
    )
    items = list(items_result.scalars().all())

    if not items:
        await call.message.edit_text(
            "🏪 Магазин пуст. Повышай уровень — появятся новые предметы!",
            reply_markup=back_to_menu_kb(),
        )
        await call.answer()
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    for item in items:
        b.button(
            text=f"{item.name} — {item.price_fc} FC",
            callback_data=f"buy:{item.id}",
        )
    b.button(text="↩ Назад", callback_data="menu:profile")
    b.adjust(1)

    await call.message.edit_text(
        f"🏪 <b>Магазин</b>\nТвой баланс: <b>{user.fitcoin_balance} FC</b>",
        reply_markup=b.as_markup(),
        parse_mode="HTML",
    )
    await call.answer()


@router.callback_query(F.data.startswith("buy:"))
async def buy_item(call: CallbackQuery, session: AsyncSession):
    import uuid
    item_id = uuid.UUID(call.data.split(":")[1])
    user = await get_or_create_user(session, call.from_user)

    item_result = await session.execute(select(ShopItem).where(ShopItem.id == item_id))
    item = item_result.scalar_one_or_none()
    if not item:
        await call.answer("Предмет не найден", show_alert=True)
        return

    # Check already purchased
    existing = await session.execute(
        select(UserPurchase).where(
            UserPurchase.user_id == user.id, UserPurchase.item_id == item_id
        )
    )
    if existing.scalar_one_or_none():
        await call.answer("Ты уже купил этот предмет", show_alert=True)
        return

    ok = await spend_fitcoin(session, user, item.price_fc, "purchase")
    if not ok:
        await call.answer(
            p("shop_purchase_not_enough",
              item_name=item.name, price_fc=item.price_fc, fitcoin_balance=user.fitcoin_balance),
            show_alert=True,
        )
        return

    purchase = UserPurchase(user_id=user.id, item_id=item.id, price_paid_fc=item.price_fc)
    session.add(purchase)

    # Apply skin if cosmetic
    if item.category == "cosmetic":
        user.avatar_skin_id = item.id
    await session.commit()

    await call.answer(
        p("shop_purchase_success", item_name=item.name, fitcoin_balance=user.fitcoin_balance),
        show_alert=True,
    )
