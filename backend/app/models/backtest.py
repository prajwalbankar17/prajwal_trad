"""Backtesting jobs, results, trades and metrics."""

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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BacktestJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "backtest_jobs"
    __table_args__ = (Index("ix_backtest_jobs_status", "status", "created_at"),)

    name: Mapped[str] = mapped_column(String(200))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    mode: Mapped[str] = mapped_column(String(20), default="QUICK")  # QUICK | ADVANCED
    status: Mapped[str] = mapped_column(String(20), default="QUEUED", index=True)

    strategy_config_ids: Mapped[list] = mapped_column(JSONB, default=list)
    combination_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategy_combinations.id", ondelete="SET NULL")
    )
    instrument_ids: Mapped[list] = mapped_column(JSONB, default=list)
    timeframe: Mapped[str] = mapped_column(String(5), default="5m")

    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    # Out-of-sample split, walk-forward windows, optimisation grid.
    validation: Mapped[dict] = mapped_column(JSONB, default=dict)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)

    initial_capital: Mapped[float] = mapped_column(Numeric(18, 2), default=1_000_000)
    include_charges: Mapped[bool] = mapped_column(Boolean, default=True)
    slippage_pct: Mapped[float] = mapped_column(Numeric(8, 4), default=0.05)

    progress_pct: Mapped[float] = mapped_column(Numeric(6, 2), default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)

    # Honest reporting: which requested instruments actually had usable data.
    data_coverage: Mapped[dict] = mapped_column(JSONB, default=dict)
    warnings: Mapped[list] = mapped_column(JSONB, default=list)

    results: Mapped[list[BacktestResult]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class BacktestResult(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One result row per (job, scope). Scope is OVERALL, a strategy, an
    instrument, or an in-sample/out-of-sample/walk-forward window."""

    __tablename__ = "backtest_results"
    __table_args__ = (Index("ix_backtest_results_job_scope", "job_id", "scope"),)

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("backtest_jobs.id", ondelete="CASCADE")
    )
    scope: Mapped[str] = mapped_column(String(30), default="OVERALL")
    scope_ref: Mapped[str | None] = mapped_column(String(120))
    window: Mapped[str | None] = mapped_column(String(30))  # IN_SAMPLE | OUT_OF_SAMPLE | WF_3

    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)

    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    winning_trades: Mapped[int] = mapped_column(Integer, default=0)
    losing_trades: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[float] = mapped_column(Numeric(8, 4), default=0)

    gross_profit: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    gross_loss: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    total_charges: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    net_profit: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    profit_factor: Mapped[float | None] = mapped_column(Numeric(12, 4))
    expectancy: Mapped[float | None] = mapped_column(Numeric(18, 4))

    average_profit: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    average_loss: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    average_rr: Mapped[float | None] = mapped_column(Numeric(10, 4))
    max_drawdown: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    max_drawdown_pct: Mapped[float] = mapped_column(Numeric(10, 4), default=0)
    sharpe_ratio: Mapped[float | None] = mapped_column(Numeric(12, 4))
    sortino_ratio: Mapped[float | None] = mapped_column(Numeric(12, 4))
    max_consecutive_wins: Mapped[int] = mapped_column(Integer, default=0)
    max_consecutive_losses: Mapped[int] = mapped_column(Integer, default=0)
    avg_mae: Mapped[float | None] = mapped_column(Numeric(18, 4))
    avg_mfe: Mapped[float | None] = mapped_column(Numeric(18, 4))

    equity_curve: Mapped[list] = mapped_column(JSONB, default=list)
    monthly_performance: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Populated when in-sample vs out-of-sample degradation looks like curve fit.
    overfitting_flags: Mapped[dict] = mapped_column(JSONB, default=dict)
    metrics_extra: Mapped[dict] = mapped_column(JSONB, default=dict)

    job: Mapped[BacktestJob] = relationship(back_populates="results")


class BacktestTrade(Base, UUIDPrimaryKeyMixin):
    """Trade-by-trade record for a backtest. Kept separate from live `positions`
    so research volume never slows down the trading tables."""

    __tablename__ = "backtest_trades"
    __table_args__ = (
        Index("ix_backtest_trades_job", "job_id", "entry_time"),
        Index("ix_backtest_trades_instrument", "job_id", "instrument_id"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("backtest_jobs.id", ondelete="CASCADE")
    )
    result_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("backtest_results.id", ondelete="CASCADE")
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instruments.id"))
    strategy_config_id: Mapped[uuid.UUID | None] = mapped_column()

    direction: Mapped[str] = mapped_column(String(4))
    quantity: Mapped[int] = mapped_column(Integer)
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    entry_price: Mapped[float] = mapped_column(Numeric(14, 4))
    exit_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exit_price: Mapped[float | None] = mapped_column(Numeric(14, 4))
    exit_reason: Mapped[str | None] = mapped_column(String(30))
    stop_loss: Mapped[float] = mapped_column(Numeric(14, 4))
    target: Mapped[float] = mapped_column(Numeric(14, 4))

    gross_pnl: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    charges: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    net_pnl: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    mae: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    mfe: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    bars_held: Mapped[int | None] = mapped_column(Integer)
    conditions: Mapped[dict] = mapped_column(JSONB, default=dict)


class BacktestConfiguration(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Saved, reusable backtest setups."""

    __tablename__ = "backtest_configurations"

    name: Mapped[str] = mapped_column(String(200), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    description: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False)
