"""Historical and live market data.

Physical design decision (see docs/DATABASE_SCHEMA.md):

* `intraday_candles` - the big one. ~3,000 instruments x 375 minutes x ~250
  sessions/year is roughly 280M rows/year at 1m alone. Declared as a
  RANGE-partitioned table on `ts` (yearly partitions created by migration and
  by `scripts/manage_partitions.py`). Partition pruning plus the
  (instrument_id, timeframe, ts) index is what keeps a backtest query bounded.
* `daily_candles` - daily/weekly/monthly. Small enough (a few million rows) to
  leave unpartitioned, and it is scanned *across* instruments, which
  partitioning by time would not help.
* Ticks are NOT stored in PostgreSQL by default. The live feed writes the
  latest tick to Redis; `live_ticks` exists for opt-in recording windows only
  (debugging a feed problem), with a retention policy.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class IntradayCandle(Base):
    __tablename__ = "intraday_candles"
    __table_args__ = (
        PrimaryKeyConstraint("ts", "instrument_id", "timeframe", name="pk_intraday_candles"),
        Index("ix_intraday_instrument_tf_ts", "instrument_id", "timeframe", "ts"),
        {"postgresql_partition_by": "RANGE (ts)"},
    )

    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    instrument_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    timeframe: Mapped[str] = mapped_column(String(5), nullable=False)

    open: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    high: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    low: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    close: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, default=0)

    # Which source this row came from - a backtest must never mix MOCK with
    # HISTORICAL_IMPORT without knowing it.
    source: Mapped[str] = mapped_column(String(30), default="HISTORICAL_IMPORT")
    source_id: Mapped[uuid.UUID | None] = mapped_column()


class DailyCandle(Base):
    __tablename__ = "daily_candles"
    __table_args__ = (
        PrimaryKeyConstraint("instrument_id", "timeframe", "ts", name="pk_daily_candles"),
        Index("ix_daily_candles_ts", "ts"),
        Index("ix_daily_candles_tf_ts", "timeframe", "ts"),
    )

    instrument_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    timeframe: Mapped[str] = mapped_column(String(5), nullable=False, default="1d")
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    open: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    high: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    low: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    close: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, default=0)
    # Split/bonus adjusted close, populated by the corporate-action job.
    adjusted_close: Mapped[float | None] = mapped_column(Numeric(14, 4))
    source: Mapped[str] = mapped_column(String(30), default="HISTORICAL_IMPORT")


class DataSource(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Provenance. Every candle points back to one of these."""

    __tablename__ = "data_sources"

    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(30))        # DataSourceKind
    description: Mapped[str | None] = mapped_column(Text)
    uri: Mapped[str | None] = mapped_column(String(500))
    is_trusted: Mapped[bool] = mapped_column(Boolean, default=True)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)


class DataImportJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Resumable import. `cursor` holds whatever the importer needs to pick up
    exactly where it stopped (symbol + last timestamp), so a 180 GB import
    survives a reboot."""

    __tablename__ = "data_import_jobs"
    __table_args__ = (Index("ix_import_jobs_status", "status", "created_at"),)

    name: Mapped[str] = mapped_column(String(200))
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("data_sources.id"))
    source_path: Mapped[str | None] = mapped_column(String(500))
    timeframe: Mapped[str] = mapped_column(String(5), default="1m")
    status: Mapped[str] = mapped_column(String(20), default="QUEUED", index=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    total_symbols: Mapped[int] = mapped_column(Integer, default=0)
    completed_symbols: Mapped[int] = mapped_column(Integer, default=0)
    rows_read: Mapped[int] = mapped_column(BigInteger, default=0)
    rows_inserted: Mapped[int] = mapped_column(BigInteger, default=0)
    rows_skipped_duplicate: Mapped[int] = mapped_column(BigInteger, default=0)
    rows_rejected: Mapped[int] = mapped_column(BigInteger, default=0)

    cursor: Mapped[dict] = mapped_column(JSONB, default=dict)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    last_error: Mapped[str | None] = mapped_column(Text)
    report: Mapped[dict] = mapped_column(JSONB, default=dict)


class DataImportFailure(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "data_import_failures"
    __table_args__ = (Index("ix_import_failures_job", "job_id"),)

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_import_jobs.id", ondelete="CASCADE")
    )
    source_symbol: Mapped[str | None] = mapped_column(String(80))
    reason: Mapped[str] = mapped_column(String(200))
    sample_row: Mapped[dict | None] = mapped_column(JSONB)
    row_count: Mapped[int] = mapped_column(Integer, default=1)


class DataQualityReport(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "data_quality_reports"
    __table_args__ = (
        Index("ix_dq_instrument_tf", "instrument_id", "timeframe", "generated_at"),
    )

    instrument_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE")
    )
    timeframe: Mapped[str] = mapped_column(String(5))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    total_records: Mapped[int] = mapped_column(BigInteger, default=0)
    earliest_date: Mapped[date | None] = mapped_column(Date)
    latest_date: Mapped[date | None] = mapped_column(Date)
    expected_sessions: Mapped[int] = mapped_column(Integer, default=0)
    present_sessions: Mapped[int] = mapped_column(Integer, default=0)
    missing_sessions: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_records: Mapped[int] = mapped_column(Integer, default=0)
    invalid_ohlc_records: Mapped[int] = mapped_column(Integer, default=0)
    zero_volume_records: Mapped[int] = mapped_column(Integer, default=0)
    completeness_pct: Mapped[float] = mapped_column(Numeric(6, 3), default=0)
    missing_ranges: Mapped[dict] = mapped_column(JSONB, default=dict)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)


class DataAvailability(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Fast lookup of 'do we have usable data for X at timeframe T?'.

    A backtest checks this before running, so a strategy never silently tests
    on 40 of 3,000 instruments and reports it as a universe-wide result.
    """

    __tablename__ = "data_availability"
    __table_args__ = (
        Index("ix_availability_instrument_tf", "instrument_id", "timeframe", unique=True),
    )

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE")
    )
    timeframe: Mapped[str] = mapped_column(String(5))
    first_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    record_count: Mapped[int] = mapped_column(BigInteger, default=0)
    completeness_pct: Mapped[float] = mapped_column(Numeric(6, 3), default=0)
    is_usable: Mapped[bool] = mapped_column(Boolean, default=False)


class LiveTick(Base):
    """Opt-in tick recording only - see the module docstring."""

    __tablename__ = "live_ticks"
    __table_args__ = (
        PrimaryKeyConstraint("ts", "instrument_token", name="pk_live_ticks"),
        Index("ix_live_ticks_ts", "ts"),
    )

    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    instrument_token: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_price: Mapped[float] = mapped_column(Numeric(14, 4))
    volume: Mapped[int | None] = mapped_column(BigInteger)
    oi: Mapped[int | None] = mapped_column(BigInteger)
    payload: Mapped[dict | None] = mapped_column(JSONB)


class MarketStatusLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "market_status_log"

    exchange: Mapped[str] = mapped_column(String(10), index=True)
    status: Mapped[str] = mapped_column(String(20))
    feed_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    last_tick_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    subscribed_count: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(Text)
