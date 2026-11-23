# API Documentation

Base path `/api/v1`. Interactive docs at `/docs` (Swagger) and `/redoc`.
**95 routes across 15 routers.**

## Conventions

**Auth** — `Authorization: Bearer <access_token>` on everything except
`/health`, `/safety`, `/` and `/auth/login`.

**Errors** — always the same shape, so the frontend branches on `code`, not on
English:

```json
{ "code": "risk_limit_breached", "message": "...", "details": {} }
```

| Code | HTTP |
|---|---|
| `not_found` | 404 |
| `validation_error` | 422 |
| `conflict` | 409 |
| `authentication_failed` | 401 |
| `permission_denied` | 403 |
| `rate_limited` | 429 |
| `risk_limit_breached` | 409 |
| `stale_market_data` | 409 |
| `live_execution_forbidden` | 403 |
| `broker_error` | 502 |
| `feature_blocked` | 503 |
| `data_quality_error` | 422 |

**Pagination** — `?page=1&page_size=50`, response
`{items, total, page, page_size}`.

---

## System

| Method | Path | Permission | Notes |
|---|---|---|---|
| GET | `/health` | — | Dependency health, market status, safety block |
| GET | `/safety` | — | Execution-safety status; always paper |
| GET | `/settings` | `system:monitor` | Sensitive values redacted |
| GET | `/audit-logs` | `audit:read` | Filter by action, entity, severity |

## Authentication

| Method | Path | Notes |
|---|---|---|
| POST | `/auth/login` | Returns access + refresh |
| POST | `/auth/refresh` | Rotates the refresh token |
| POST | `/auth/logout` | Revokes sessions |
| GET | `/auth/me` | Current user with roles |
| GET | `/auth/me/permissions` | Flat list of permission codes |
| POST | `/auth/change-password` | Ends other sessions |

## Dashboard

`GET /dashboard` — capital, P&L, trades, strategies, signals, risk, modules,
data coverage and recent trades. Always carries `is_paper_trading: true` and a
disclaimer string.

## Instruments and watchlists

| Method | Path | Permission |
|---|---|---|
| GET | `/instruments` | `instrument:read` |
| GET | `/instruments/{id}` | `instrument:read` |
| GET | `/sectors` | `instrument:read` |
| GET/POST | `/watchlists` | `watchlist:read` / `watchlist:write` |
| POST/DELETE | `/watchlists/{id}/items[/{item_id}]` | `watchlist:write` |
| DELETE | `/watchlists/{id}` | `watchlist:write` |

Instrument filters: `q`, `exchange`, `segment`, `sector`, `is_active`,
`min_price`, `max_price`, `min_volume`.

## Market data

| Method | Path | Permission | Notes |
|---|---|---|---|
| GET | `/market-data/status` | — | Says plainly when no live feed is connected |
| GET | `/market-data/candles` | `marketdata:read` | Resamples above 1m |
| GET | `/market-data/availability` | `marketdata:read` | |
| POST | `/market-data/imports/inspect` | `marketdata:import` | Read-only schema inspection |
| POST | `/market-data/imports` | `marketdata:import` | |
| POST | `/market-data/imports/{id}/resume` | `marketdata:import` | Resumes from the cursor |
| GET | `/market-data/imports[/{id}]` | `marketdata:read` | |
| GET | `/market-data/quality/summary` | `marketdata:quality` | |
| GET | `/market-data/quality/{instrument_id}` | `marketdata:quality` | Gaps and thin sessions |
| GET | `/market-data/quality-reports` | `marketdata:quality` | |

## Strategies

| Method | Path | Permission |
|---|---|---|
| GET | `/strategies/catalogue` | `strategy:read` |
| GET | `/strategies` | `strategy:read` |
| POST | `/strategies/{id}/activate?active=` | `strategy:activate` |
| GET/POST | `/strategy-configs` | `strategy:read` / `strategy:write` |
| PATCH/DELETE | `/strategy-configs/{id}` | `strategy:write` |
| GET | `/strategy-configs/{id}/executions` | `strategy:read` |
| GET/POST | `/strategy-combinations` | `combination:read` / `combination:write` |
| GET | `/trading-modules` | `strategy:read` |
| POST | `/trading-modules/{module}?active=` | `module:activate` |

Activating a strategy with a `blocked_reason` returns 422 rather than
pretending.

## Signals

| Method | Path | Permission |
|---|---|---|
| GET | `/signals` | `signal:read` |
| GET | `/signals/{id}` | `signal:read` |
| POST | `/signals/generate` | `signal:manage` |
| POST | `/signals/{id}/cancel` | `signal:manage` |
| POST | `/signals/expire-stale` | `signal:manage` |

`GET /signals/{id}` returns the full condition-by-condition breakdown, the risk
validation with every check, the indicator snapshot and the state history.

## Paper trading

| Method | Path | Permission |
|---|---|---|
| GET | `/trading/positions` | `trade:read` |
| GET | `/trading/positions/{id}` | `trade:read` |
| POST | `/trading/positions/enter` | `trade:manage` |
| POST | `/trading/positions/{id}/exit` | `trade:manage` |
| POST | `/trading/positions/monitor` | `trade:manage` |
| GET | `/trading/history` | `trade:read` |

**There is no live order endpoint, in this router or any other.**

## Risk

| Method | Path | Permission |
|---|---|---|
| GET | `/risk/profiles` | `risk:read` |
| PATCH | `/risk/profiles/{id}` | `risk:write` |
| GET | `/risk/utilisation` | `risk:read` |
| GET | `/risk/breaches` | `risk:read` |
| GET | `/risk/daily-state` | `risk:read` |
| POST | `/risk/kill-switch?active=` | `risk:killswitch` |

## Backtesting

| Method | Path | Permission |
|---|---|---|
| POST | `/backtests` | `backtest:run` |
| GET | `/backtests` | `backtest:read` |
| GET | `/backtests/{id}` | `backtest:read` |
| GET | `/backtests/{id}/trades` | `backtest:read` |
| GET | `/backtests/compare/?job_ids=a,b` | `backtest:read` |
| DELETE | `/backtests/{id}` | `backtest:delete` |

`compare` returns caveats when trade counts differ enough that the comparison
is not apples to apples.

## Portfolio, AI, broker, notifications, users

| Method | Path | Permission |
|---|---|---|
| GET | `/portfolio` | `portfolio:read` |
| GET | `/portfolio/{id}/holdings` | `portfolio:read` |
| GET | `/portfolio/{id}/snapshots` | `portfolio:read` |
| GET | `/ai/status` | — |
| GET | `/ai/prompts` | `ai:read` |
| POST | `/ai/explain-signal/{id}` | `ai:run` |
| POST | `/ai/analyse-backtest/{id}` | `ai:run` |
| GET | `/ai/analyses`, `/ai/usage` | `ai:read` |
| GET | `/broker/status` | — |
| GET | `/broker/connections` | `broker:read` |
| POST | `/broker/connect` | `broker:connect` |
| GET | `/broker/margins` | `broker:read` |
| GET | `/notifications` | `notification:read` |
| POST | `/notifications/{id}/read`, `/read-all` | `notification:read` |
| GET/PUT | `/notifications/preferences` | `notification:read` / `notification:write` |
| GET/POST | `/users` | `user:read` / `user:write` |
| PATCH/DELETE | `/users/{id}` | `user:write` |
| GET | `/roles`, `/permissions` | `role:read` |
| PUT | `/roles/{id}/permissions` | `role:write` |

`DELETE /users/{id}` **deactivates** rather than deletes: a user's audit trail
must survive.
