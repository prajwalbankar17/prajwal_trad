"""Performance metrics, including the honesty guards."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.engines.metrics import MIN_OBSERVATIONS_FOR_RATIOS, Trade, compute, overfitting_flags


def make_trades(pnls: list[float], start: date = date(2024, 1, 1)) -> list[Trade]:
    return [
        Trade(
            entry_time=start + timedelta(days=i),
            exit_time=start + timedelta(days=i),
            net_pnl=p,
            gross_pnl=p + 10,
            charges=10,
            risk=100,
        )
        for i, p in enumerate(pnls)
    ]


def test_no_trades_reports_nothing_rather_than_zeros():
    m = compute([], initial_capital=100_000)
    assert m.total_trades == 0
    assert any("No trades" in note for note in m.notes)


def test_win_rate_and_counts():
    m = compute(make_trades([100, -50, 200, -25]), initial_capital=100_000)
    assert m.total_trades == 4
    assert m.winning_trades == 2
    assert m.losing_trades == 2
    assert m.win_rate == pytest.approx(50.0)


def test_profit_factor_is_gross_profit_over_gross_loss():
    m = compute(make_trades([100, 100, -50]), initial_capital=100_000)
    assert m.profit_factor == pytest.approx(200 / 50)


def test_profit_factor_is_none_without_losses():
    m = compute(make_trades([100, 50]), initial_capital=100_000)
    assert m.profit_factor is None
    assert any("undefined" in note for note in m.notes)


def test_net_profit_uses_net_not_gross():
    trades = make_trades([100, -50])
    m = compute(trades, initial_capital=100_000)
    assert m.net_profit == pytest.approx(50.0)
    assert m.gross_profit != m.net_profit


def test_max_drawdown_measured_from_the_peak():
    # Equity: 100k -> 101k -> 100.5k -> 100.7k.  Peak 101k, trough 100.5k.
    m = compute(make_trades([1000, -500, 200]), initial_capital=100_000)
    assert m.max_drawdown == pytest.approx(500.0)
    assert m.max_drawdown_pct == pytest.approx(500 / 101_000 * 100, abs=1e-3)


def test_consecutive_streaks():
    m = compute(make_trades([10, 10, 10, -5, -5, 10]), initial_capital=100_000)
    assert m.max_consecutive_wins == 3
    assert m.max_consecutive_losses == 2


def test_sharpe_is_none_with_too_few_observations():
    m = compute(make_trades([10, -5, 20]), initial_capital=100_000)
    assert m.sharpe_ratio is None
    assert any("Sharpe" in note for note in m.notes)


def test_sharpe_is_computed_with_enough_observations():
    pnls = [100 if i % 3 else -40 for i in range(MIN_OBSERVATIONS_FOR_RATIOS + 10)]
    m = compute(make_trades(pnls), initial_capital=1_000_000)
    assert m.sharpe_ratio is not None


def test_small_sample_is_flagged():
    m = compute(make_trades([10] * 5), initial_capital=100_000)
    assert any("small sample" in note for note in m.notes)


def test_expectancy_combines_win_rate_and_average_sizes():
    m = compute(make_trades([100, 100, -100, -100]), initial_capital=100_000)
    # 50% x 100 + 50% x (-100) = 0
    assert m.expectancy == pytest.approx(0.0)


def test_monthly_breakdown_groups_by_month():
    trades = make_trades([10] * 40, start=date(2024, 1, 1))
    m = compute(trades, initial_capital=100_000)
    assert "2024-01" in m.monthly_performance
    assert "2024-02" in m.monthly_performance


def test_equity_curve_starts_at_initial_capital():
    m = compute(make_trades([100, -50]), initial_capital=100_000)
    assert m.equity_curve[0]["equity"] == pytest.approx(100_000)
    assert m.equity_curve[-1]["equity"] == pytest.approx(100_050)


def test_overfitting_flags_catch_a_collapse_out_of_sample():
    in_sample = compute(make_trades([100] * 40 + [-20] * 5), initial_capital=100_000)
    out_sample = compute(make_trades([-50] * 20), initial_capital=100_000)
    result = overfitting_flags(in_sample, out_sample)
    assert result["likely_overfit"]
    assert result["flags"]


def test_overfitting_flags_are_quiet_when_results_hold_up():
    pnls = [100 if i % 3 else -40 for i in range(60)]
    in_sample = compute(make_trades(pnls), initial_capital=1_000_000)
    out_sample = compute(make_trades(pnls[:30]), initial_capital=1_000_000)
    result = overfitting_flags(in_sample, out_sample)
    assert not result["likely_overfit"]
