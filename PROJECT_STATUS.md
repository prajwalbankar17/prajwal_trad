# Project Status

**Last updated:** 2026-11-23
**Phase:** 1 (Equity foundation) — built and running locally
**Execution mode:** PAPER ONLY. Live order execution is disabled and not implemented.

---

## Completed

### Phase 0 — Audit and architecture
- Audited the repository: empty except `README.md`, one commit. Nothing was overwritten.
- Audited the environment: PostgreSQL 16 (Homebrew, port 5435) and Redis present;
  Python was 3.9 so 3.12 was installed; Node 20 and Docker present.
- Architecture, database design, roadmap and risk register written to `docs/`.

### Foundation
- FastAPI app, structured logging with secret redaction, typed exception
  hierarchy with stable error codes.
- Settings from environment only (`pydantic-settings`); no credential in any
  tracked file.
- PostgreSQL schema: **56 tables** across instruments, market data, strategies,
  signals, trading, risk, backtesting, portfolio, AI and system domains.
- `intraday_candles` is RANGE-partitioned by `ts` with yearly partitions
  2018–2031 plus a DEFAULT partition. Partition routing verified.
- Alembic configured; two migrations applied cleanly.
- JWT auth with refresh-token rotation and session revocation; account lockout
  after 5 failed attempts.
- RBAC: 39 permissions, 5 seeded roles. Route guards check permission codes,
  never role names.
- Append-only audit log.

### Market data
- Candle service with session-anchored resampling (09:15 IST anchor).
- Resumable SQLite importer: streamed cursors, bounded memory, batch inserts
  with `ON CONFLICT DO NOTHING`, per-symbol resume cursor, failure recording.
- Schema inspection endpoint that reads the source layout instead of assuming it.
- Data-quality reporting: coverage, missing sessions, thin sessions, invalid
  OHLC, duplicates, completeness percentage.
- `data_availability` table so a backtest knows which instruments it can trust.

### Strategy engine
- **19 indicators** across trend, momentum, volatility, volume and levels.
- **20 strategies** in 4 categories, each with a parameter schema, its own
  condition reporting, and configurable stop/target/risk-reward.
- Registry mapping database codes to implementations; seed data is derived
  from the classes, so documentation cannot drift from behaviour.
- Combination engine with AND / OR / weighted / minimum-confirmation logic,
  mandatory legs and direction-agreement checking.

### Signals, risk, paper trading
- Signal engine: history sufficiency, data-freshness guard, coherence check,
  per-candle deduplication, full state history.
- Risk engine: position sizing, 10 limit checks, daily state persisted to
  PostgreSQL, kill switch, breach recording.
- Paper trading engine: simulated fills with adverse slippage, stop/target
  monitoring, gap handling, trailing stops, partial exits, session square-off,
  full charge breakdown.

### Backtesting
- Bar-by-bar engine sharing fill logic with the paper engine.
- Entries fill on the next bar's open; exits are checked before new entries.
- Metrics: 25+ including expectancy, profit factor, MAE/MFE, Sharpe/Sortino
  (null when the sample is too small), monthly breakdown, equity curve.
- In-sample/out-of-sample split with overfitting heuristics.
- Data-coverage reporting so skipped instruments are visible.

### Frontend
- React 18 + Vite + Tailwind, professional dark terminal theme.
- 29 screens, nested sidebar navigation, permission-aware.
- Reusable `DataTable` (search, sort, pagination, CSV export) and
  `CandleChart` (candles, volume, crosshair, zoom, markers, price lines).
- Paper-trading banner on every screen that shows money.
- Indian number formatting (lakh/crore), tabular figures, colour-blind-safe
  profit/loss palette.

### Verified end-to-end
- Login → JWT → permissions → dashboard, via HTTP.
- Signal generation → risk validation → paper entry → monitoring → exit, with
  correct gross/charges/net and portfolio reconciliation.
- Backtest over 5 instruments × 267 trades completing in 2 seconds.
- Module deactivation blocks new entries while monitoring continues.
- Database `CHECK` constraint rejects `execution_mode='LIVE'`.

### Testing
- **243 backend tests**, all passing: indicators (incl. causality for every
  indicator and every strategy), charges, execution, strategies, metrics,
  risk sizing, security, safety, aggregation, calendar, API, database.
- **18 frontend tests**, all passing: formatting, `DataTable` behaviour,
  Dashboard rendering including loading, error and halted states.

---

## In progress

Nothing is mid-change. The tree is in a consistent, working state.

---

## Pending (next, in order)

1. **Import the real historical database.** Inspect the schema, confirm the
   column mapping, run the import, generate quality reports. See
   `docs/DATA_IMPORT_GUIDE.md`.
