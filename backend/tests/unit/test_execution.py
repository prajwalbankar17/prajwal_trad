"""Fill simulation: slippage direction, exit precedence and gap handling.

These encode the conservative choices that keep backtests honest.
"""

from __future__ import annotations

import pytest

from app.core.enums import Direction, ExitReason
from app.engines.execution import (
    SlippageModel,
    check_exit_on_candle,
    excursions,
    round_trip_pnl,
    simulate_entry,
    simulate_exit,
    update_trailing_stop,
)

# --- Slippage -------------------------------------------------------------


def test_slippage_always_works_against_the_trader_on_entry():
    model = SlippageModel(base_pct=0.1)
    buy = simulate_entry(
        reference_price=100, direction=Direction.BUY, quantity=1, slippage=model
    )
    sell = simulate_entry(
        reference_price=100, direction=Direction.SELL, quantity=1, slippage=model
    )
    assert buy.price > 100
    assert sell.price < 100


def test_slippage_works_against_the_trader_on_exit():
    model = SlippageModel(base_pct=0.1)
    # Exiting a long is a sell, so it fills lower.
    long_exit = simulate_exit(
        reference_price=100, direction=Direction.BUY, quantity=1, slippage=model
    )
    short_exit = simulate_exit(
        reference_price=100, direction=Direction.SELL, quantity=1, slippage=model
    )
    assert long_exit.price < 100
    assert short_exit.price > 100


def test_zero_slippage_fills_at_reference():
    fill = simulate_entry(
        reference_price=100,
        direction=Direction.BUY,
        quantity=1,
        slippage=SlippageModel(base_pct=0),
    )
    assert fill.price == pytest.approx(100)


# --- Exit detection -------------------------------------------------------


def test_long_stop_takes_precedence_when_both_levels_trade():
    """Without tick data we cannot know which came first, so we assume the
    unfavourable one. This understates results rather than overstating them."""
    result = check_exit_on_candle(
        direction=Direction.BUY, stop_loss=99, target=102,
        candle_open=100, candle_high=103, candle_low=98,
    )
    assert result.triggered
    assert result.reason == ExitReason.STOP_LOSS_HIT
    assert result.price == 99


def test_short_stop_takes_precedence_when_both_levels_trade():
    result = check_exit_on_candle(
        direction=Direction.SELL, stop_loss=101, target=98,
        candle_open=100, candle_high=102, candle_low=97,
    )
    assert result.reason == ExitReason.STOP_LOSS_HIT


def test_gap_through_long_stop_fills_at_the_open():
    result = check_exit_on_candle(
        direction=Direction.BUY, stop_loss=99, target=102,
        candle_open=95, candle_high=96, candle_low=94,
    )
    assert result.reason == ExitReason.STOP_LOSS_HIT
    assert result.price == 95      # worse than the stop - what really happens
    assert result.gapped


def test_gap_through_long_target_fills_at_the_open():
    result = check_exit_on_candle(
        direction=Direction.BUY, stop_loss=99, target=102,
        candle_open=105, candle_high=106, candle_low=104,
    )
    assert result.reason == ExitReason.TARGET_HIT
    assert result.price == 105
    assert result.gapped


def test_no_exit_when_price_stays_inside_the_range():
    result = check_exit_on_candle(
        direction=Direction.BUY, stop_loss=99, target=102,
        candle_open=100, candle_high=101, candle_low=99.5,
    )
    assert not result.triggered


def test_target_alone_exits_at_target():
    result = check_exit_on_candle(
        direction=Direction.BUY, stop_loss=99, target=102,
        candle_open=100, candle_high=102.5, candle_low=99.5,
    )
    assert result.reason == ExitReason.TARGET_HIT
    assert result.price == 102


# --- Trailing stop --------------------------------------------------------


def test_trailing_stop_only_moves_in_the_favourable_direction():
    raised = update_trailing_stop(
        direction=Direction.BUY, current_stop=95, entry_price=100,
        last_price=110, trail_value=5, trail_type="PERCENT",
    )
    assert raised == pytest.approx(104.5)

    kept = update_trailing_stop(
        direction=Direction.BUY, current_stop=104.5, entry_price=100,
        last_price=100, trail_value=5, trail_type="PERCENT",
    )
    assert kept == pytest.approx(104.5)   # never loosened


def test_short_trailing_stop_only_falls():
    lowered = update_trailing_stop(
        direction=Direction.SELL, current_stop=105, entry_price=100,
        last_price=90, trail_value=5, trail_type="PERCENT",
    )
    assert lowered == pytest.approx(94.5)


# --- P&L and excursions ---------------------------------------------------


def test_round_trip_reports_gross_charges_and_net_separately():
    result = round_trip_pnl(
        direction=Direction.BUY, entry_price=100, exit_price=105, quantity=100
    )
    assert result["gross_pnl"] == pytest.approx(500.0)
    assert result["charges"] > 0
    assert result["net_pnl"] == pytest.approx(result["gross_pnl"] - result["charges"])


def test_excursions_are_signed_from_the_position_viewpoint():
    mfe, mae = excursions(
        direction=Direction.BUY, entry_price=100, high=105, low=97, quantity=10
    )
    assert mfe == pytest.approx(50.0)
    assert mae == pytest.approx(-30.0)

    mfe_s, mae_s = excursions(
        direction=Direction.SELL, entry_price=100, high=105, low=97, quantity=10
    )
    assert mfe_s == pytest.approx(30.0)
    assert mae_s == pytest.approx(-50.0)
