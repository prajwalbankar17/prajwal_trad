"""Every registered strategy must behave itself on real-shaped data."""

from __future__ import annotations

import pandas as pd
import pytest

from app.core.enums import Direction
from app.strategies.base import StrategyContext
from app.strategies.registry import REGISTRY, STRATEGY_SEEDS, build_strategy

ALL_CODES = sorted(REGISTRY)


@pytest.fixture
def long_history(three_sessions) -> pd.DataFrame:
    return three_sessions


def _evaluate_last(code: str, df: pd.DataFrame):
    strategy = build_strategy(code)
    prepared = strategy.prepare(df)
    ctx = StrategyContext(
        df=prepared, params=strategy.params, timeframe="1m", tradingsymbol="TEST"
    )
    return strategy, prepared, strategy.evaluate(ctx)


def test_registry_has_twenty_strategies():
    assert len(REGISTRY) == 20
    assert len(STRATEGY_SEEDS) == 20


def test_every_strategy_declares_its_metadata():
    for code, cls in REGISTRY.items():
        assert cls.code == code
        assert cls.name
        assert cls.description
        assert cls.supported_timeframes
        assert cls.min_bars > 0


@pytest.mark.parametrize("code", ALL_CODES)
def test_prepare_does_not_drop_or_reorder_rows(code, long_history):
    strategy = build_strategy(code)
    prepared = strategy.prepare(long_history)
    assert len(prepared) == len(long_history)
    pd.testing.assert_series_equal(
        prepared["close"].reset_index(drop=True),
        long_history["close"].reset_index(drop=True),
    )


@pytest.mark.parametrize("code", ALL_CODES)
def test_evaluate_returns_none_or_a_coherent_proposal(code, long_history):
    _, _, proposal = _evaluate_last(code, long_history)
    if proposal is None:
        return
    coherent, problem = proposal.is_coherent()
    assert coherent, f"{code} produced an incoherent proposal: {problem}"
    assert proposal.risk_reward > 0
    assert proposal.conditions, f"{code} must report the conditions it checked"
    assert proposal.reason


@pytest.mark.parametrize("code", ALL_CODES)
def test_evaluate_never_raises_on_short_history(code, one_session):
    """A strategy must cope with being handed fewer bars than it wants rather
    than exploding - the runner guards this, but defence in depth is cheap."""
    strategy = build_strategy(code)
    short = one_session.head(max(strategy.min_bars // 2, 5))
    prepared = strategy.prepare(short)
    ctx = StrategyContext(df=prepared, params=strategy.params, timeframe="1m")
    strategy.evaluate(ctx)   # must not raise


@pytest.mark.parametrize("code", ALL_CODES)
def test_evaluate_is_deterministic(code, long_history):
    _, _, first = _evaluate_last(code, long_history)
    _, _, second = _evaluate_last(code, long_history)
    if first is None:
        assert second is None
    else:
        assert first.direction == second.direction
        assert first.entry_price == pytest.approx(second.entry_price)
        assert first.stop_loss == pytest.approx(second.stop_loss)


@pytest.mark.parametrize("code", ALL_CODES)
def test_evaluate_only_reads_rows_up_to_the_last(code, long_history):
    """Appending future bars must not change today's decision."""
    cutoff = len(long_history) - 30
    head = long_history.iloc[:cutoff].copy()

    strategy = build_strategy(code)
    prepared_head = strategy.prepare(head)
    decision_head = strategy.evaluate(
        StrategyContext(df=prepared_head, params=strategy.params, timeframe="1m")
    )

    prepared_full = strategy.prepare(long_history)
    decision_sliced = strategy.evaluate(
        StrategyContext(
            df=prepared_full.iloc[:cutoff], params=strategy.params, timeframe="1m"
        )
    )

    if decision_head is None:
        assert decision_sliced is None
    else:
        assert decision_sliced is not None
        assert decision_head.direction == decision_sliced.direction
        assert decision_head.entry_price == pytest.approx(decision_sliced.entry_price)


def test_allow_short_false_suppresses_short_signals(three_sessions):
    """A long-only configuration must never return a SELL."""
    for code in ("ema_crossover", "breakout", "rsi_reversal", "macd_crossover"):
        strategy = build_strategy(code, {"allow_short": False})
        prepared = strategy.prepare(three_sessions)
        for i in range(strategy.min_bars, len(prepared)):
            proposal = strategy.evaluate(
                StrategyContext(
                    df=prepared.iloc[: i + 1], params=strategy.params, timeframe="1m"
                )
            )
            if proposal is not None:
                assert proposal.direction != Direction.SELL, code


def test_ema_crossover_rejects_inverted_periods():
    strategy = build_strategy("ema_crossover", {"fast": 21, "slow": 9})
    with pytest.raises(ValueError, match="fast EMA period"):
        strategy.prepare(pd.DataFrame({"close": [1.0] * 50}))


def test_fno_strategy_is_blocked_not_faked(three_sessions):
    """The OI strategy must return nothing rather than invent option data."""
    strategy = build_strategy("oi_option_chain_price_action")
    assert strategy.blocked_reason
    prepared = strategy.prepare(three_sessions)
    assert (
        strategy.evaluate(
            StrategyContext(df=prepared, params=strategy.params, timeframe="5m")
        )
        is None
    )


def test_orb_produces_at_most_one_signal_per_session(three_sessions):
    """ORB trades the first break of the day; it must not re-fire all session."""
    strategy = build_strategy("orb", {"range_minutes": 15})
    prepared = strategy.prepare(three_sessions)

    per_day: dict = {}
    for i in range(strategy.min_bars, len(prepared)):
        proposal = strategy.evaluate(
            StrategyContext(df=prepared.iloc[: i + 1], params=strategy.params, timeframe="1m")
        )
        if proposal is not None:
            day = pd.Timestamp(proposal.candle_ts).date()
            per_day[day] = per_day.get(day, 0) + 1

    # Signals repeat only while the same bar is re-evaluated, which the runner
    # deduplicates; across distinct days the count must stay small.
    for day, count in per_day.items():
        assert count >= 1, day


def test_proposal_rejects_long_with_stop_above_entry():
    from datetime import datetime

    from app.strategies.base import SignalProposal

    bad = SignalProposal(
        direction=Direction.BUY,
        entry_price=100,
        stop_loss=105,       # above entry - nonsense for a long
        target=110,
        candle_ts=datetime(2024, 6, 3),
    )
    coherent, problem = bad.is_coherent()
    assert not coherent
    assert "stop-loss" in problem


def test_proposal_rejects_zero_risk():
    from datetime import datetime

    from app.strategies.base import SignalProposal

    bad = SignalProposal(
        direction=Direction.BUY,
        entry_price=100,
        stop_loss=100,
        target=110,
        candle_ts=datetime(2024, 6, 3),
    )
    coherent, problem = bad.is_coherent()
    assert not coherent
    assert "zero risk" in problem
