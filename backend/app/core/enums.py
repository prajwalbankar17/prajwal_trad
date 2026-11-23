"""Shared enumerations.

These are the vocabulary of the whole platform; both SQLAlchemy models and
Pydantic schemas import from here so a value can never drift between layers.
"""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


# --- Market ---------------------------------------------------------------


class Exchange(StrEnum):
    NSE = "NSE"
    BSE = "BSE"
    NFO = "NFO"
    BFO = "BFO"


class Segment(StrEnum):
    EQUITY = "EQUITY"
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"
    INDEX = "INDEX"


class Timeframe(StrEnum):
    M1 = "1m"
    M3 = "3m"
    M5 = "5m"
    M10 = "10m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    D1 = "1d"
    W1 = "1w"
    MO1 = "1M"


TIMEFRAME_MINUTES: dict[str, int] = {
    Timeframe.M1: 1,
    Timeframe.M3: 3,
    Timeframe.M5: 5,
    Timeframe.M10: 10,
    Timeframe.M15: 15,
    Timeframe.M30: 30,
    Timeframe.H1: 60,
    Timeframe.D1: 375,  # one NSE equity session
}

INTRADAY_TIMEFRAMES = [
    Timeframe.M1,
    Timeframe.M3,
    Timeframe.M5,
    Timeframe.M10,
    Timeframe.M15,
    Timeframe.M30,
    Timeframe.H1,
]


class DataSourceKind(StrEnum):
    """Never let a caller confuse one of these for another."""

    HISTORICAL_IMPORT = "HISTORICAL_IMPORT"
    BROKER_HISTORICAL = "BROKER_HISTORICAL"
    BROKER_LIVE = "BROKER_LIVE"
    DELAYED = "DELAYED"
    MOCK = "MOCK"


class MarketStatus(StrEnum):
    PRE_OPEN = "PRE_OPEN"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    HOLIDAY = "HOLIDAY"
    POST_CLOSE = "POST_CLOSE"


# --- Strategy / signal ----------------------------------------------------


class StrategyCategory(StrEnum):
    PRICE_ACTION = "PRICE_ACTION"
    INDICATOR = "INDICATOR"
    INTRADAY = "INTRADAY"
    VOLUME = "VOLUME"
    COMBINATION = "COMBINATION"


class Direction(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class SignalState(StrEnum):
    GENERATED = "GENERATED"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    PENDING = "PENDING"
    PAPER_EXECUTED = "PAPER_EXECUTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class CombinationLogic(StrEnum):
    AND = "AND"
    OR = "OR"
    WEIGHTED = "WEIGHTED"
    MIN_CONFIRMATIONS = "MIN_CONFIRMATIONS"


# --- Trading --------------------------------------------------------------


class ExecutionMode(StrEnum):
    PAPER = "PAPER"
    LIVE = "LIVE"  # present for schema completeness; never executable here


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SL_M = "SL-M"


class ProductType(StrEnum):
    MIS = "MIS"      # intraday margin
    CNC = "CNC"      # delivery
    NRML = "NRML"    # carry-forward F&O


class OrderStatus(StrEnum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class PositionStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    PARTIALLY_CLOSED = "PARTIALLY_CLOSED"


class ExitReason(StrEnum):
    TARGET_HIT = "TARGET_HIT"
    STOP_LOSS_HIT = "STOP_LOSS_HIT"
    TRAILING_STOP = "TRAILING_STOP"
    STRATEGY_EXIT = "STRATEGY_EXIT"
    SESSION_END = "SESSION_END"
    RISK_LIMIT = "RISK_LIMIT"
    MANUAL = "MANUAL"
    KILL_SWITCH = "KILL_SWITCH"


# --- Jobs -----------------------------------------------------------------


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class NotificationChannel(StrEnum):
    IN_APP = "IN_APP"
    TELEGRAM = "TELEGRAM"
    EMAIL = "EMAIL"


class NotificationEvent(StrEnum):
    NEW_SIGNAL = "NEW_SIGNAL"
    PAPER_TRADE_ENTERED = "PAPER_TRADE_ENTERED"
    STOP_LOSS_TRIGGERED = "STOP_LOSS_TRIGGERED"
    TARGET_ACHIEVED = "TARGET_ACHIEVED"
    TRADE_EXITED = "TRADE_EXITED"
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    STRATEGY_DISABLED = "STRATEGY_DISABLED"
    BROKER_DISCONNECTED = "BROKER_DISCONNECTED"
    MARKET_DATA_DISCONNECTED = "MARKET_DATA_DISCONNECTED"
    BACKTEST_COMPLETED = "BACKTEST_COMPLETED"
    IMPORT_COMPLETED = "IMPORT_COMPLETED"
    SYSTEM_ERROR = "SYSTEM_ERROR"


class TradingModule(StrEnum):
    EQUITY = "EQUITY"
    FNO = "FNO"
