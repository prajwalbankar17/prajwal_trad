"""Volume indicators: VWAP, volume SMA, relative volume, OBV."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _session_key(ts: pd.Series) -> pd.Series:
    return pd.to_datetime(ts).dt.date


def vwap(df: pd.DataFrame, *, session_reset: bool = True) -> pd.Series:
    """Volume-weighted average price.

    Intraday VWAP **resets at each session open**. A VWAP that runs
    continuously across days is a different, much slower indicator, and a
    strategy written against session VWAP will behave nothing like its backtest
    if this is wrong. `session_reset=False` is offered only for daily series.
    """
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = typical * df["volume"]

    if not session_reset:
        cum_pv = pv.cumsum()
        cum_vol = df["volume"].cumsum()
    else:
        key = _session_key(df["ts"])
        cum_pv = pv.groupby(key).cumsum()
        cum_vol = df["volume"].groupby(key).cumsum()

    return cum_pv / cum_vol.replace(0, np.nan)


def volume_sma(volume: pd.Series, period: int = 20) -> pd.Series:
    return volume.rolling(window=period, min_periods=period).mean()


def relative_volume(volume: pd.Series, period: int = 20) -> pd.Series:
    """Current volume as a multiple of its recent average.

    The average **excludes the current bar** - including it dampens exactly the
    spike the indicator exists to detect.
    """
    baseline = volume.shift(1).rolling(window=period, min_periods=period).mean()
    return volume / baseline.replace(0, np.nan)


def obv(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["close"].diff()).fillna(0.0)
    return (direction * df["volume"]).cumsum()
