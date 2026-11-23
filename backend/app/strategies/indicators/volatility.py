"""Volatility: True Range, ATR, Bollinger Bands."""

from __future__ import annotations

import pandas as pd


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    ranges = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder's ATR (RMA), not a simple moving average of True Range."""
    tr = true_range(df)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def bollinger_bands(
    close: pd.Series, period: int = 20, std_dev: float = 2.0
) -> pd.DataFrame:
    middle = close.rolling(window=period, min_periods=period).mean()
    # ddof=0: population std, which is what the standard Bollinger definition
    # uses. ddof=1 shifts the bands slightly and will not match a charting app.
    deviation = close.rolling(window=period, min_periods=period).std(ddof=0)
    upper = middle + std_dev * deviation
    lower = middle - std_dev * deviation
    width = (upper - lower) / middle.replace(0, pd.NA)
    return pd.DataFrame(
        {
            "middle": middle,
            "upper": upper,
            "lower": lower,
            "bandwidth": width,
            "percent_b": (close - lower) / (upper - lower).replace(0, pd.NA),
        }
    )
