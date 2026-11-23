# Architecture

## Principles

1. **Business logic is independent of delivery.** Engines and strategies know
   nothing about FastAPI, and the API layer contains no trading rules.
2. **Strategy proposes, risk disposes.** `app/strategies` never imports
   `app/engines/risk`, and risk never imports a strategy.
3. **One fill model.** The paper engine and the backtester both call
   `app/engines/execution.py`, so results are comparable by construction.
4. **Blocked beats faked.** A missing credential raises `FeatureBlockedError`
   naming the dependency. Nothing returns a plausible-looking fake.
5. **Live execution is structurally impossible**, not merely switched off.

## Layers

```
┌──────────────────────────────────────────────────────────────┐
│ React UI (Vite, Tailwind, TanStack Query, Zustand)           │
│   /api proxy in dev; no hardcoded host in the bundle          │
└───────────────────────────┬──────────────────────────────────┘
                            │ JSON over HTTP, Bearer JWT
┌───────────────────────────▼──────────────────────────────────┐
│ API layer — app/api/v1                                        │
│   15 routers · dependency-injected session · permission guards │
│   No trading logic lives here                                  │
└───────────────────────────┬──────────────────────────────────┘
┌───────────────────────────▼──────────────────────────────────┐
│ Engines — app/engines                                         │
│   risk · signal · combination · paper_trading · backtest       │
│   execution (shared fill model) · metrics                      │
└──────┬──────────────────────────────┬────────────────────────┘
       │                              │
┌──────▼────────────────┐   ┌─────────▼──────────────────────┐
│ Strategies            │   │ Services                        │
│   indicators (pure)   │   │   auth · audit · candles         │
│   20 strategies       │   │   data_import · data_quality     │
│   registry            │   └─────────┬──────────────────────┘
└───────────────────────┘             │
┌─────────────────────────────────────▼────────────────────────┐
│ Data — app/models, app/db                                     │
│   SQLAlchemy 2.0 · Alembic · PostgreSQL 16 · Redis            │
└──────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────┐
│ Adapters — app/brokers, app/ai, app/marketdata                │
│   MarketDataAdapter (read) · ExecutionAdapter (paper only)     │
│   Claude client (read-only, no tools)                          │
└──────────────────────────────────────────────────────────────┘
```

## Request flow: generating a signal

1. `POST /signals/generate` → permission guard `signal:manage`.
2. `SignalEngine.evaluate(config, instrument)`:
   - loads `min_bars + 10` candles through the candle service;
   - refuses if there is not enough history;
   - refuses if the newest candle is older than the freshness threshold —
     stale data never becomes a live signal;
   - calls `strategy.prepare()` once (indicators), then `strategy.evaluate()`
     on the final row only;
   - checks the proposal is coherent (a long whose stop is above entry is a
     bug, not a trade);
   - computes a dedupe key of (config, instrument, timeframe, candle) and
     drops a duplicate.
3. Persists a `TradingSignal` in `GENERATED` with every condition recorded.
4. `RiskEngine.validate_entry()` runs 10 checks and sizes the position.
   Pass → `VALIDATED`. Fail → `REJECTED`, with a `RiskLimitBreach` row.
5. Every transition is appended to `signal_history`.

A signal is never an order. Only `PaperTradingEngine.enter_from_signal()`
turns a `VALIDATED` signal into a `Position`, and only when the module is
active.

## Module activation semantics

`trading_module_states` has one row per module (`EQUITY`, `FNO`).

| | Module active | Module inactive |
|---|---|---|
| New signals | yes | **no** |
| New entries | yes | **no** |
| Stop-loss monitoring | yes | **yes** |
| Target monitoring | yes | **yes** |
| Exit processing | yes | **yes** |
| Square-off | yes | **yes** |

`monitor_open_positions` is forced to `True` whenever the flag is written.
`PaperTradingEngine.monitor_positions()` does not consult the module state at
all — that is the structural guarantee, not a convention.

## Data layer

**`intraday_candles`** — RANGE partitioned on `ts`, yearly partitions plus a
DEFAULT. PK `(ts, instrument_id, timeframe)`; index
`(instrument_id, timeframe, ts)`. At ~3,000 instruments × 375 minutes × 250
sessions this is ~280M rows per year at 1m alone, so partition pruning is not
an optimisation but a requirement.

**`daily_candles`** — not partitioned. Small, and scanned across instruments.

**Higher timeframes are not stored.** 1m is the source of truth; 3m–1h are
resampled on read, anchored to the 09:15 session open. This removes a whole
class of inconsistency between stored and derived candles.

**Redis** holds only ephemeral state: latest tick, in-progress candle, feed
heartbeat, kill switch, signal dedupe keys, import progress. Anything that must
survive a restart (daily risk state, positions, signals) is in PostgreSQL.

## Broker abstraction

`MarketDataAdapter` (read) and `ExecutionAdapter` (write) are separate
interfaces. `ZerodhaAdapter` implements only the read side — it has no
`place_order` method at all. `get_execution_adapter()` is hardcoded to return
`PaperExecutionAdapter`; it takes no argument. `LiveExecutionAdapter` exists
solely so the attachment point is explicit, and every one of its methods
raises.

Adding Kotak Neo means writing one class and adding one registry entry.

## AI boundary

The Claude client receives a dict of already-computed numbers and returns text.
It has no tools, no database handle, no shell and no order interface. Every
call records prompt name and version, model, input context, output, token
counts, estimated cost and latency — on failure as well as success. Spend is
checked against the monthly budget *before* the call.

Output passes through `validate_output()`, which flags overconfident language
and instruction-shaped text. The platform never acts on AI output; a human
reads it, labelled as research.

## Deployment (Phase 8, not implemented)

Planned: Docker images for API, worker, scheduler and market-data service
behind Nginx with HTTPS, PostgreSQL and Redis as managed or containerised
services, `pg_dump` backups with restore verification, health checks and
process supervision. See `DEPLOYMENT.md`.
