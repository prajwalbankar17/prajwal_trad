"""Indicator correctness, and the two invariants the whole platform rests on:
no look-ahead, and NaN (not zero) before there is enough history."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.strategies import indicators as ind
from app.strategies.indicators.trend import crossover, crossunder

# --- Known-value tests ----------------------------------------------------


def test_sma_known_values():
    series = pd.Series([1, 2, 3, 4, 5], dtype=float)
    result = ind.sma(series, 3)
    assert pd.isna(result.iloc[0]) and pd.isna(result.iloc[1])
    assert result.iloc[2] == pytest.approx(2.0)
    assert result.iloc[4] == pytest.approx(4.0)


def test_ema_matches_manual_recursion():
    close = pd.Series([10, 11, 12, 13, 14, 15], dtype=float)
    period = 3
    result = ind.ema(close, period)

    alpha = 2 / (period + 1)
    # pandas seeds ewm from the first observation, with min_periods hiding the
    # first `period - 1` values.
    expected = close.iloc[0]
    for value in close.iloc[1:]:
        expected = alpha * value + (1 - alpha) * expected
    assert result.iloc[-1] == pytest.approx(expected)
    assert result.iloc[:2].isna().all()


def test_rsi_all_gains_is_100():
    close = pd.Series(np.arange(1, 40, dtype=float))
    assert ind.rsi(close, 14).iloc[-1] == pytest.approx(100.0)


def test_rsi_flat_series_is_50():
    close = pd.Series([100.0] * 40)
    assert ind.rsi(close, 14).iloc[-1] == pytest.approx(50.0)


def test_rsi_bounded_between_0_and_100(three_sessions):
    values = ind.rsi(three_sessions["close"], 14).dropna()
    assert values.between(0, 100).all()


def test_true_range_uses_previous_close():
    df = pd.DataFrame(
        {
            "high": [10.0, 12.0],
            "low": [9.0, 11.0],
            "close": [9.5, 11.5],
        }
    )
    tr = ind.true_range(df)
    # Second bar gapped up: |high - prev_close| = |12 - 9.5| = 2.5 beats the
    # 1.0 intrabar range.
    assert tr.iloc[1] == pytest.approx(2.5)


def test_bollinger_bands_are_symmetric(three_sessions):
    bb = ind.bollinger_bands(three_sessions["close"], 20, 2.0).dropna()
    upper_gap = bb["upper"] - bb["middle"]
    lower_gap = bb["middle"] - bb["lower"]
    assert np.allclose(upper_gap, lower_gap)


def test_vwap_resets_each_session(three_sessions):
    vwap = ind.vwap(three_sessions)
    key = pd.to_datetime(three_sessions["ts"]).dt.date
    first_rows = three_sessions.groupby(key).head(1).index
    typical = (
        three_sessions["high"] + three_sessions["low"] + three_sessions["close"]
    ) / 3
    # The first bar of each session: VWAP == that bar's typical price.
    assert np.allclose(vwap[first_rows], typical[first_rows])


def test_vwap_without_reset_is_continuous(three_sessions):
    reset = ind.vwap(three_sessions, session_reset=True)
    continuous = ind.vwap(three_sessions, session_reset=False)
    # They must differ after the first session, or the reset is not happening.
    assert not np.allclose(reset.iloc[-1], continuous.iloc[-1])


def test_relative_volume_excludes_current_bar():
    volume = pd.Series([100] * 20 + [1000])
    rel = ind.relative_volume(volume, 20)
    # Baseline is the prior 20 bars (all 100), so the spike reads as 10x.
    assert rel.iloc[-1] == pytest.approx(10.0)


# --- Session-level levels -------------------------------------------------


def test_previous_day_levels_are_nan_on_first_session(three_sessions):
    levels = ind.previous_day_levels(three_sessions)
    first_day_mask = pd.to_datetime(three_sessions["ts"]).dt.date == pd.Timestamp(
        "2024-06-03"
    ).date()
    assert levels.loc[first_day_mask, "pdh"].isna().all()


def test_previous_day_levels_match_prior_session(three_sessions):
    ts = pd.to_datetime(three_sessions["ts"])
    day1 = three_sessions[ts.dt.date == pd.Timestamp("2024-06-03").date()]
    levels = ind.previous_day_levels(three_sessions)
    day2_mask = ts.dt.date == pd.Timestamp("2024-06-04").date()

    assert levels.loc[day2_mask, "pdh"].iloc[0] == pytest.approx(day1["high"].max())
    assert levels.loc[day2_mask, "pdl"].iloc[0] == pytest.approx(day1["low"].min())


def test_previous_day_levels_never_use_current_session(three_sessions):
    """The decisive look-ahead check: PDH for day 2 must not change when day 2's
    own prices are altered."""
    levels_before = ind.previous_day_levels(three_sessions)
    ts = pd.to_datetime(three_sessions["ts"])
    day2_mask = (ts.dt.date == pd.Timestamp("2024-06-04").date()).to_numpy()

    tampered = three_sessions.copy()
    tampered.loc[day2_mask, "high"] = 9999.0
    levels_after = ind.previous_day_levels(tampered)

    pd.testing.assert_series_equal(
        levels_before.loc[day2_mask, "pdh"],
        levels_after.loc[day2_mask, "pdh"],
    )


def test_cpr_orders_tc_above_bc(three_sessions):
    frame = ind.cpr(three_sessions).dropna()
    assert (frame["tc"] >= frame["bc"]).all()


def test_opening_range_is_nan_while_forming(one_session):
    orr = ind.opening_range(one_session, 15)
    assert orr["or_high"].iloc[:15].isna().all()
    assert orr["or_high"].iloc[15:].notna().all()


def test_opening_range_matches_first_15_minutes(one_session):
    orr = ind.opening_range(one_session, 15)
    assert orr["or_high"].iloc[20] == pytest.approx(one_session["high"].iloc[:15].max())
    assert orr["or_low"].iloc[20] == pytest.approx(one_session["low"].iloc[:15].min())


def test_swing_levels_are_confirmed_not_instant(one_session):
    """A swing high is only known `lookback` bars later. Without the shift this
    is look-ahead bias."""
    swings = ind.swing_levels(one_session, 5)
    highs = one_session["high"]
    confirmed_idx = swings.index[swings["is_swing_high"]]
    for idx in confirmed_idx[:5]:
        original = idx - 5
        # The confirmed value equals the high from `lookback` bars earlier.
        assert swings["swing_high"].iloc[idx] == pytest.approx(highs.iloc[original])


# --- Invariants -----------------------------------------------------------


@pytest.mark.parametrize(
    "func,period",
    [
        (lambda df, p: ind.sma(df["close"], p), 20),
        (lambda df, p: ind.ema(df["close"], p), 20),
        (lambda df, p: ind.rsi(df["close"], p), 14),
        (lambda df, p: ind.atr(df, p), 14),
    ],
)
def test_leading_values_are_nan_not_zero(three_sessions, func, period):
    result = func(three_sessions, period)
    assert result.iloc[: period - 1].isna().all()
    assert result.iloc[period:].notna().any()


@pytest.mark.parametrize(
    "name,func",
    [
        ("ema", lambda df: ind.ema(df["close"], 20)),
        ("rsi", lambda df: ind.rsi(df["close"], 14)),
        ("atr", lambda df: ind.atr(df, 14)),
        ("macd", lambda df: ind.macd(df["close"])["macd"]),
        ("supertrend", lambda df: ind.supertrend(df, 10, 3.0)["trend"]),
        ("adx", lambda df: ind.adx(df, 14)["adx"]),
        ("bollinger", lambda df: ind.bollinger_bands(df["close"], 20, 2)["upper"]),
        ("obv", lambda df: ind.obv(df)),
    ],
)
def test_indicator_is_causal(three_sessions, name, func):
    """Truncating the future must not change any past value.

    This is the single most important property in the library: every backtest
    result is meaningless if an indicator peeks forward.
    """
    cutoff = len(three_sessions) - 50
    full = func(three_sessions)
    truncated = func(three_sessions.iloc[:cutoff].copy())

    a = full.iloc[:cutoff].reset_index(drop=True)
    b = truncated.reset_index(drop=True)
    pd.testing.assert_series_equal(a, b, check_names=False, rtol=1e-9)


def test_crossover_fires_once_per_cross():
    fast = pd.Series([1, 2, 3, 4, 5, 4, 3, 2], dtype=float)
    slow = pd.Series([3, 3, 3, 3, 3, 3, 3, 3], dtype=float)
    ups = crossover(fast, slow)
    downs = crossunder(fast, slow)
    assert ups.sum() == 1
    assert downs.sum() == 1
    assert ups.iloc[3]      # fast 3 -> 4 closes above the slow line at 3
    # Index 6 has fast == slow == 3, which is a touch, not a cross. The cross
    # completes at index 7 when fast closes strictly below.
    assert not downs.iloc[6]
    assert downs.iloc[7]


def test_supertrend_trend_is_only_plus_or_minus_one(three_sessions):
    trend = ind.supertrend(three_sessions, 10, 3.0)["trend"].dropna()
    assert set(trend.unique()).issubset({1.0, -1.0})
