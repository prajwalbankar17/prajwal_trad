# Requirements

Traceability from the specification to the implementation.

Legend: ✅ done · ⚠️ built but blocked on an external dependency · ⏸ deferred ·
⏳ future phase · ❌ not done

## Platform

| Requirement | State | Where |
|---|---|---|
| Historical market data management | ✅ | `app/marketdata`, `app/services/data_import.py` |
| Real-time market data processing | ❌ | Needs broker credentials; `/market-data/status` says so plainly |
| Multiple configurable strategies | ✅ 20 | `app/strategies/library` |
| Strategy combination and confirmation | ✅ | `app/engines/combination.py` |
| Automated signal generation | ✅ | `app/engines/signal_engine.py` |
| Automated paper trading | ✅ | `app/engines/paper_trading.py` |
| Portfolio and position management | ✅ | `app/models/portfolio.py`, `trading.py` |
| Advanced backtesting | ✅ (walk-forward pending) | `app/engines/backtest.py` |
| Strategy performance analytics | ✅ | `app/engines/metrics.py` |
| AI market research | ⚠️ | `app/ai` — needs `ANTHROPIC_API_KEY` |
| Broker integration | ⚠️ | `app/brokers/zerodha.py` — needs Kite credentials |
| Risk management | ✅ | `app/engines/risk.py` |
| Notifications and alerts | ✅ in-app; ❌ Telegram/email senders | `app/api/v1/routers/notifications.py` |
| Trade history and audit logs | ✅ | `audit_logs`, `positions`, `signal_history` |
| Future F&O capability | ⏳ architected | Schema columns, module switch, roadmap Phase 9 |
| Cloud/VPS 24/7 execution | ⏸ | `docs/DEPLOYMENT.md` |

## Technology

| Required | Used |
|---|---|
| React, JavaScript primary | ✅ React 18, JavaScript (no TypeScript, per "do not unnecessarily complicate") |
| Professional charting | ✅ `lightweight-charts` + `recharts` |
| Scalable state management | ✅ TanStack Query (server state) + Zustand (auth) |
| Python, FastAPI, Pydantic | ✅ |
| SQLAlchemy, Alembic | ✅ 2.0 style |
| PostgreSQL, Redis | ✅ |
| WebSockets | ❌ not implemented (no feed to carry) |
| Background task queue | ⚠️ Celery installed; workers not written |
| Anthropic Claude API | ⚠️ blocked on key |
| Read-only MCP | ❌ not implemented |
| Windows/macOS development | ✅ no platform-specific code; developed on macOS |
| Docker and Docker Compose | ✅ local infrastructure only |
| Nginx, HTTPS, backups, monitoring | ⏸ Phase 8 |

## Strategies

All 20 implemented. See `STRATEGY_DOCUMENTATION.md` for exact rules.
`oi_option_chain_price_action` is registered and documented but returns no
signals — it needs options data that does not exist here.

## Timeframes

1m, 3m, 5m, 10m, 15m, 30m, 1h ✅ (1m stored, rest resampled);
daily, weekly, monthly ✅ (`daily_candles`).

## Database modules

All ten logical groups from the specification exist as physical tables — 56 in
total. Physical design deviates from the literal list where query patterns
justified it (one partitioned `intraday_candles` rather than separate
`historical_candles`/`intraday_candles`), which the specification explicitly
permits. See `DATABASE_SCHEMA.md`.

## Acceptance criteria

| # | Criterion | State |
|---|---|---|
| 1 | Users can securely log in | ✅ verified over HTTP |
| 2 | Instruments can be managed | ✅ |
| 3 | Historical data can be imported | ✅ built; not yet run on the real file |
| 4 | Data quality can be inspected | ✅ |
| 5 | Live data can be connected and validated | ❌ blocked on credentials |
| 6 | Strategies can be configured | ✅ |
| 7 | Strategies independently enabled/disabled | ✅ |
| 8 | Signals can be generated | ✅ verified |
| 9 | Signal conditions can be explained | ✅ condition-by-condition |
| 10 | Paper trades created automatically | ✅ verified |
| 11 | Positions can be monitored | ✅ verified |
| 12 | Stop-loss and target processed | ✅ verified, incl. gaps |
| 13 | Transaction costs included | ✅ full Indian charge model |
| 14 | Backtests can execute | ✅ 267 trades in 2s |
| 15 | Backtest metrics inspectable | ✅ 25+ metrics |
| 16 | Strategies can be compared | ✅ with fairness caveats |
| 17 | Risk limits prevent new trades | ✅ verified |
| 18 | Trade history persisted | ✅ |
| 19 | AI can analyse stored research data | ⚠️ blocked on key |
| 20 | Notifications work | ✅ in-app; ❌ external channels |
| 21 | System restarts without losing state | ✅ daily risk state and positions in PostgreSQL |
| 22 | VPS deployment runs independently | ⏸ deferred |
| 23 | Backups and recovery tested | ⏸ deferred |
| 24 | Real orders remain disabled | ✅ five independent mechanisms |

## Explicitly honoured constraints

- No fake market data in production features — demo data is labelled `MOCK`
  and flagged in the UI.
- Mock, historical, delayed and live data are distinguished by
  `DataSourceKind` and surfaced on every signal.
- No credential is hardcoded, logged or stored in the database.
- No success is reported that was not achieved — blocked features raise named
  errors.
- Nothing was deleted or overwritten; the repository was empty at the start.
