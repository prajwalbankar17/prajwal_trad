"""Transaction-cost model.

Costs decide whether a strategy is viable. These tests pin the model to known
values so a change to the rates is deliberate, not accidental.
"""

from __future__ import annotations

import pytest

from app.core.charges import ChargesConfig, compute_charges, net_pnl


def test_intraday_stt_is_charged_on_sell_leg_only():
    breakdown = compute_charges(
        entry_price=100, exit_price=110, quantity=100, intraday=True, side="BUY"
    )
    buy_leg, sell_leg = breakdown.legs
    assert buy_leg["stt"] == 0
    assert sell_leg["stt"] > 0


def test_brokerage_is_capped_per_order():
    cfg = ChargesConfig()
    # A 50 lakh turnover would be 0.03% = Rs 1,500 without the cap.
    breakdown = compute_charges(
        entry_price=5000, exit_price=5000, quantity=1000, intraday=True
    )
    for leg in breakdown.legs:
        assert leg["brokerage"] == pytest.approx(cfg.intraday_brokerage_cap)


def test_entry_only_charges_single_leg():
    breakdown = compute_charges(entry_price=100, exit_price=None, quantity=50)
    assert len(breakdown.legs) == 1
    assert breakdown.legs[0]["side"] == "BUY"


def test_net_pnl_is_gross_minus_charges():
    result = net_pnl(entry_price=100, exit_price=105, quantity=200, side="BUY")
    assert result["gross_pnl"] == pytest.approx(1000.0)
    assert result["net_pnl"] == pytest.approx(
        result["gross_pnl"] - result["charges"]["total"]
    )
    assert result["net_pnl"] < result["gross_pnl"]


def test_short_trade_pnl_is_inverted():
    result = net_pnl(entry_price=105, exit_price=100, quantity=200, side="SELL")
    assert result["gross_pnl"] == pytest.approx(1000.0)


def test_charges_scale_with_turnover():
    small = compute_charges(entry_price=100, exit_price=100, quantity=10)
    large = compute_charges(entry_price=100, exit_price=100, quantity=1000)
    assert large.total > small.total


def test_delivery_attracts_stt_on_both_legs():
    breakdown = compute_charges(
        entry_price=100, exit_price=110, quantity=100, intraday=False, side="BUY"
    )
    assert all(leg["stt"] > 0 for leg in breakdown.legs)


def test_zero_rate_config_produces_zero_charges():
    free = ChargesConfig(
        intraday_brokerage_pct=0, intraday_brokerage_cap=0, stt_intraday_sell_pct=0,
        exchange_txn_pct=0, sebi_charges_per_crore=0, stamp_duty_buy_intraday_pct=0,
        gst_pct=0, ipft_pct=0,
    )
    breakdown = compute_charges(
        entry_price=100, exit_price=110, quantity=100, config=free
    )
    assert breakdown.total == 0
