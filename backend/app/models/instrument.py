"""Instrument master, exchanges, sectors, symbol mappings, holidays, watchlists."""

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
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ExchangeRef(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "exchanges"

    code: Mapped[str] = mapped_column(String(10), unique=True, index=True)  # NSE, BSE
    name: Mapped[str] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(5), default="IN")
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Kolkata")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Sector(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "sectors"

    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    industry: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)


class Instrument(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One tradable instrument. Equity in Phase 1; the F&O columns are present
    but unused so the options engine can be added without a schema rewrite."""

    __tablename__ = "instruments"
    __table_args__ = (
        UniqueConstraint("exchange", "tradingsymbol", name="uq_instruments_exchange_symbol"),
        Index("ix_instruments_symbol_active", "tradingsymbol", "is_active"),
        Index("ix_instruments_sector", "sector_id"),
        Index("ix_instruments_segment", "segment"),
    )

    tradingsymbol: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str | None] = mapped_column(String(200), index=True)
    exchange: Mapped[str] = mapped_column(String(10), index=True)
    segment: Mapped[str] = mapped_column(String(20), default="EQUITY", index=True)
    isin: Mapped[str | None] = mapped_column(String(20), index=True)

    # Broker instrument token (Kite). Nullable until instruments are synced.
    instrument_token: Mapped[int | None] = mapped_column(BigInteger, index=True)
    exchange_token: Mapped[int | None] = mapped_column(BigInteger)

    sector_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sectors.id"))
    lot_size: Mapped[int] = mapped_column(Integer, default=1)
    tick_size: Mapped[float] = mapped_column(Numeric(10, 4), default=0.05)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_tradable: Mapped[bool] = mapped_column(Boolean, default=True)
    listed_on: Mapped[date | None] = mapped_column(Date)
    delisted_on: Mapped[date | None] = mapped_column(Date)

    # Liquidity / price filters used by universe selection.
    avg_daily_volume: Mapped[int | None] = mapped_column(BigInteger)
    avg_daily_turnover: Mapped[float | None] = mapped_column(Numeric(20, 2))
    last_price: Mapped[float | None] = mapped_column(Numeric(14, 4))
    market_cap: Mapped[float | None] = mapped_column(Numeric(20, 2))

    # --- F&O placeholders (Phase 9) ---
    expiry: Mapped[date | None] = mapped_column(Date)
    strike: Mapped[float | None] = mapped_column(Numeric(14, 4))
    option_type: Mapped[str | None] = mapped_column(String(4))  # CE / PE
    underlying_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("instruments.id"))

    meta: Mapped[dict] = mapped_column(JSONB, default=dict)

    sector: Mapped[Sector | None] = relationship(lazy="joined")


class SymbolMapping(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Maps the symbol used by an external source (the historical SQLite file,
    a broker feed) to our instrument. Symbols get renamed; this keeps history
    attached to the right company."""

    __tablename__ = "symbol_mappings"
    __table_args__ = (
        UniqueConstraint("source", "source_symbol", name="uq_symbol_mapping_source_symbol"),
        Index("ix_symbol_mappings_instrument", "instrument_id"),
    )

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE")
    )
    source: Mapped[str] = mapped_column(String(50), index=True)
    source_symbol: Mapped[str] = mapped_column(String(80), index=True)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)


class CorporateAction(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Splits, bonuses and the like. Backtests must know about these or the
    price series lies."""

    __tablename__ = "corporate_actions"
    __table_args__ = (Index("ix_corp_actions_instrument_date", "instrument_id", "ex_date"),)

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE")
    )
    action_type: Mapped[str] = mapped_column(String(30))  # SPLIT | BONUS | DIVIDEND | RENAME
    ex_date: Mapped[date] = mapped_column(Date, index=True)
    ratio_from: Mapped[float | None] = mapped_column(Numeric(14, 6))
    ratio_to: Mapped[float | None] = mapped_column(Numeric(14, 6))
    adjustment_factor: Mapped[float | None] = mapped_column(Numeric(14, 8))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_applied_to_history: Mapped[bool] = mapped_column(Boolean, default=False)


class MarketHoliday(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "market_holidays"
    __table_args__ = (
        UniqueConstraint("exchange", "holiday_date", name="uq_holiday_exchange_date"),
    )

    exchange: Mapped[str] = mapped_column(String(10), index=True)
    holiday_date: Mapped[date] = mapped_column(Date, index=True)
    description: Mapped[str | None] = mapped_column(String(200))
    is_full_day: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(40), default="manual")


class Watchlist(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "watchlists"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_watchlist_user_name"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    color: Mapped[str | None] = mapped_column(String(20))

    items: Mapped[list[WatchlistItem]] = relationship(
        back_populates="watchlist", cascade="all, delete-orphan", lazy="selectin"
    )


class WatchlistItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint("watchlist_id", "instrument_id", name="uq_watchlist_item"),
    )

    watchlist_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("watchlists.id", ondelete="CASCADE")
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE")
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(Text)
    added_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    watchlist: Mapped[Watchlist] = relationship(back_populates="items")
    instrument: Mapped[Instrument] = relationship(lazy="joined")
