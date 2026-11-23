"""Orders, paper trades, positions, executions and exits.

`execution_mode` is on every row that represents money moving. In this build it
is always PAPER; the column exists so a future live engine cannot write rows
that look identical to simulated ones.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Order(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Simulated order. A live adapter would write here too - hence
    `execution_mode` and the CHECK that keeps this build honest."""

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("execution_mode = 'PAPER'", name="orders_paper_only"),
        Index("ix_orders_status_time", "status", "created_at"),
        Index("ix_orders_position", "position_id"),
    )

    execution_mode: Mapped[str] = mapped_column(String(10), default="PAPER")
    position_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("positions.id", ondelete="CASCADE")
    )
    signal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trading_signals.id", ondelete="SET NULL")
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instruments.id"))

    side: Mapped[str] = mapped_column(String(4))
    order_type: Mapped[str] = mapped_column(String(10), default="MARKET")
    product: Mapped[str] = mapped_column(String(10), default="MIS")
    quantity: Mapped[int] = mapped_column(Integer)
    filled_quantity: Mapped[int] = mapped_column(Integer, default=0)
    price: Mapped[float | None] = mapped_column(Numeric(14, 4))
    trigger_price: Mapped[float | None] = mapped_column(Numeric(14, 4))
    average_price: Mapped[float | None] = mapped_column(Numeric(14, 4))

    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    status_message: Mapped[str | None] = mapped_column(Text)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    placed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Simulation detail: what we assumed about slippage and why.
    simulation: Mapped[dict] = mapped_column(JSONB, default=dict)
    broker_order_id: Mapped[str | None] = mapped_column(String(60))


class Position(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An open or closed paper position with its full lifecycle."""

    __tablename__ = "positions"
    __table_args__ = (
        CheckConstraint("execution_mode = 'PAPER'", name="positions_paper_only"),
        Index("ix_positions_status_time", "status", "entry_time"),
        Index("ix_positions_instrument", "instrument_id", "status"),
        Index("ix_positions_date", "trade_date"),
    )

    execution_mode: Mapped[str] = mapped_column(String(10), default="PAPER")
    module: Mapped[str] = mapped_column(String(10), default="EQUITY", index=True)

    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instruments.id"))
    signal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trading_signals.id", ondelete="SET NULL")
    )
    strategy_config_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategy_configs.id", ondelete="SET NULL")
    )
    risk_profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("risk_profiles.id"))
    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("portfolios.id", ondelete="SET NULL")
    )

    direction: Mapped[str] = mapped_column(String(4))
    product: Mapped[str] = mapped_column(String(10), default="MIS")
    quantity: Mapped[int] = mapped_column(Integer)
    remaining_quantity: Mapped[int] = mapped_column(Integer)

    entry_price: Mapped[float] = mapped_column(Numeric(14, 4))
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)

    exit_price: Mapped[float | None] = mapped_column(Numeric(14, 4))
    exit_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exit_reason: Mapped[str | None] = mapped_column(String(30))

    stop_loss: Mapped[float] = mapped_column(Numeric(14, 4))
    target: Mapped[float] = mapped_column(Numeric(14, 4))
    initial_stop_loss: Mapped[float] = mapped_column(Numeric(14, 4))
    trailing_stop_active: Mapped[bool] = mapped_column(Boolean, default=False)

    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)

    # P&L: gross, charges and net are stored separately and never conflated.
    gross_pnl: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    charges: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    net_pnl: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    unrealised_pnl: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    charge_breakdown: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Excursions, for MAE/MFE analytics.
    max_favourable_excursion: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    max_adverse_excursion: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    highest_price_seen: Mapped[float | None] = mapped_column(Numeric(14, 4))
    lowest_price_seen: Mapped[float | None] = mapped_column(Numeric(14, 4))

    capital_deployed: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    margin_used: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    is_backtest: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    backtest_job_id: Mapped[uuid.UUID | None] = mapped_column()

    executions: Mapped[list[TradeExecution]] = relationship(
        back_populates="position", cascade="all, delete-orphan"
    )
    exits: Mapped[list[ExitRecord]] = relationship(
        back_populates="position", cascade="all, delete-orphan"
    )


class TradeExecution(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single fill. Partial entries and partial exits each produce one."""

    __tablename__ = "trade_executions"
    __table_args__ = (Index("ix_executions_position_time", "position_id", "executed_at"),)

    position_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("positions.id", ondelete="CASCADE")
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"))
    side: Mapped[str] = mapped_column(String(4))
    quantity: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Numeric(14, 4))
    requested_price: Mapped[float | None] = mapped_column(Numeric(14, 4))
    slippage: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    charges: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    leg: Mapped[str] = mapped_column(String(10), default="ENTRY")  # ENTRY | EXIT
    details: Mapped[dict] = mapped_column(JSONB, default=dict)

    position: Mapped[Position] = relationship(back_populates="executions")


class ExitRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Why a position (or part of it) was closed."""

    __tablename__ = "exit_records"
    __table_args__ = (Index("ix_exits_position", "position_id"),)

    position_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("positions.id", ondelete="CASCADE")
    )
    quantity: Mapped[int] = mapped_column(Integer)
    exit_price: Mapped[float] = mapped_column(Numeric(14, 4))
    exit_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(String(30))
    gross_pnl: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    charges: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    net_pnl: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    is_partial: Mapped[bool] = mapped_column(Boolean, default=False)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)

    position: Mapped[Position] = relationship(back_populates="exits")
