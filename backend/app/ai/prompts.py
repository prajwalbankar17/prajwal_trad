"""Versioned prompts.

Every prompt has a name and a version, both recorded with the output. When a
prompt changes, old analyses remain explainable: you can see exactly what the
model was asked.
"""

from __future__ import annotations

from dataclasses import dataclass

RESEARCH_DISCLAIMER = (
    "You are a research assistant for a trading-research platform. You analyse "
    "data that has already been computed by the platform. You do not place "
    "orders, you do not have access to any trading system, and your output is "
    "research commentary, never an instruction to trade. If the data provided "
    "is insufficient to support a conclusion, say so plainly instead of "
    "speculating. Never claim a strategy is profitable on the basis of a small "
    "sample."
)


@dataclass(frozen=True)
class Prompt:
    name: str
    version: int
    task: str
    system: str
    template: str

    def render(self, context: dict) -> str:
        return self.template.format(**context)


EXPLAIN_SIGNAL = Prompt(
    name="explain_signal",
    version=1,
    task="signal_explanation",
    system=RESEARCH_DISCLAIMER,
    template=(
        "Explain this trading signal in plain English for a trader reviewing it.\n\n"
        "Instrument: {symbol}\n"
        "Strategy: {strategy}\n"
        "Direction: {direction}\n"
        "Entry: {entry}  Stop-loss: {stop_loss}  Target: {target}  "
        "Risk/reward: {risk_reward}\n"
        "Timeframe: {timeframe}\n"
        "Conditions evaluated:\n{conditions}\n"
        "Indicator values:\n{indicators}\n\n"
        "Cover: what the strategy saw, which conditions carried the decision, "
        "and the two or three ways this setup most often fails. Do not invent "
        "data that is not listed above."
    ),
)

ANALYSE_BACKTEST = Prompt(
    name="analyse_backtest",
    version=1,
    task="backtest_analysis",
    system=RESEARCH_DISCLAIMER,
    template=(
        "Review these backtest results and give an honest assessment.\n\n"
        "Strategy: {strategy}\nPeriod: {start} to {end}\n"
        "Instruments tested: {instrument_count} (skipped for lack of data: {skipped})\n\n"
        "Metrics:\n{metrics}\n\n"
        "In-sample vs out-of-sample:\n{windows}\n\n"
        "Address: whether the sample is large enough to conclude anything, "
        "signs of overfitting, how much of the gross edge the costs consumed, "
        "and what would need to be true for this to work live. If the result is "
        "poor, say so directly."
    ),
)

ANALYSE_FAILED_TRADES = Prompt(
    name="analyse_failed_trades",
    version=1,
    task="failed_trade_analysis",
    system=RESEARCH_DISCLAIMER,
    template=(
        "These are losing trades from one strategy.\n\n"
        "Strategy: {strategy}\nLosing trades: {count}\n{trades}\n\n"
        "Look for patterns: time of day, market condition, exit reason, how "
        "often the stop was hit before any favourable movement (MAE vs MFE). "
        "Suggest hypotheses to test. Be explicit that these are hypotheses "
        "requiring their own backtest, not fixes."
    ),
)

MARKET_SUMMARY = Prompt(
    name="market_summary",
    version=1,
    task="market_summary",
    system=RESEARCH_DISCLAIMER,
    template=(
        "Summarise the market session from the platform's own data.\n\n"
        "Date: {date}\nMarket status: {market_status}\n"
        "Instruments monitored: {instrument_count}\n"
        "Signals generated: {signal_count} ({validated} validated, "
        "{rejected} rejected by risk)\n"
        "Paper trades: {trade_count}, net P&L after costs: {net_pnl}\n"
        "Top movers:\n{movers}\n\n"
        "Keep it factual and short. Do not speculate about news or events you "
        "have not been given."
    ),
)

STRATEGY_COMPARISON = Prompt(
    name="strategy_comparison",
    version=1,
    task="strategy_comparison",
    system=RESEARCH_DISCLAIMER,
    template=(
        "Compare these strategies over the same period.\n\n{table}\n\n"
        "Say which has the stronger evidence behind it and why, where the "
        "comparison is unfair (different trade counts, different exposure), and "
        "what a sensible next test would be. Do not pick a winner if the "
        "samples do not support one."
    ),
)

ALL_PROMPTS = [
    EXPLAIN_SIGNAL,
    ANALYSE_BACKTEST,
    ANALYSE_FAILED_TRADES,
    MARKET_SUMMARY,
    STRATEGY_COMPARISON,
]

BY_NAME = {p.name: p for p in ALL_PROMPTS}
