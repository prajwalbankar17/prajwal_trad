"""Indicator library.

Every function takes a DataFrame with columns ts/open/high/low/close/volume
sorted ascending, and returns a Series or DataFrame aligned to the input index.

Two invariants hold throughout, and the tests enforce both:

1. **No look-ahead.** The value at index *i* uses only rows 0..i. Nothing is
   centred, back-filled, or computed from the full series and then shifted into
   place.
2. **Leading NaN, not zero.** Before an indicator has enough history it is NaN.
   A strategy must treat NaN as "no opinion"; filling with 0 would make an EMA
   look like a crossover on the first bar of every backtest.
"""

from app.strategies.indicators.levels import (
    cpr,
    opening_range,
    pivot_points,
    previous_day_levels,
    swing_levels,
)
from app.strategies.indicators.momentum import rsi, stochastic
from app.strategies.indicators.trend import adx, ema, macd, sma, supertrend
from app.strategies.indicators.volatility import atr, bollinger_bands, true_range
from app.strategies.indicators.volume import obv, relative_volume, volume_sma, vwap

__all__ = [
    "adx", "ema", "macd", "sma", "supertrend",
    "rsi", "stochastic",
    "atr", "bollinger_bands", "true_range",
    "obv", "relative_volume", "volume_sma", "vwap",
    "cpr", "opening_range", "pivot_points", "previous_day_levels", "swing_levels",
]
