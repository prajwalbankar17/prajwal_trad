# Changelog

## [0.1.0] — 2026-11-23

Initial build. Phases 0–7 complete; Phase 8 deferred; Phase 9 by design.

### Added

**Foundation**
- FastAPI application with structured logging, secret redaction and a typed
  exception hierarchy with stable machine-readable codes.
- Environment-only configuration via `pydantic-settings`.
- PostgreSQL schema: 56 tables; `intraday_candles` RANGE-partitioned by year.
- Alembic migrations (initial schema + partitions).
- JWT auth with refresh-token rotation, session revocation and account lockout.
- RBAC: 39 permissions, 5 seeded roles, permission-code route guards.
- Append-only audit logging.

**Market data**
- Candle service with session-anchored resampling (09:15 IST).
- Resumable streaming SQLite importer with schema inspection, batch inserts,
  conflict-skip idempotency and failure recording.
- Data-quality reporting including thin-session detection.
- `data_availability` gating for backtests.

**Strategy engine**
- 19 indicators, all causality-tested.
- 20 strategies across price action, indicators, intraday and volume.
- Registry deriving database seed data from the classes.
- Combination engine: AND / OR / weighted / minimum-confirmation, mandatory
  legs, direction agreement.

**Trading**
- Signal engine with freshness guard, coherence check and deduplication.
- Risk engine: sizing plus ten limits, kill switch, daily state, breach log.
- Paper trading engine: adverse slippage, gap handling, trailing stops,
  partial exits, square-off, full charge breakdown.
- Backtesting engine with next-bar entries, 25+ metrics, in/out-of-sample
  split and overfitting heuristics.

**Integrations**
- Broker abstraction with paper and Zerodha adapters.
- Claude AI client with versioned prompts, budget enforcement and full usage
  recording.

**Frontend**
- React 18 + Vite + Tailwind dark trading terminal; 29 screens.
- Reusable `DataTable` (search, sort, pagination, CSV) and `CandleChart`.
- Indian number formatting, colour-blind-safe P&L palette.

**Testing and docs**
- 243 backend tests, 18 frontend tests.
- 18 documents.

### Safety

- Live order execution disabled through five independent mechanisms:
  unconditional guard, no live adapter, hardcoded factory, database CHECK
  constraints, and no API route.

### Fixed during development

- **Overfitting heuristics used truthiness**, so an out-of-sample win rate of
  exactly 0% — the strongest possible warning — was silently skipped. Now
  checks trade counts and `is not None` explicitly. Caught by a test.
- **passlib replaced with bcrypt directly**: passlib has been unmaintained
  since 2020 and emits a spurious version error against bcrypt ≥ 4.1.
- **Liquidity sweep had a malformed `allow_short` condition** that could gate
  the wrong branch; the long side is no longer affected by it.
- **SQL NULL parameters** needed explicit casts for PostgreSQL type inference.

### Known gaps

See `PROJECT_STATUS.md`. Principal ones: live market data, Celery workers, the
real historical import, corporate-action adjustment, walk-forward testing,
external notification channels, and deployment.
