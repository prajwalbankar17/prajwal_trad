"""Candle aggregation.

Higher timeframes are derived from 1-minute candles rather than stored
separately, except for daily/weekly/monthly which live in `daily_candles`.

Two rules this module exists to enforce:

1. Buckets are anchored to the session open (09:15 IST), not to the clock hour.
   A 15m bucket is 09:15-09:30, not 09:15-09:30 for some days and 09:00-09:15
   for others. Getting this wrong silently shifts every signal.
2. A partial trailing bucket is returned only when `include_partial=True`, and
   it is flagged. A strategy evaluating a half-formed candle is look-ahead bias
   in reverse - it acts on information the candle does not yet contain.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

from app.core.enums import TIMEFRAME_MINUTES, Timeframe
from app.core.market_calendar import IST, MARKET_OPEN, to_ist


@dataclass
class Candle:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    is_partial: bool = False


def bucket_start(ts: datetime, minutes: int) -> datetime:
    """Session-anchored bucket start for an intraday timestamp."""
    ts = to_ist(ts)
    session_open = datetime.combine(ts.date(), MARKET_OPEN, tzinfo=IST)
    if ts < session_open:
        return session_open
    elapsed = int((ts - session_open).total_seconds() // 60)
    return session_open + timedelta(minutes=(elapsed // minutes) * minutes)


def resample(
    candles: list[Candle] | pd.DataFrame,
    target: str,
    *,
    include_partial: bool = False,
) -> list[Candle]:
    """Aggregate 1-minute candles into `target`.

    Raises if `target` is not an intraday timeframe - daily and above come from
    `daily_candles`, not from resampling minutes, because a day's true OHLC
    includes pre-open and auction prints the minute series does not carry.
    """
    if target == Timeframe.M1:
        return list(candles) if isinstance(candles, list) else _df_to_candles(candles)

    minutes = TIMEFRAME_MINUTES.get(target)
    if minutes is None or target in (Timeframe.D1, Timeframe.W1, Timeframe.MO1):
        raise ValueError(
            f"{target!r} cannot be produced by resampling minute candles; "
            "read it from daily_candles instead."
        )

    rows = _df_to_candles(candles) if isinstance(candles, pd.DataFrame) else list(candles)
    if not rows:
        return []

    rows.sort(key=lambda c: c.ts)
    out: list[Candle] = []
    current: Candle | None = None
    current_key: datetime | None = None
    expected = minutes  # how many 1m candles a complete bucket holds
    count = 0

    for row in rows:
        key = bucket_start(row.ts, minutes)
        if current_key is None or key != current_key:
            if current is not None:
                current.is_partial = count < expected
                out.append(current)
            current_key = key
            current = Candle(
                ts=key,
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                volume=row.volume,
            )
            count = 1
        else:
            assert current is not None
            current.high = max(current.high, row.high)
            current.low = min(current.low, row.low)
            current.close = row.close
            current.volume += row.volume
            count += 1

    if current is not None:
        current.is_partial = count < expected
        out.append(current)

    if not include_partial:
        out = [c for c in out if not c.is_partial]
    return out


def _df_to_candles(df: pd.DataFrame) -> list[Candle]:
    return [
        Candle(
            ts=to_ist(row.ts if hasattr(row, "ts") else row.Index),
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=int(row.volume),
        )
        for row in df.itertuples()
    ]


def candles_to_frame(candles: list[Candle]) -> pd.DataFrame:
    """Indicator functions take a DataFrame; this is the single conversion point."""
    return pd.DataFrame(
        {
            "ts": [c.ts for c in candles],
            "open": [c.open for c in candles],
            "high": [c.high for c in candles],
            "low": [c.low for c in candles],
            "close": [c.close for c in candles],
            "volume": [c.volume for c in candles],
        }
    )


def validate_ohlc(candle: Candle) -> list[str]:
    """Structural checks. Returns the reasons a candle is unusable."""
    problems = []
    if candle.high < candle.low:
        problems.append("high < low")
    if not (candle.low <= candle.open <= candle.high):
        problems.append("open outside [low, high]")
    if not (candle.low <= candle.close <= candle.high):
        problems.append("close outside [low, high]")
    if candle.volume < 0:
        problems.append("negative volume")
    if min(candle.open, candle.high, candle.low, candle.close) <= 0:
        problems.append("non-positive price")
    return problems
