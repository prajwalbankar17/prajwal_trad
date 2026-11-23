"""Candle aggregation and the market calendar."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.core.market_calendar import (
    IST,
    is_market_open,
    is_trading_day,
    market_status,
    next_trading_day,
    previous_trading_day,
    trading_days_between,
)
from app.marketdata.aggregation import Candle, bucket_start, resample, validate_ohlc
from tests.conftest import build_session


def to_candles(rows) -> list[Candle]:
    return [
        Candle(r["ts"], r["open"], r["high"], r["low"], r["close"], r["volume"])
        for r in rows
    ]


# --- Bucketing ------------------------------------------------------------


def test_buckets_are_anchored_to_the_session_open():
    """09:15 anchored, not clock-hour anchored - getting this wrong shifts
    every signal."""
    ts = datetime(2024, 6, 3, 9, 37, tzinfo=IST)
    assert bucket_start(ts, 15) == datetime(2024, 6, 3, 9, 30, tzinfo=IST)
    assert bucket_start(ts, 30) == datetime(2024, 6, 3, 9, 15, tzinfo=IST)
    assert bucket_start(ts, 60) == datetime(2024, 6, 3, 9, 15, tzinfo=IST)


def test_first_bucket_starts_at_market_open():
    ts = datetime(2024, 6, 3, 9, 15, tzinfo=IST)
    assert bucket_start(ts, 15) == ts


def test_resample_aggregates_ohlcv_correctly():
    rows = build_session(datetime(2024, 6, 3, tzinfo=IST), minutes=30, seed=1)
    candles = to_candles(rows)
    result = resample(candles, "15m")

    assert len(result) == 2
    first = result[0]
    source = candles[:15]
    assert first.open == source[0].open
    assert first.close == source[-1].close
    assert first.high == max(c.high for c in source)
    assert first.low == min(c.low for c in source)
    assert first.volume == sum(c.volume for c in source)


def test_partial_bucket_is_excluded_by_default():
    rows = build_session(datetime(2024, 6, 3, tzinfo=IST), minutes=20, seed=1)
    result = resample(to_candles(rows), "15m")
    assert len(result) == 1          # the trailing 5 minutes are dropped


def test_partial_bucket_is_flagged_when_requested():
    rows = build_session(datetime(2024, 6, 3, tzinfo=IST), minutes=20, seed=1)
    result = resample(to_candles(rows), "15m", include_partial=True)
    assert len(result) == 2
    assert result[-1].is_partial


def test_full_session_resamples_to_expected_counts():
    rows = build_session(datetime(2024, 6, 3, tzinfo=IST), minutes=375, seed=1)
    candles = to_candles(rows)
    assert len(resample(candles, "5m")) == 75
    assert len(resample(candles, "15m")) == 25
    # 375 is not divisible by 30, so the last bucket is partial and dropped.
    assert len(resample(candles, "30m")) == 12


def test_resampling_to_one_minute_is_a_no_op():
    candles = to_candles(build_session(datetime(2024, 6, 3, tzinfo=IST), minutes=10))
    assert len(resample(candles, "1m")) == 10


def test_daily_cannot_be_produced_by_resampling_minutes():
    candles = to_candles(build_session(datetime(2024, 6, 3, tzinfo=IST), minutes=10))
    with pytest.raises(ValueError, match="daily_candles"):
        resample(candles, "1d")


def test_resample_handles_empty_input():
    assert resample([], "15m") == []


# --- Validation -----------------------------------------------------------


def test_validate_ohlc_accepts_a_sane_candle():
    good = Candle(datetime(2024, 6, 3, tzinfo=IST), 100, 102, 99, 101, 500)
    assert validate_ohlc(good) == []


@pytest.mark.parametrize(
    "candle,expected",
    [
        (Candle(datetime(2024, 6, 3, tzinfo=IST), 100, 98, 99, 101, 5), "high < low"),
        (
            Candle(datetime(2024, 6, 3, tzinfo=IST), 105, 102, 99, 101, 5),
            "open outside [low, high]",
        ),
        (
            Candle(datetime(2024, 6, 3, tzinfo=IST), 100, 102, 99, 110, 5),
            "close outside [low, high]",
        ),
        (Candle(datetime(2024, 6, 3, tzinfo=IST), 100, 102, 99, 101, -1), "negative volume"),
        (Candle(datetime(2024, 6, 3, tzinfo=IST), 0, 102, 0, 101, 5), "non-positive price"),
    ],
)
def test_validate_ohlc_catches_bad_candles(candle, expected):
    assert expected in validate_ohlc(candle)


# --- Calendar -------------------------------------------------------------


def test_weekends_are_not_trading_days():
    assert not is_trading_day(date(2024, 6, 1))    # Saturday
    assert not is_trading_day(date(2024, 6, 2))    # Sunday
    assert is_trading_day(date(2024, 6, 3))        # Monday


def test_database_holidays_override_the_seed_list():
    custom = {date(2024, 6, 3)}
    assert not is_trading_day(date(2024, 6, 3), holidays=custom)
    assert is_trading_day(date(2024, 6, 4), holidays=custom)


def test_previous_and_next_trading_day_skip_the_weekend():
    assert previous_trading_day(date(2024, 6, 3)) == date(2024, 5, 31)
    assert next_trading_day(date(2024, 5, 31)) == date(2024, 6, 3)


def test_trading_days_between_excludes_weekends():
    days = trading_days_between(date(2024, 6, 3), date(2024, 6, 9))
    assert len(days) == 5
    assert date(2024, 6, 8) not in days


def test_market_hours_boundaries():
    assert not is_market_open(datetime(2024, 6, 3, 9, 14, tzinfo=IST))
    assert is_market_open(datetime(2024, 6, 3, 9, 15, tzinfo=IST))
    assert is_market_open(datetime(2024, 6, 3, 15, 29, tzinfo=IST))
    assert not is_market_open(datetime(2024, 6, 3, 15, 30, tzinfo=IST))


def test_market_status_phases():
    assert market_status(datetime(2024, 6, 3, 9, 5, tzinfo=IST)) == "PRE_OPEN"
    assert market_status(datetime(2024, 6, 3, 11, 0, tzinfo=IST)) == "OPEN"
    assert market_status(datetime(2024, 6, 3, 15, 45, tzinfo=IST)) == "POST_CLOSE"
    assert market_status(datetime(2024, 6, 3, 20, 0, tzinfo=IST)) == "CLOSED"
    assert market_status(datetime(2024, 6, 1, 11, 0, tzinfo=IST)) == "CLOSED"  # Saturday
