import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255))
    first_name: Mapped[Optional[str]] = mapped_column(String(255))

    # Onboarding profile
    goal: Mapped[Optional[str]] = mapped_column(String(50))          # mass / cut / tone
    fitness_level: Mapped[Optional[str]] = mapped_column(String(50)) # beginner / mid / adv
    gender: Mapped[Optional[str]] = mapped_column(String(20))
    days_per_week: Mapped[Optional[int]] = mapped_column(Integer)

    # Subscription
    is_subscribed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sub_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    trial_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Gamification
    xp_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # numeric level 1-250+
    epoch: Mapped[Optional[str]] = mapped_column(String(50))

    # Weekly streak (not daily!)
    streak_weeks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_week_workouts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    week_started_at: Mapped[Optional[date]] = mapped_column(Date)

    # Fitcoin economy
    fitcoin_balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fitcoin_total_earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Avatar (FK to shop_items, nullable — user may not have bought a skin)
    avatar_skin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shop_items.id"), nullable=True
    )
