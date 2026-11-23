"""Trend indicators: SMA, EMA, MACD, Supertrend, ADX."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.strategies.indicators.volatility import atr


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """Wilder-style seeding: the first value is the SMA of the first `period`
    points, so two implementations of "9 EMA" agree on historical data."""
    if period <= 0:
        raise ValueError("period must be positive")
    out = series.ewm(span=period, adjust=False, min_periods=period).mean()
    return out


def macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame(
        {
            "macd": macd_line,
            "signal": signal_line,
            "histogram": macd_line - signal_line,
        }
    )


def supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    """Supertrend.

    The band-carry rule (a band only tightens while the trend holds) is
    inherently sequential; it is computed in one forward pass. NumPy arrays
    rather than .iloc keep it fast enough for 3,000 instruments.
    """
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    atr_values = atr(df, period).to_numpy(dtype=float)

    hl2 = (high + low) / 2.0
    upper_basic = hl2 + multiplier * atr_values
    lower_basic = hl2 - multiplier * atr_values

    n = len(df)
    upper = np.full(n, np.nan)
    lower = np.full(n, np.nan)
    trend = np.full(n, np.nan)
    line = np.full(n, np.nan)

    started = False
    for i in range(n):
        if np.isnan(atr_values[i]):
            continue
        if not started:
            upper[i], lower[i] = upper_basic[i], lower_basic[i]
            trend[i] = 1.0
            line[i] = lower[i]
            started = True
            continue

        prev_upper = upper[i - 1]
        prev_lower = lower[i - 1]
        upper[i] = (
            upper_basic[i]
            if (upper_basic[i] < prev_upper or close[i - 1] > prev_upper)
            else prev_upper
        )
        lower[i] = (
            lower_basic[i]
            if (lower_basic[i] > prev_lower or close[i - 1] < prev_lower)
            else prev_lower
        )

        prev_trend = trend[i - 1]
        if prev_trend == 1.0 and close[i] < lower[i]:
            trend[i] = -1.0
        elif prev_trend == -1.0 and close[i] > upper[i]:
            trend[i] = 1.0
        else:
            trend[i] = prev_trend
        line[i] = lower[i] if trend[i] == 1.0 else upper[i]

    return pd.DataFrame(
        {
            "supertrend": line,
            "trend": trend,          # 1 = up, -1 = down
            "upper_band": upper,
            "lower_band": lower,
        },
        index=df.index,
    )


def adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Average Directional Index with Wilder smoothing."""
    high, low = df["high"], df["low"]

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index
    )

    atr_values = atr(df, period)
    alpha = 1.0 / period
    plus_di = 100 * plus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean() / atr_values
    minus_di = (
        100 * minus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean() / atr_values
    )

    denom = (plus_di + minus_di).replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / denom
    adx_values = dx.ewm(alpha=alpha, adjust=False, min_periods=period).mean()

    return pd.DataFrame({"adx": adx_values, "plus_di": plus_di, "minus_di": minus_di})


def crossover(fast: pd.Series, slow: pd.Series) -> pd.Series:
    """True on the bar where `fast` crosses above `slow`.

    Requires the previous bar to be strictly below, so a series that merely
    touches and stays does not fire repeatedly.
    """
    prev_below = fast.shift(1) <= slow.shift(1)
    now_above = fast > slow
    return (prev_below & now_above).eq(True)


def crossunder(fast: pd.Series, slow: pd.Series) -> pd.Series:
    prev_above = fast.shift(1) >= slow.shift(1)
    now_below = fast < slow
    return (prev_above & now_below).eq(True)