2. **Instrument master sync** from the broker (needs credentials) to replace
   auto-created instruments with real tokens, lot sizes and ISINs.
3. **Background workers.** Imports and backtests currently run in FastAPI
   `BackgroundTasks`, which is fine for one developer and wrong for a VPS.
   Celery is already a dependency; the worker module is not written.
4. **Live market data service** — broker WebSocket, tick processing, live
   candle construction, heartbeats, reconnection. Blocked on credentials.
5. **Notification delivery.** The data model, preferences and in-app feed exist;
   the Telegram and email senders are not written.
6. **Portfolio snapshots job** for the equity curve on the Portfolio page.
7. **Walk-forward testing and parameter optimisation** (the schema supports
   both; the engine implements in-sample/out-of-sample only).
8. **Phase 8 deployment** — deliberately deferred at your request.

---

## Blocked

| Item | Blocked by | Behaviour today |
|---|---|---|
| Zerodha market data, instruments, margins, holdings | `KITE_API_KEY`, `KITE_API_SECRET`, `KITE_ACCESS_TOKEN` | `FeatureBlockedError` naming the missing variables |
| Live WebSocket feed | Same | Not implemented; `/market-data/status` reports `feed_connected: false` |
| Claude AI research | `ANTHROPIC_API_KEY`, `AI_ENABLED=true` | `FeatureBlockedError`; UI shows a blocked-feature panel |
| Telegram / email alerts | Bot token / SMTP settings | Channels reported as "not configured" |
| F&O module | No options data feed; Phase 9 | Registered, documented, returns no signals |
| Real historical import | The 180 GB SQLite file is not on this machine | Importer written and tested; never run against it |

Nothing blocked is faked. Each returns a specific error naming its dependency.

---

## Known issues and accepted limitations

1. **Imports and backtests run in-process.** A long import will tie up an API
   worker. Move to Celery before the VPS.
2. **Demo data is synthetic.** `scripts/load_demo_data.py` writes `source='MOCK'`
   rows and flags instruments as demo. Purge with `--purge` before real use.
3. **Holiday list is a seed.** `app/core/market_calendar.py` ships 2025–2026
   NSE holidays. Populate `market_holidays` from the exchange calendar; the
   code already prefers the database when rows exist.
4. **Corporate actions are modelled but not applied.** The table and
   `adjusted_close` column exist; the adjustment job is not written. Backtests
   across a split will currently see a price discontinuity.
5. **Charge rates need verification** against your broker's current contract
   note. They are parameterised (`ChargesConfig`), not hardcoded.
6. **Sharpe/Sortino are null below 20 trading days** with activity — by design,
   rather than printing an impressive number from four trades.
7. **`assumed_leverage` defaults to 1.0.** Broker leverage is never assumed;
   when margin data becomes available the lower of the two will apply.
8. **Frontend bundle** is ~940 KB before splitting, ~570 KB of it charting
   libraries. Code-split into four chunks; could be lazy-loaded per route.

---

## Technical decisions

| Decision | Reasoning |
|---|---|
| One `intraday_candles` table partitioned by year, not per-timeframe tables | ~280M rows/year at 1m. Partition pruning plus `(instrument_id, timeframe, ts)` is what keeps a backtest query bounded. Higher timeframes resample on read. |
| `daily_candles` left unpartitioned | A few million rows, and it is scanned *across* instruments, which time partitioning would not help. |
| Ticks are not stored in PostgreSQL by default | Volume is enormous and the value is low. Latest tick lives in Redis; `live_ticks` exists for opt-in debugging windows. |
| bcrypt used directly, not via passlib | passlib has been unmaintained since 2020 and emits a spurious version error against bcrypt ≥ 4.1. |
| Stop assumed before target within one candle | Without tick data it is unknowable. The conservative choice understates results. |
| Entry fills on the next bar's open | Filling at the signal bar's close assumes you could trade at a price you only knew once the bar ended. |
| Permissions as rows, not code | New roles need no deployment. |
| `execution_mode` CHECK constraint in the database | Defence in depth: even a code bug cannot record a live order. |
| Secrets never in the database | `broker_connections` stores `has_credentials`, never a token. |

---

## Test results

```
backend   243 passed in 4.70s
frontend   18 passed in 1.44s
lint       ruff: all checks passed
build      vite: built in 3.48s
```

---

## Next session starts here

The fastest useful next step is the historical import:

```bash
curl -X POST localhost:8000/api/v1/market-data/imports/inspect \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"source_path":"/path/to/equity_1min.sqlite"}'
```

Confirm the reported column mapping, then create the job. It resumes safely if
interrupted. Full procedure in `docs/DATA_IMPORT_GUIDE.md`.
