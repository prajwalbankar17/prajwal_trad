"""Strategy contract.

A strategy is a pure function of price history and parameters. It:

* receives candles that are **already complete** - the live runner and the
  backtester both drop a forming candle before calling;
* evaluates the LAST row only, using rows 0..n-1 (no look-ahead);
* returns a `SignalProposal` or `None`, never an order;
* reports every condition it checked, passed or failed, so the UI can explain
  why a signal did or did not appear.

Strategies never size positions, never consult risk limits and never touch the
database. That separation is what lets the same class run in a backtest, in
paper trading and in a what-if, with identical results.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar

import pandas as pd

from app.core.enums import Direction, StrategyCategory


@dataclass
class Condition:
    name: str
    passed: bool
    detail: str = ""
    value: Any = None
    weight: float = 1.0

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "value": _jsonable(self.value),
            "weight": self.weight,
        }


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        return None if pd.isna(value) else round(value, 6)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


@dataclass
class SignalProposal:
    direction: Direction
    entry_price: float
    stop_loss: float
    target: float
    candle_ts: datetime
    conditions: list[Condition] = field(default_factory=list)
    reason: str = ""
    confidence: float = 0.5
    indicator_snapshot: dict = field(default_factory=dict)

    @property
    def risk_per_unit(self) -> float:
        return abs(self.entry_price - self.stop_loss)

    @property
    def risk_reward(self) -> float:
        risk = self.risk_per_unit
        return abs(self.target - self.entry_price) / risk if risk > 0 else 0.0

    def is_coherent(self) -> tuple[bool, str]:
        """Catches a strategy that proposes a nonsensical trade - a long whose
        stop is above entry, a zero-width risk, a target on the wrong side."""
        if self.entry_price <= 0:
            return False, "entry price must be positive"
        if self.risk_per_unit <= 0:
            return False, "stop-loss equals entry price (zero risk)"
        if self.direction == Direction.BUY:
            if self.stop_loss >= self.entry_price:
                return False, "long stop-loss is not below entry"
            if self.target <= self.entry_price:
                return False, "long target is not above entry"
        else:
            if self.stop_loss <= self.entry_price:
                return False, "short stop-loss is not above entry"
            if self.target >= self.entry_price:
                return False, "short target is not below entry"
        return True, ""

    def as_dict(self) -> dict:
        return {
            "direction": str(self.direction),
            "entry_price": round(self.entry_price, 4),
            "stop_loss": round(self.stop_loss, 4),
            "target": round(self.target, 4),
            "risk_reward": round(self.risk_reward, 3),
            "confidence": round(self.confidence, 3),
            "reason": self.reason,
            "conditions": [c.as_dict() for c in self.conditions],
            "indicators": self.indicator_snapshot,
        }


@dataclass
class StrategyContext:
    """Everything a strategy may look at."""

    df: pd.DataFrame                 # complete candles, ascending, ts/o/h/l/c/v
    params: dict
    timeframe: str
    instrument_id: Any = None
    tradingsymbol: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def last(self) -> pd.Series:
        return self.df.iloc[-1]

    @property
    def candle_ts(self) -> datetime:
        return self.df["ts"].iloc[-1]

    def param(self, key: str, default: Any = None) -> Any:
        return self.params.get(key, default)


class BaseStrategy(ABC):
    """Base class for every strategy in the library."""

    code: ClassVar[str] = ""
    name: ClassVar[str] = ""
    category: ClassVar[StrategyCategory] = StrategyCategory.INDICATOR
    description: ClassVar[str] = ""
    default_parameters: ClassVar[dict] = {}
    parameter_schema: ClassVar[dict] = {}
    supported_timeframes: ClassVar[list[str]] = ["5m", "15m", "30m", "1h"]
    default_timeframe: ClassVar[str] = "5m"
    module: ClassVar[str] = "EQUITY"
    # Bars needed before the strategy can say anything. The runner refuses to
    # evaluate with less, instead of returning a signal built on NaNs.
    min_bars: ClassVar[int] = 50

    def __init__(self, params: dict | None = None) -> None:
        self.params = {**self.default_parameters, **(params or {})}

    # -- helpers ---------------------------------------------------------

    def _stop_and_target(
        self,
        entry: float,
        direction: Direction,
        *,
        stop_distance: float,
        rr: float,
    ) -> tuple[float, float]:
        """Derive stop and target from a risk distance and a risk/reward ratio."""
        if direction == Direction.BUY:
            return entry - stop_distance, entry + stop_distance * rr
        return entry + stop_distance, entry - stop_distance * rr

    @staticmethod
    def _ok(conditions: list[Condition]) -> bool:
        return all(c.passed for c in conditions)

    # -- contract --------------------------------------------------------

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        """Attach the indicator columns this strategy needs.

        Called once per instrument per run, not once per bar - this is what
        keeps a 3,000-instrument backtest tractable.
        """
        return df

    @abstractmethod
    def evaluate(self, ctx: StrategyContext) -> SignalProposal | None:
        """Inspect the final row of `ctx.df` and propose a trade, or not."""

    def describe(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "category": str(self.category),
            "description": self.description,
            "parameters": self.params,
            "parameter_schema": self.parameter_schema,
            "supported_timeframes": self.supported_timeframes,
            "min_bars": self.min_bars,
            "module": self.module,
        }
