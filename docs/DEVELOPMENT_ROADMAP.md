# Development Roadmap

| Phase | Scope | State |
|---|---|---|
| 0 | Audit and architecture | **Done** |
| 1 | Foundation: auth, RBAC, schema, layout | **Done** |
| 2 | Market data: instruments, import, quality | **Done** (import not yet run on the real file) |
| 3 | Strategy engine: indicators, strategies, signals | **Done** |
| 4 | Paper trading: execution, positions, risk | **Done** |
| 5 | Backtesting: engine, metrics, comparison | **Done** (walk-forward and optimisation pending) |
| 6 | AI research | **Built, blocked on API key** |
| 7 | Professional UI | **Done** |
| 8 | VPS deployment | **Deferred at your request** |
| 9 | F&O module | **Not started, by design** |

---

## Phase 0 — Audit and architecture ✅

Repository was empty but for a one-line `README.md`. Environment audited:
PostgreSQL 16 and Redis present, Python 3.9 upgraded to 3.12, Node 20 and
Docker available. Architecture, schema, roadmap and risk register written
before any code.

## Phase 1 — Foundation ✅

FastAPI app with structured logging and secret redaction; typed exceptions;
environment-only configuration; 56-table schema with partitioned candles;
Alembic; JWT auth with refresh rotation and lockout; RBAC with 39 permissions;
append-only audit log; React shell with nested sidebar.

## Phase 2 — Market data ✅ (one caveat)

Instrument master, symbol mapping, corporate-action and holiday tables; candle
service with session-anchored resampling; resumable streaming SQLite importer;
schema inspection; data-quality reporting including thin-session detection;
`data_availability` for backtest gating.

**Caveat:** the importer has not met the real 180 GB file. Expect to extend
`COLUMN_ALIASES` once its schema is known.

**Not done:** live WebSocket feed (blocked on credentials), instrument sync
from broker, corporate-action adjustment job.

## Phase 3 — Strategy engine ✅

19 indicators, all causality-tested. 20 strategies across 4 categories, each
reporting its conditions. Registry deriving seed data from the classes.
Combination engine with AND/OR/weighted/minimum-confirmation, mandatory legs
and direction agreement. Signal engine with freshness guard, coherence check
and per-candle deduplication.

## Phase 4 — Paper trading ✅

Position sizing, ten risk limits, daily state persisted, kill switch, breach
recording. Simulated fills with adverse slippage, stop/target monitoring, gap
handling, trailing stops, partial exits, session square-off, full charge
breakdown. Verified end-to-end including that module deactivation does not
abandon positions.

## Phase 5 — Backtesting ✅ (partial)

Bar-by-bar engine sharing fill logic with the paper engine; next-bar-open
entries; 25+ metrics; in-sample/out-of-sample split with overfitting
heuristics; per-instrument and per-strategy breakdowns; coverage reporting.

**Not done:** walk-forward testing, parameter optimisation, sensitivity
analysis. The schema supports all three.

## Phase 6 — AI research ⚠️ blocked

Client, versioned prompts, full usage and cost recording, budget enforcement,
output validation, UI. Needs `ANTHROPIC_API_KEY`. Read-only MCP not
implemented.

## Phase 7 — Professional UI ✅

29 screens, dark terminal theme, permission-aware navigation, reusable
`DataTable` with CSV export, candlestick charts with volume and markers,
loading/empty/error states throughout, paper-trading labelling on every screen
showing money, Indian number formatting.

**Possible improvements:** route-level lazy loading, column customisation,
chart indicator overlays, mobile layout refinement.

## Phase 8 — VPS deployment ⏸ deferred

Deferred at your request so local development could be completed first. Covers
Docker images for API, worker, scheduler and market-data service; Nginx with
HTTPS; process supervision; health checks; centralised logs; resource and disk
monitoring; `pg_dump` backups with **verified restores**; recovery procedures;
24/7 runtime validation. Plan in `DEPLOYMENT.md`.

**Prerequisite:** move imports and backtests out of `BackgroundTasks` into
Celery workers. Running a multi-hour import inside an API worker is acceptable
for one developer on a laptop and wrong on a server.

## Phase 9 — F&O module ⏳ by design

Options for NIFTY, BANK NIFTY and SENSEX; CE/PE buying for intraday first.

Already in place: `expiry`, `strike`, `option_type` and `underlying_id` columns
on `instruments`; an independent `FNO` module switch; the registered (and
signal-free) `oi_option_chain_price_action` strategy; a `module` field
throughout signals and positions.

Still needed: options data feed, option-chain storage, OI and change-in-OI,
PCR, Greeks, IV, strike selection (ATM/ITM/OTM), premium tracking, expiry
management, options-specific risk (premium decay, not percentage stops),
options backtesting.

**Equity assumptions must not leak into options calculations.** A percentage
stop on a premium behaves nothing like one on a cash price. The module gets its
own engine.

---

## Immediate next steps

1. Import the real historical database (`DATA_IMPORT_GUIDE.md`).
2. Generate quality reports; establish which instruments are actually usable.
3. Backtest a few strategies on real data and read the results honestly.
4. Move imports and backtests to Celery.
5. Obtain Kite credentials; sync instruments; build the live feed.
6. Then Phase 8.
