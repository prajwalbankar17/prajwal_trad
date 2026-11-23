# Backtesting Guide

The engine is built to tell you when a strategy does **not** work. Most of its
design exists to stop a backtest flattering itself.

## Bias controls

| Bias | Control |
|---|---|
| Look-ahead in indicators | Every indicator is causal; `test_indicator_is_causal` truncates the series and asserts no past value changes. |
| Look-ahead in strategies | The strategy sees `df.iloc[:i+1]` and nothing beyond. Asserted for all 20 strategies. |
| Look-ahead in levels | PDH/PDL/CPR/pivots use strictly prior sessions. Opening-range levels are NaN while the range is forming. Swing points are confirmed `lookback` bars late. |
| Fill-price optimism | Entries fill on the **next bar's open**, never the signal bar's close. |
| Slippage optimism | Slippage always works against the trader, on entry and exit. |
| Ambiguous intrabar order | When one candle contains both stop and target, the **stop is assumed first**. |
| Gap optimism | A candle opening beyond the stop fills at the open, not the stop. |
| Survivorship bias | Partially mitigated: `instruments` carries `listed_on`/`delisted_on`, and coverage is reported. If your source only contains currently-listed names, that bias remains — this is a data problem, not an engine problem. |
| Curve fitting | In-sample/out-of-sample split with explicit overfitting heuristics. |

## Running one

**UI:** Backtesting → Run Backtest. Pick configurations, instruments, dates,
timeframe, capital, risk per trade, slippage and an out-of-sample percentage.

**API:**

```bash
curl -X POST localhost:8000/api/v1/backtests \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{
        "name": "EMA 9/21, 15m, FY25",
        "mode": "ADVANCED",
        "strategy_config_ids": ["..."],
        "instrument_ids": ["..."],
        "timeframe": "15m",
        "start_date": "2024-04-01",
        "end_date": "2025-03-31",
        "initial_capital": 1000000,
        "risk_per_trade_pct": 1.0,
        "include_charges": true,
        "slippage_pct": 0.05,
        "out_of_sample_pct": 30
      }'
```

## Reading the results

### Look at these first, in this order

1. **Trade count.** Under 30 trades, nothing below it means anything. The
   engine says so in `notes`.
2. **Data coverage.** `data_coverage.skipped` lists instruments with
   insufficient history. A "universe-wide" result over 40 of 3,000 names is not
   a universe-wide result.
3. **Net profit vs gross.** The gap is your cost drag. If costs consume most of
   the gross edge, the strategy does not survive contact with a broker.
4. **Out-of-sample window.** If it collapses, the parameters are fitted.
5. **Max drawdown.** A curve you could not have sat through is not tradable.
6. *Then* win rate.

### Why not win rate first

A 90% win rate with a 10:1 loss-to-win size ratio loses money. `expectancy`
(average expected rupees per trade) and `profit_factor` (gross profit ÷ gross
loss) answer the question win rate only gestures at.

### Metrics reported

Total/winning/losing trades, win rate, gross profit, gross loss, total charges,
net profit, profit factor, expectancy, average profit, average loss, average
R:R, max drawdown (absolute and %), Sharpe, Sortino, max consecutive wins and
losses, average MAE and MFE, monthly performance, equity curve.

Broken down by OVERALL, per instrument, per strategy, and per window.

### Deliberate nulls

- **Profit factor is null** when there were no losing trades — it is undefined,
  not infinite.
- **Sharpe and Sortino are null** below 20 trading days with activity. A Sharpe
  computed from four trades is a decorative number.

Each null comes with a note explaining why.

## Overfitting detection

With `out_of_sample_pct`, trades are split chronologically and compared:

- Win rate falling more than 15 points out of sample
- Profit factor retaining under 60% of its in-sample value
- Profitable in sample but not out of sample
- Too few trades in either window to compare

Two or more flags sets `likely_overfit: true`. These are **heuristics that
prompt a closer look**, not a verdict.

> A note on how this check was built: it originally used truthiness
> (`if in_sample.win_rate and out_of_sample.win_rate`), which silently skipped
> the case where the out-of-sample win rate was exactly **0%** — the strongest
> possible warning. A test caught it. It now checks trade counts and
> `is not None` explicitly.

## Interpreting a losing result

A strategy that loses money on a backtest has told you something useful and
cheap. Before discarding it, check whether the result is real:

- Does it lose *because of* costs? Compare gross and net.
- Does it lose on all instruments, or is one name dominating? Check the
  per-instrument breakdown.
- Is the exit the problem rather than the entry? Compare average MFE with
  average profit — large MFE and small profit means winners are being cut.
- Is it losing in one regime only? Check `monthly_performance`.

## What is not implemented

- **Walk-forward testing** — the schema supports windows; the rolling
  re-optimisation loop is not written.
- **Parameter optimisation / grid search** — the job model carries a
  `validation` blob for it; the sweep is not implemented.
- **Sensitivity analysis** — run neighbouring parameter values manually for
  now; a result that collapses when a period changes by one is fitted.

## Honest expectations

A "70% research accuracy" target is an aspiration, not a result. Most published
retail strategies do not survive realistic costs. The platform is built so that
finding this out is quick and unambiguous — which is worth considerably more
than a backtest that flatters.
