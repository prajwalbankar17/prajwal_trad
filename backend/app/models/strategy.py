"""Strategy definitions, versions, parameters and combinations.

Strategies are rows, not classes-with-hardcoded-numbers. A `Strategy` names a
registered implementation (`code`, resolved through `app.strategies.registry`);
a `StrategyVersion` freezes the parameter set that produced a given set of
results, so a backtest from three months ago can still be explained.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Strategy(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "strategies"
    __table_args__ = (Index("ix_strategies_active_module", "is_active", "module"),)

    code: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(150))
    category: Mapped[str] = mapped_column(String(30), index=True)
    module: Mapped[str] = mapped_column(String(10), default="EQUITY", index=True)
    description: Mapped[str | None] = mapped_column(Text)

    # Activation is per strategy AND per module (see TradingModuleState).
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_research_only: Mapped[bool] = mapped_column(Boolean, default=True)

    default_timeframe: Mapped[str] = mapped_column(String(5), default="5m")
    supported_timeframes: Mapped[list] = mapped_column(JSONB, default=list)
    default_parameters: Mapped[dict] = mapped_column(JSONB, default=dict)
    parameter_schema: Mapped[dict] = mapped_column(JSONB, default=dict)

    current_version_id: Mapped[uuid.UUID | None] = mapped_column()
    notes: Mapped[str | None] = mapped_column(Text)

    versions: Mapped[list[StrategyVersion]] = relationship(
        back_populates="strategy", cascade="all, delete-orphan"
    )


class StrategyVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "strategy_versions"
    __table_args__ = (
        UniqueConstraint("strategy_id", "version", name="uq_strategy_version"),
    )

    strategy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE")
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict)
    changelog: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    strategy: Mapped[Strategy] = relationship(back_populates="versions")


class StrategyConfig(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A user's runnable configuration of a strategy: which instruments, which
    timeframe, which session window, which exits."""

    __tablename__ = "strategy_configs"
    __table_args__ = (Index("ix_strategy_configs_enabled", "is_enabled"),)

    strategy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE")
    )
    strategy_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategy_versions.id")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(150))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    timeframe: Mapped[str] = mapped_column(String(5), default="5m")
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Universe selection: an explicit instrument list, a watchlist, or a filter.
    instrument_ids: Mapped[list] = mapped_column(JSONB, default=list)
    watchlist_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("watchlists.id"))
    universe_filter: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Risk / exits
    stop_loss_type: Mapped[str] = mapped_column(String(20), default="PERCENT")
    stop_loss_value: Mapped[float] = mapped_column(Numeric(10, 4), default=1.0)
    target_type: Mapped[str] = mapped_column(String(20), default="RR")
    target_value: Mapped[float] = mapped_column(Numeric(10, 4), default=2.0)
    trailing_stop_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    trailing_stop_value: Mapped[float | None] = mapped_column(Numeric(10, 4))
    min_risk_reward: Mapped[float] = mapped_column(Numeric(6, 2), default=1.5)

    # Session window (IST)
    session_start: Mapped[time] = mapped_column(Time, default=time(9, 20))
    session_end: Mapped[time] = mapped_column(Time, default=time(15, 0))
    square_off_time: Mapped[time] = mapped_column(Time, default=time(15, 15))

    max_signals_per_day: Mapped[int] = mapped_column(Integer, default=10)
    allow_repeat_signal_same_candle: Mapped[bool] = mapped_column(Boolean, default=False)
    risk_profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("risk_profiles.id"))

    strategy: Mapped[Strategy] = relationship(lazy="joined")


class StrategyCombination(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Combine 2-5 strategy configs with AND / OR / weighted / min-confirmation
    logic. Mandatory legs must pass regardless of score."""

    __tablename__ = "strategy_combinations"

    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    logic: Mapped[str] = mapped_column(String(20), default="WEIGHTED")
    min_confirmations: Mapped[int] = mapped_column(Integer, default=2)
    entry_threshold: Mapped[float] = mapped_column(Numeric(6, 3), default=0.6)
    exit_threshold: Mapped[float] = mapped_column(Numeric(6, 3), default=0.4)
    timeframe: Mapped[str] = mapped_column(String(5), default="5m")
    config: Mapped[dict] = mapped_column(JSONB, default=dict)

    legs: Mapped[list[StrategyCombinationLeg]] = relationship(
        back_populates="combination", cascade="all, delete-orphan", lazy="selectin"
    )


class StrategyCombinationLeg(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "strategy_combination_legs"
    __table_args__ = (
        UniqueConstraint("combination_id", "strategy_config_id", name="uq_combination_leg"),
    )

    combination_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategy_combinations.id", ondelete="CASCADE")
    )
    strategy_config_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategy_configs.id", ondelete="CASCADE")
    )
    weight: Mapped[float] = mapped_column(Numeric(6, 3), default=1.0)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=False)
    role: Mapped[str | None] = mapped_column(String(40))  # trend | entry | volume | risk
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    combination: Mapped[StrategyCombination] = relationship(back_populates="legs")
    strategy_config: Mapped[StrategyConfig] = relationship(lazy="joined")


class StrategyExecutionLog(Base, UUIDPrimaryKeyMixin):
    """One row per strategy evaluation pass. This is what makes a signal - or
    the absence of one - explainable after the fact."""

    __tablename__ = "strategy_execution_logs"
    __table_args__ = (
        Index("ix_strategy_exec_config_time", "strategy_config_id", "evaluated_at"),
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    strategy_config_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategy_configs.id", ondelete="CASCADE")
    )
    instrument_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("instruments.id"))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    candle_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timeframe: Mapped[str | None] = mapped_column(String(5))
    produced_signal: Mapped[bool] = mapped_column(Boolean, default=False)
    conditions: Mapped[dict] = mapped_column(JSONB, default=dict)
    indicator_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)


class TradingModuleState(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Per-module Active/Inactive switch.

    Deactivating a module stops NEW signals and NEW entries. Monitoring of open
    positions, stop-loss, target and exits continues - an open position is never
    abandoned because someone flipped a switch.
    """

    __tablename__ = "trading_module_states"

    module: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    # Always True while any position is open, regardless of is_active.
    monitor_open_positions: Mapped[bool] = mapped_column(Boolean, default=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deactivated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(Text)
