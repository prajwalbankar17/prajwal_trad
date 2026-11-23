"""Performance metrics.

Every figure is computed from **net** P&L (after charges and slippage) unless
its name says gross. Reporting gross as if it were net is the most flattering
lie a backtest can tell.

Sharpe and Sortino are returned as `None` when there are too few observations
to mean anything, rather than as an impressive-looking number computed from
four trades.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

MIN_OBSERVATIONS_FOR_RATIOS = 20
TRADING_DAYS_PER_YEAR = 252


@dataclass
class Trade:
    entry_time: object
    exit_time: object
    net_pnl: float
    gross_pnl: float = 0.0
    charges: float = 0.0
    mae: float = 0.0
    mfe: float = 0.0
    risk: float = 0.0
    instrument: str = ""
    strategy: str = ""
    direction: str = "BUY"
    exit_reason: str = ""


@dataclass
class Metrics:
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    total_charges: float = 0.0
    net_profit: float = 0.0
    profit_factor: float | None = None
    expectancy: float | None = None
    average_profit: float = 0.0
    average_loss: float = 0.0
    average_rr: float | None = None
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    avg_mae: float | None = None
    avg_mfe: float | None = None
    equity_curve: list = field(default_factory=list)
    monthly_performance: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        data = self.__dict__.copy()
        for key, value in data.items():
            if isinstance(value, float):
                data[key] = round(value, 4)
        return data


def _stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


def compute(
    trades: list[Trade], *, initial_capital: float, risk_free_rate: float = 0.0
) -> Metrics:
    m = Metrics()
    m.total_trades = len(trades)
    if not trades:
        m.notes.append("No trades were taken; metrics are not meaningful.")
        return m

    ordered = sorted(trades, key=lambda t: (t.exit_time or t.entry_time))

    wins = [t for t in ordered if t.net_pnl > 0]
    losses = [t for t in ordered if t.net_pnl < 0]

    m.winning_trades = len(wins)
    m.losing_trades = len(losses)
    m.win_rate = round(len(wins) / len(ordered) * 100, 4)

    m.gross_profit = round(sum(t.gross_pnl for t in ordered if t.gross_pnl > 0), 2)
    m.gross_loss = round(sum(t.gross_pnl for t in ordered if t.gross_pnl < 0), 2)
    m.total_charges = round(sum(t.charges for t in ordered), 2)
    m.net_profit = round(sum(t.net_pnl for t in ordered), 2)

    profit_sum = sum(t.net_pnl for t in wins)
    loss_sum = abs(sum(t.net_pnl for t in losses))
    m.profit_factor = round(profit_sum / loss_sum, 4) if loss_sum > 0 else None
    if loss_sum == 0 and profit_sum > 0:
        m.notes.append("No losing trades in this sample - profit factor is undefined.")

    m.average_profit = round(profit_sum / len(wins), 2) if wins else 0.0
    m.average_loss = round(-loss_sum / len(losses), 2) if losses else 0.0
    win_rate_fraction = len(wins) / len(ordered)
    m.expectancy = round(
        win_rate_fraction * m.average_profit + (1 - win_rate_fraction) * m.average_loss, 4
    )

    rr_values = [t.net_pnl / t.risk for t in ordered if t.risk > 0]
    m.average_rr = round(sum(rr_values) / len(rr_values), 4) if rr_values else None

    mae_values = [t.mae for t in ordered if t.mae]
    mfe_values = [t.mfe for t in ordered if t.mfe]
    m.avg_mae = round(sum(mae_values) / len(mae_values), 2) if mae_values else None
    m.avg_mfe = round(sum(mfe_values) / len(mfe_values), 2) if mfe_values else None

    # Equity curve and drawdown.
    equity = initial_capital
    peak = initial_capital
    max_dd = 0.0
    max_dd_pct = 0.0
    curve = [{"t": None, "equity": round(equity, 2), "drawdown_pct": 0.0}]

    for trade in ordered:
        equity += trade.net_pnl
        peak = max(peak, equity)
        drawdown = peak - equity
        drawdown_pct = drawdown / peak * 100 if peak else 0.0
        max_dd = max(max_dd, drawdown)
        max_dd_pct = max(max_dd_pct, drawdown_pct)
        curve.append(
            {
                "t": str(trade.exit_time) if trade.exit_time else None,
                "equity": round(equity, 2),
                "drawdown_pct": round(drawdown_pct, 4),
            }
        )

    m.max_drawdown = round(max_dd, 2)
    m.max_drawdown_pct = round(max_dd_pct, 4)
    m.equity_curve = curve

    # Consecutive streaks.
    streak = best_win = best_loss = 0
    last_sign = 0
    for trade in ordered:
        sign = 1 if trade.net_pnl > 0 else (-1 if trade.net_pnl < 0 else 0)
        streak = streak + 1 if sign == last_sign and sign != 0 else (1 if sign != 0 else 0)
        last_sign = sign
        if sign > 0:
            best_win = max(best_win, streak)
        elif sign < 0:
            best_loss = max(best_loss, streak)
    m.max_consecutive_wins = best_win
    m.max_consecutive_losses = best_loss

    # Daily returns drive the risk ratios, not per-trade P&L.
    daily: dict[date, float] = {}
    for trade in ordered:
        key = _as_date(trade.exit_time or trade.entry_time)
        if key is not None:
            daily[key] = daily.get(key, 0.0) + trade.net_pnl

    returns = [pnl / initial_capital for _, pnl in sorted(daily.items())]
    if len(returns) >= MIN_OBSERVATIONS_FOR_RATIOS:
        mean_return = sum(returns) / len(returns)
        excess = mean_return - risk_free_rate / TRADING_DAYS_PER_YEAR
        sd = _stdev(returns)
        if sd > 0:
            m.sharpe_ratio = round(excess / sd * math.sqrt(TRADING_DAYS_PER_YEAR), 4)
        downside = [r for r in returns if r < 0]
        dd = _stdev(downside) if len(downside) >= 2 else 0.0
        if dd > 0:
            m.sortino_ratio = round(excess / dd * math.sqrt(TRADING_DAYS_PER_YEAR), 4)
    else:
        m.notes.append(
            f"Only {len(returns)} trading days with activity; Sharpe and Sortino "
            f"need at least {MIN_OBSERVATIONS_FOR_RATIOS} to be meaningful and "
            "are reported as null."
        )

    # Monthly breakdown.
    monthly: dict[str, dict] = {}
    for trade in ordered:
        key = _as_date(trade.exit_time or trade.entry_time)
        if key is None:
            continue
        month = f"{key.year:04d}-{key.month:02d}"
        bucket = monthly.setdefault(month, {"net_pnl": 0.0, "trades": 0, "wins": 0})
        bucket["net_pnl"] = round(bucket["net_pnl"] + trade.net_pnl, 2)
        bucket["trades"] += 1
        if trade.net_pnl > 0:
            bucket["wins"] += 1
    for bucket in monthly.values():
        bucket["win_rate"] = (
            round(bucket["wins"] / bucket["trades"] * 100, 2) if bucket["trades"] else 0.0
        )
    m.monthly_performance = monthly

    if m.total_trades < 30:
        m.notes.append(
            f"{m.total_trades} trades is a small sample - treat these figures as "
            "indicative, not as evidence of an edge."
        )
    return m


def _as_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not hasattr(value, "hour"):
        return value
    if hasattr(value, "date"):
        return value.date()
    return None


def group_by(trades: list[Trade], key: str) -> dict[str, list[Trade]]:
    buckets: dict[str, list[Trade]] = {}
    for trade in trades:
        buckets.setdefault(getattr(trade, key, "") or "unknown", []).append(trade)
    return buckets


def overfitting_flags(in_sample: Metrics, out_of_sample: Metrics) -> dict:
    """Compare in-sample and out-of-sample results.

    These are heuristics that prompt a closer look, not a verdict. A strategy
    that halves out of sample is usually curve-fitted; one that improves is
    usually lucky.
    """
    flags: list[str] = []

    if in_sample.total_trades < 30 or out_of_sample.total_trades < 10:
        flags.append("Too few trades in one of the windows to compare reliably.")

    # Note the explicit `is not None` / trade-count checks: a 0% out-of-sample
    # win rate or a 0.0 profit factor is the STRONGEST warning there is, and a
    # truthiness check would silently skip exactly those cases.
    if in_sample.total_trades and out_of_sample.total_trades:
        drop = in_sample.win_rate - out_of_sample.win_rate
        if drop > 15:
            flags.append(
                f"Win rate fell {drop:.1f} points out of sample "
                f"({in_sample.win_rate:.1f}% -> {out_of_sample.win_rate:.1f}%)."
            )

    if in_sample.profit_factor is not None and out_of_sample.profit_factor is not None:
        if in_sample.profit_factor > 0:
            ratio = out_of_sample.profit_factor / in_sample.profit_factor
            if ratio < 0.6:
                flags.append(
                    f"Profit factor retained only {ratio * 100:.0f}% of its in-sample "
                    "value - a classic curve-fitting signature."
                )
    elif in_sample.profit_factor is not None and out_of_sample.profit_factor is None:
        # No losses out of sample is not evidence of an edge on a short window.
        flags.append(
            "Out-of-sample window has no losing trades - too short to judge."
        )

    if in_sample.net_profit > 0 >= out_of_sample.net_profit:
        flags.append("Profitable in sample but not out of sample.")

    return {
        "flags": flags,
        "likely_overfit": len(flags) >= 2,
        "in_sample": {
            "trades": in_sample.total_trades,
            "win_rate": in_sample.win_rate,
            "profit_factor": in_sample.profit_factor,
            "net_profit": in_sample.net_profit,
        },
        "out_of_sample": {
            "trades": out_of_sample.total_trades,
            "win_rate": out_of_sample.win_rate,
            "profit_factor": out_of_sample.profit_factor,
            "net_profit": out_of_sample.net_profit,
        },
    }
