# Project Overview

## What this is

A research and **paper-trading** platform for Indian equities. It stores
historical candles, runs configurable strategies against them, generates
signals, validates them against risk limits, simulates execution with realistic
costs, and reports performance honestly — including when the answer is that a
strategy does not work.

## What it is not

- Not a live trading system. Live execution is disabled and not implemented.
- Not a source of investment advice.
- Not a collection of profitable strategies. All 20 are research candidates.

## Who it is for

A single developer-trader doing serious research, with room to add users later
(RBAC is in place from the start).

## Core capabilities today

| Capability | Detail |
|---|---|
| Historical data | Resumable streaming import from a large SQLite source; 1m storage; resampling on read |
| Data quality | Coverage, gaps, thin sessions, invalid OHLC, usability gating |
| Instruments | ~3,000 equity universe supported; search, sector and liquidity filters; watchlists |
| Strategies | 19 indicators, 20 strategies, parameterised and versioned |
| Combinations | 2–5 legs with AND/OR/weighted/minimum-confirmation and mandatory legs |
| Signals | Full condition breakdown, freshness guard, deduplication, state history |
| Risk | Ten limits, position sizing, daily state, kill switch, breach log |
| Paper trading | Adverse slippage, real charges, gap handling, trailing stops, square-off |
| Backtesting | Next-bar fills, 25+ metrics, in/out-of-sample split, overfitting heuristics |
| AI research | Claude explains signals and backtests — read-only, budgeted, recorded |
| UI | 29 screens, dark terminal theme, CSV export, candlestick charts |

## Guiding principle

Every design decision in this codebase answers the same question: *would this
make a backtest look better than reality?* Where the answer was yes, the
conservative option was taken — adverse slippage, stop-before-target, next-bar
entries, nulls instead of flattering statistics, and blocked features instead
of simulated ones.

A platform that tells you a strategy fails is worth more than one that tells
you it succeeds when it does not.

## Scope boundaries

**Phase 1 is equity margin/MIS intraday.** F&O is architected for (schema
columns, independent module switch, a registered placeholder strategy) and
deliberately not implemented — options need option-chain, OI, IV and Greeks
data this build has no feed for, and equity assumptions must not leak into
options maths.

**Deployment is deferred.** Everything runs locally today.

See `DEVELOPMENT_ROADMAP.md` for phases and `PROJECT_STATUS.md` for exactly
what is done, pending and blocked.
