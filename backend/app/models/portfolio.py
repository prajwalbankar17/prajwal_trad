"""Portfolios, holdings and snapshots."""

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


class Portfolio(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "portfolios"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_portfolio_user_name"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    execution_mode: Mapped[str] = mapped_column(String(10), default="PAPER")
    risk_profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("risk_profiles.id"))

    starting_capital: Mapped[float] = mapped_column(Numeric(18, 2), default=1_000_000)
    current_capital: Mapped[float] = mapped_column(Numeric(18, 2), default=1_000_000)
    available_capital: Mapped[float] = mapped_column(Numeric(18, 2), default=1_000_000)
    deployed_capital: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    realised_pnl: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    unrealised_pnl: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    total_charges: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class Holding(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Delivery holdings. Synced read-only from the broker when connected."""

    __tablename__ = "holdings"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "instrument_id", name="uq_holding_portfolio_instrument"),
    )

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE")
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instruments.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    average_price: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    last_price: Mapped[float | None] = mapped_column(Numeric(14, 4))
    unrealised_pnl: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    source: Mapped[str] = mapped_column(String(20), default="PAPER")


class PortfolioSnapshot(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """End-of-day (and intraday) snapshot - the series behind the equity curve."""

    __tablename__ = "portfolio_snapshots"
    __table_args__ = (
        Index("ix_snapshots_portfolio_date", "portfolio_id", "snapshot_date"),
    )

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE")
    )
    snapshot_date: Mapped[date] = mapped_column(Date, index=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    equity: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    available_capital: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    deployed_capital: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    realised_pnl: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    unrealised_pnl: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    charges: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    open_positions: Mapped[int] = mapped_column(Integer, default=0)
    drawdown_pct: Mapped[float] = mapped_column(Numeric(10, 4), default=0)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
