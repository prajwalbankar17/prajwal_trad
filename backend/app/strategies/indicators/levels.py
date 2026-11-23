"""Price levels: previous-day high/low, CPR, pivots, opening range, swings.

Every function here is session-aware and deliberately uses only *completed*
prior sessions. `previous_day_levels` for 2024-06-05 uses 2024-06-04 and never
peeks at 2024-06-05's own high - that mistake makes a backtest look brilliant
and a live run look broken.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _daily_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    key = pd.to_datetime(df["ts"]).dt.date
    return df.groupby(key).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )


def previous_day_levels(df: pd.DataFrame) -> pd.DataFrame:
    """PDH / PDL / PDC broadcast onto every intraday row of the next session."""
    daily = _daily_ohlc(df)
    prev = daily.shift(1)  # the shift is the whole point: strictly prior session
    key = pd.to_datetime(df["ts"]).dt.date

    return pd.DataFrame(
        {
            "pdh": key.map(prev["high"]).to_numpy(dtype=float),
            "pdl": key.map(prev["low"]).to_numpy(dtype=float),
            "pdc": key.map(prev["close"]).to_numpy(dtype=float),
            "pdo": key.map(prev["open"]).to_numpy(dtype=float),
        },
        index=df.index,
    )


def cpr(df: pd.DataFrame) -> pd.DataFrame:
    """Central Pivot Range from the previous session.

    pivot = (H + L + C) / 3; BC = (H + L) / 2; TC = 2*pivot - BC.
    TC and BC are then ordered so `tc >= bc` regardless of which formula wins -
    a narrow CPR often inverts them.
    """
    daily = _daily_ohlc(df)
    prev = daily.shift(1)

    pivot = (prev["high"] + prev["low"] + prev["close"]) / 3.0
    bc = (prev["high"] + prev["low"]) / 2.0
    tc = 2 * pivot - bc

    top = np.maximum(tc, bc)
    bottom = np.minimum(tc, bc)
    width = (top - bottom) / pivot.replace(0, np.nan)

    frame = pd.DataFrame(
        {"pivot": pivot, "tc": top, "bc": bottom, "cpr_width": width}, index=daily.index
    )
    key = pd.to_datetime(df["ts"]).dt.date
    return pd.DataFrame(
        {col: key.map(frame[col]).to_numpy(dtype=float) for col in frame.columns},
        index=df.index,
    )


def pivot_points(df: pd.DataFrame) -> pd.DataFrame:
    """Classic floor-trader pivots (R1-R3 / S1-S3) from the prior session."""
    daily = _daily_ohlc(df)
    prev = daily.shift(1)

    pivot = (prev["high"] + prev["low"] + prev["close"]) / 3.0
    span = prev["high"] - prev["low"]

    frame = pd.DataFrame(
        {
            "pivot": pivot,
            "r1": 2 * pivot - prev["low"],
            "s1": 2 * pivot - prev["high"],
            "r2": pivot + span,
            "s2": pivot - span,
            "r3": prev["high"] + 2 * (pivot - prev["low"]),
            "s3": prev["low"] - 2 * (prev["high"] - pivot),
        },
        index=daily.index,
    )
    key = pd.to_datetime(df["ts"]).dt.date
    return pd.DataFrame(
        {col: key.map(frame[col]).to_numpy(dtype=float) for col in frame.columns},
        index=df.index,
    )


def opening_range(df: pd.DataFrame, minutes: int = 15) -> pd.DataFrame:
    """Opening Range high/low for each session.

    Rows *inside* the opening range get NaN: the range is not yet known while
    it is forming, and a strategy must not trade a level it could not have had.
    """
    ts = pd.to_datetime(df["ts"])
    key = ts.dt.date

    session_open = ts.groupby(key).transform("min")
    elapsed = (ts - session_open).dt.total_seconds() / 60.0
    in_range = elapsed < minutes

    masked_high = df["high"].where(in_range)
    masked_low = df["low"].where(in_range)

    or_high = masked_high.groupby(key).transform("max")
    or_low = masked_low.groupby(key).transform("min")

    return pd.DataFrame(
        {
            "or_high": or_high.where(~in_range),
            "or_low": or_low.where(~in_range),
            "or_range": (or_high - or_low).where(~in_range),
            "in_opening_range": in_range,
            "minutes_since_open": elapsed,
        },
        index=df.index,
    )


def swing_levels(df: pd.DataFrame, lookback: int = 5) -> pd.DataFrame:
    """Confirmed swing highs/lows.

    A swing at bar *i* is only confirmed `lookback` bars later, so the
    confirmed value is shifted forward by `lookback`. Without that shift this
    is textbook look-ahead bias: the pattern is only visible in hindsight.
    """
    high, low = df["high"], df["low"]
    window = 2 * lookback + 1

    is_high = high == high.rolling(window=window, center=True, min_periods=window).max()
    is_low = low == low.rolling(window=window, center=True, min_periods=window).min()

    swing_high = high.where(is_high).shift(lookback).ffill()
    swing_low = low.where(is_low).shift(lookback).ffill()

    return pd.DataFrame(
        {
            "swing_high": swing_high,
            "swing_low": swing_low,
            "is_swing_high": is_high.shift(lookback).eq(True),
            "is_swing_low": is_low.shift(lookback).eq(True),
        },
        index=df.index,
    )
