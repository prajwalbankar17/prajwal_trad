"""Risk profiles, limits and the daily risk state.

Risk lives apart from strategy logic on purpose: a strategy proposes, risk
disposes. Nothing in `app/strategies` may import this module's enforcement.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class RiskProfile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "risk_profiles"

    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    capital: Mapped[float] = mapped_column(Numeric(18, 2), default=1_000_000)
    max_risk_per_trade_pct: Mapped[float] = mapped_column(Numeric(6, 3), default=1.0)
    max_daily_loss_pct: Mapped[float] = mapped_column(Numeric(6, 3), default=3.0)
    max_open_positions: Mapped[int] = mapped_column(Integer, default=5)
    max_trades_per_day: Mapped[int] = mapped_column(Integer, default=20)
    max_total_exposure_pct: Mapped[float] = mapped_column(Numeric(6, 3), default=80.0)
    max_sector_exposure_pct: Mapped[float] = mapped_column(Numeric(6, 3), default=30.0)
    max_capital_utilisation_pct: Mapped[float] = mapped_column(Numeric(6, 3), default=80.0)
    max_position_size_pct: Mapped[float] = mapped_column(Numeric(6, 3), default=20.0)

    # Margin is never assumed. This is what *we* are willing to model; the
    # broker's actual leverage is fetched and the lower of the two applies.
    assumed_leverage: Mapped[float] = mapped_column(Numeric(6, 2), default=1.0)
    use_broker_margin_when_available: Mapped[bool] = mapped_column(Boolean, default=True)

    kill_switch_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)


class RiskLimitBreach(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Every block is recorded - a strategy that looks quiet may simply have
    been stopped by risk all day."""

    __tablename__ = "risk_limit_breaches"
    __table_args__ = (Index("ix_risk_breach_time", "occurred_at"),)

    risk_profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("risk_profiles.id"))
    signal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trading_signals.id", ondelete="SET NULL")
    )
    limit_name: Mapped[str] = mapped_column(String(60), index=True)
    limit_value: Mapped[float | None] = mapped_column(Numeric(18, 4))
    actual_value: Mapped[float | None] = mapped_column(Numeric(18, 4))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    action_taken: Mapped[str] = mapped_column(String(60), default="SIGNAL_REJECTED")
    details: Mapped[dict] = mapped_column(JSONB, default=dict)


class DailyRiskState(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One row per profile per trading day. Survives a process restart, which
    is why it is in PostgreSQL and not only in Redis."""

    __tablename__ = "daily_risk_states"
    __table_args__ = (
        UniqueConstraint("risk_profile_id", "trade_date", name="uq_daily_risk_profile_date"),
    )

    risk_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("risk_profiles.id", ondelete="CASCADE")
    )
    trade_date: Mapped[date] = mapped_column(Date, index=True)

    realised_pnl: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    unrealised_pnl: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    charges_paid: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    trades_taken: Mapped[int] = mapped_column(Integer, default=0)
    open_positions: Mapped[int] = mapped_column(Integer, default=0)
    deployed_capital: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    sector_exposure: Mapped[dict] = mapped_column(JSONB, default=dict)

    trading_halted: Mapped[bool] = mapped_column(Boolean, default=False)
    halt_reason: Mapped[str | None] = mapped_column(Text)
    halted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExposureRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "exposure_records"
    __table_args__ = (Index("ix_exposure_profile_time", "risk_profile_id", "recorded_at"),)

    risk_profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("risk_profiles.id"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    total_exposure: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    utilisation_pct: Mapped[float] = mapped_column(Numeric(8, 3), default=0)
    by_sector: Mapped[dict] = mapped_column(JSONB, default=dict)
    by_instrument: Mapped[dict] = mapped_column(JSONB, default=dict)
