# VPS Setup

See **[DEPLOYMENT.md](DEPLOYMENT.md)** — the topology, sizing guidance and the
full Phase 8 checklist live there, so there is one source of truth rather than
two that drift.

**Status: not implemented.** Deployment was deferred so local development could
be completed first.

## Before you start

1. **Move long jobs to Celery.** Imports and backtests currently run in
   FastAPI `BackgroundTasks`. Acceptable on a laptop, wrong on a server.
2. **Measure disk.** Import a few symbols, check
   `pg_total_relation_size('intraday_candles')`, extrapolate, then size the
   plan. Do not buy first.
3. **Verify `/api/v1/safety`** after every deployment. It must still report
   `live_order_placement_possible: false`.
