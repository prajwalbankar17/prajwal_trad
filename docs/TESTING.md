# Testing

```
backend   245 passed
frontend   18 passed
```

## Running

```bash
make test
```

```bash
cd backend && .venv/bin/pytest tests/unit -q
```

```bash
cd frontend && npm test
```

Integration tests are marked `integration` and **skip automatically** when
PostgreSQL is unreachable, so `pytest` always runs.

## What is covered, and why

### `test_indicators.py` — 31 tests

Known-value checks (SMA of 1–5, RSI of a monotonic series is 100, RSI of a flat
series is 50, True Range uses the previous close), plus two invariants:

**Causality.** `test_indicator_is_causal` truncates the series and asserts no
past value changes, for EMA, RSI, ATR, MACD, Supertrend, ADX, Bollinger and
OBV. If an indicator peeks forward, every backtest result is meaningless.

**NaN, not zero.** Before enough history exists an indicator is NaN. Filling
with 0 would make an EMA look like a crossover on the first bar of every
backtest.

Also: VWAP resets at each session open; session VWAP differs from continuous
VWAP; relative volume excludes the current bar; previous-day levels do not
change when the *current* session's prices are tampered with; opening-range
levels are NaN while forming; swing points are confirmed late.

### `test_strategies.py` — 108 tests

Parametrised across all 20 strategies:

- `prepare()` does not drop or reorder rows
- `evaluate()` returns `None` or a **coherent** proposal (no long with a stop
  above entry, no zero risk)
- never raises on insufficient history
- is deterministic
- **only reads rows up to the last** — appending future bars must not change
  today's decision

Plus: `allow_short=False` never yields a SELL; `ema_crossover` rejects inverted
periods; the F&O strategy returns nothing rather than inventing option data.

### `test_charges.py` — 8 tests

STT on the sell leg only for intraday and both legs for delivery; brokerage
capped per order; net = gross − charges; short P&L inverted; a zero-rate config
produces zero charges.

### `test_execution.py` — 15 tests

Slippage always works against the trader on entry *and* exit; the stop takes
precedence when one candle contains both levels; gaps fill at the open; a
trailing stop only moves favourably; excursions are signed from the position's
viewpoint.

### `test_metrics.py` — 16 tests

Profit factor is `None` without losses rather than infinite; Sharpe is `None`
below 20 observations; drawdown is measured from the running peak; small
samples are flagged; overfitting heuristics fire on a genuine collapse and stay
quiet when results hold up.

> This file caught a real defect: the overfitting check used truthiness, so an
> out-of-sample win rate of exactly **0%** — the strongest possible warning —
> was silently skipped. It now checks trade counts and `is not None`.

### `test_risk_sizing.py` — 8 tests

Size is risk budget ÷ stop distance, then clamped; each constraint can bind and
the binding one is reported; zero stop distance returns zero rather than
infinity; lot size rounds down; leverage increases size but not risk.

### `test_safety.py` — 8 tests

The paper-only guarantee. `test_live_execution_raises_even_if_settings_are_flipped`
sets every permissive flag and asserts it still raises. The factory only ever
returns the paper adapter. Every `LiveExecutionAdapter` method raises. Secrets
are redacted in logs.

**If these fail, the build can place a real order.**

### `test_security.py` — 13 tests

Salted hashes; over-72-byte passwords rejected rather than truncated; weak
passwords rejected; token type enforced; tampered and expired tokens rejected;
unique `jti` per token.

### `test_aggregation.py` — 24 tests

Buckets anchored to 09:15 rather than the clock hour; partial buckets excluded
by default and flagged when requested; a 375-minute session gives 75×5m, 25×15m
and 12×30m; daily cannot be resampled from minutes; OHLC validation; calendar
boundaries at 09:15 and 15:30; database holidays override the seed list.

### Integration — 17 tests

API shape, 401 on protected routes, no account enumeration, the OpenAPI schema
contains **no order-placement route**, seeded roles and permissions, Viewer is
read-only, modules start inactive, the `execution_mode` CHECK constraint
rejects LIVE, candles are partitioned.

### Frontend — 18 tests

Indian currency grouping (10,00,000 not 1,000,000); zero P&L is neutral, not
green; `DataTable` search, sort, pagination, empty and loading states;
Dashboard renders headline metrics, always states figures are simulated, shows
module state, surfaces a trading halt, and renders an error state when the API
fails.

## Determinism

Fixtures build candles from a seeded `numpy` generator, so a failure is
reproducible. `tests/conftest.py` exposes `one_session`, `three_sessions` and
`trending_session`.

## What is not covered

- The live WebSocket feed — not implemented.
- Broker API round trips — blocked on credentials. A recorded-response suite
  should be added once they exist.
- Real AI calls — only the blocked path is tested.
- Browser end-to-end flows — component tests cover rendering; Playwright would
  be the next step.
- The real 180 GB import — the importer is unit-tested; the file is not here.

## Before committing

```bash
cd backend && .venv/bin/ruff check app tests scripts && .venv/bin/pytest -q
```

```bash
cd frontend && npm test && npm run build
```
