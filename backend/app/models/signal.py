"""Trading signals.

A signal is a *proposal*. It is never a trade. Only the paper engine turns a
VALIDATED signal into a PaperTrade, and it records the link both ways.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TradingSignal(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "trading_signals"
    __table_args__ = (
        Index("ix_signals_state_time", "state", "generated_at"),
        Index("ix_signals_instrument_time", "instrument_id", "generated_at"),
        Index("ix_signals_config_time", "strategy_config_id", "generated_at"),
        # Guarantees one signal per strategy/instrument/timeframe/candle unless
        # the config explicitly allows repeats (then dedupe_key carries a nonce).
        UniqueConstraint("dedupe_key", name="uq_signal_dedupe"),
    )

    # --- Identity ---
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instruments.id"))
    exchange: Mapped[str] = mapped_column(String(10))
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("strategies.id"))
    strategy_config_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategy_configs.id", ondelete="SET NULL")
    )
    strategy_version: Mapped[int | None] = mapped_column(Integer)
    combination_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategy_combinations.id", ondelete="SET NULL")
    )
    module: Mapped[str] = mapped_column(String(10), default="EQUITY")

    # --- Trade proposal ---
    direction: Mapped[str] = mapped_column(String(4))
    entry_price: Mapped[float] = mapped_column(Numeric(14, 4))
    stop_loss: Mapped[float] = mapped_column(Numeric(14, 4))
    target: Mapped[float] = mapped_column(Numeric(14, 4))
    risk_reward: Mapped[float | None] = mapped_column(Numeric(8, 3))
    suggested_quantity: Mapped[int | None] = mapped_column(Integer)
    timeframe: Mapped[str] = mapped_column(String(5))

    # --- Timing ---
    candle_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- Evaluation ---
    state: Mapped[str] = mapped_column(String(20), default="GENERATED", index=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(6, 3))
    score: Mapped[float | None] = mapped_column(Numeric(8, 3))
    entry_reason: Mapped[str | None] = mapped_column(Text)
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    # Full condition-by-condition breakdown: what passed, what failed, values.
    conditions: Mapped[dict] = mapped_column(JSONB, default=dict)
    confirmations: Mapped[dict] = mapped_column(JSONB, default=dict)
    market_context: Mapped[dict] = mapped_column(JSONB, default=dict)
    risk_validation: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Freshness guard: which source and how old the driving data was.
    data_source: Mapped[str] = mapped_column(String(30), default="HISTORICAL_IMPORT")
    data_age_seconds: Mapped[int | None] = mapped_column(Integer)

    dedupe_key: Mapped[str] = mapped_column(String(220))
    is_backtest: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    backtest_job_id: Mapped[uuid.UUID | None] = mapped_column()

    history: Mapped[list[SignalHistory]] = relationship(
        back_populates="signal", cascade="all, delete-orphan"
    )


class SignalHistory(Base, UUIDPrimaryKeyMixin):
    """State transitions. Nothing overwrites a signal's past."""

    __tablename__ = "signal_history"
    __table_args__ = (Index("ix_signal_history_signal", "signal_id", "changed_at"),)

    signal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trading_signals.id", ondelete="CASCADE")
    )
    from_state: Mapped[str | None] = mapped_column(String(20))
    to_state: Mapped[str] = mapped_column(String(20))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(40), default="system")

    signal: Mapped[TradingSignal] = relationship(back_populates="history")
