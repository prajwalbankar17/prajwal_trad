"""Position sizing arithmetic, isolated from the database."""

from __future__ import annotations

import pytest

from app.engines.risk import RiskEngine


class FakeProfile:
    """Minimal stand-in so sizing can be tested without a session."""

    id = "fake"
    capital = 1_000_000.0
    max_risk_per_trade_pct = 1.0
    max_position_size_pct = 20.0
    assumed_leverage = 1.0
    max_daily_loss_pct = 3.0
    max_open_positions = 5
    max_trades_per_day = 20
    max_total_exposure_pct = 80.0
    max_sector_exposure_pct = 30.0
    max_capital_utilisation_pct = 80.0
    kill_switch_enabled = False


@pytest.fixture
def engine():
    return RiskEngine(db=None, profile=FakeProfile())


def test_size_is_risk_budget_divided_by_stop_distance(engine):
    # 1% of 10,00,000 = 10,000 risk; stop distance 10 -> 1,000 shares.
    qty, detail = engine.position_size(entry_price=100, stop_loss=90)
    assert detail["qty_by_risk"] == 1000
    # But 1,000 x 100 = 1,00,000 exceeds the 20% position cap of 2,00,000? No:
    # 2,00,000 / 100 = 2,000, so risk is the binding constraint.
    assert qty == 1000
    assert detail["binding_constraint"] == "risk_per_trade"


def test_position_size_cap_can_bind_before_risk(engine):
    # Tight stop -> huge risk-based size, but 20% of capital caps it.
    qty, detail = engine.position_size(entry_price=100, stop_loss=99.5)
    assert detail["qty_by_risk"] == 20_000
    assert detail["qty_by_position_cap"] == 2_000
    assert qty == 2_000
    assert detail["binding_constraint"] == "max_position_size"


def test_available_capital_can_bind(engine):
    qty, detail = engine.position_size(
        entry_price=100, stop_loss=90, available_capital=50_000
    )
    assert detail["qty_by_available_capital"] == 500
    assert qty == 500
    assert detail["binding_constraint"] == "available_capital"


def test_zero_stop_distance_returns_zero_not_infinity(engine):
    qty, detail = engine.position_size(entry_price=100, stop_loss=100)
    assert qty == 0
    assert "stop distance is zero" in detail["reason"]


def test_lot_size_rounds_down(engine):
    qty, _ = engine.position_size(entry_price=100, stop_loss=90, lot_size=75)
    assert qty % 75 == 0
    assert qty == 975         # 1000 rounded down to a multiple of 75


def test_leverage_increases_size_but_not_risk(engine):
    engine.profile.assumed_leverage = 5.0
    qty, detail = engine.position_size(
        entry_price=100, stop_loss=99.5, available_capital=100_000
    )
    # The position cap and available capital both scale with leverage; the
    # risk budget does not, which is the whole point.
    assert detail["qty_by_risk"] == 20_000          # unchanged by leverage
    assert detail["qty_by_position_cap"] == 10_000  # 20% of capital x 5
    assert detail["qty_by_available_capital"] == 5_000
    assert qty == 5_000                              # capital is the binding one
    assert detail["binding_constraint"] == "available_capital"


def test_short_trade_sizing_uses_absolute_distance(engine):
    long_qty, _ = engine.position_size(entry_price=100, stop_loss=90)
    short_qty, _ = engine.position_size(entry_price=100, stop_loss=110)
    assert long_qty == short_qty


def test_size_never_goes_negative(engine):
    qty, _ = engine.position_size(
        entry_price=100, stop_loss=90, available_capital=0
    )
    assert qty == 0
