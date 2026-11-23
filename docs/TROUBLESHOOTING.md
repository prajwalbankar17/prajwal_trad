# Troubleshooting

## Setup

### `psql: fe_sendauth: no password supplied`

More than one PostgreSQL is installed and you are reaching the wrong one.

```bash
ls -la /tmp/.s.PGSQL.*
```

Each socket is a separate instance. Find the Homebrew one (usually owned by
your user) and use its port:

```bash
psql -p 5435 -d postgres -c "SELECT version();"
```

Set `POSTGRES_PORT` in `.env` to match. Or use Docker instead
(`docker compose up -d`, port 5433).

### `Cannot connect to the Docker daemon`

Docker Desktop is not running. Start it, or use a local PostgreSQL and Redis
and point `.env` at them.

### `python3.12: command not found`

```bash
brew install python@3.12
```

Then recreate the venv:

```bash
rm -rf backend/.venv && make setup
```

### `Could not connect to Redis`

```bash
brew services start redis
```

```bash
redis-cli ping
```

Should answer `PONG`.

### `email-validator is not installed`

Reinstall dependencies; `pydantic[email]` is in `requirements.txt`.

```bash
cd backend && .venv/bin/pip install -r requirements.txt
```

## Migrations

### `relation "intraday_candles" does not exist`

Migrations have not run.

```bash
make migrate
```

### Autogenerate wants to drop the candle partitions

It should not — `alembic/env.py` filters names starting with
`intraday_candles_`. If you see it, the filter has been removed; restore
`include_object`.

### `no partition of relation "intraday_candles" found for row`

A timestamp fell outside every yearly partition, and the DEFAULT partition is
missing. Check:

```sql
SELECT count(*) FROM intraday_candles_default;
```

Add partitions for the years you need in a new migration.

## Authentication

### `401` on every request after a while

The access token expired and refresh failed. Sign in again. If it recurs
immediately, `SECRET_KEY` changed — every existing token is now invalid, which
is correct behaviour.

### Account locked

Five failed attempts locks the account for 15 minutes. Wait, or clear it:

```sql
UPDATE users SET failed_login_attempts = 0, locked_until = NULL
WHERE username = 'admin';
```

### Lost the admin password

```bash
cd backend && .venv/bin/python -m scripts.seed
```

will *not* reset an existing user. Either delete the user and re-seed, or set a
new hash directly.

## Data and backtests

### A backtest returns zero trades

In order of likelihood:

1. **No data.** Check `GET /market-data/availability` — is the instrument
   `is_usable`?
2. **Not enough bars.** Each strategy declares `min_bars`; the window must
   exceed it at the chosen timeframe.
3. **Risk/reward filter.** `min_risk_reward` on the configuration rejects
   proposals below it.
4. **The strategy genuinely did not trigger.** Check
   `GET /strategy-configs/{id}/executions` for the condition-by-condition log.

The job's `warnings` array usually says which.

### Candles are missing at 15m but present at 1m

Expected. Higher intraday timeframes are **resampled from 1m on read**, and
incomplete trailing buckets are dropped. If 1m has gaps, higher timeframes have
proportionally fewer candles.

### `could not determine data type of parameter`

PostgreSQL cannot infer the type of a bare NULL placeholder. Cast it:

```sql
WHERE (CAST(:end AS timestamptz) IS NULL OR ts <= CAST(:end AS timestamptz))
```

### Import seems stuck

Check progress — it may be working through a large symbol:

```bash
curl localhost:8000/api/v1/market-data/imports/{job_id} -H "Authorization: Bearer $TOKEN"
```

`rows_read` increasing means it is alive. If the status is `FAILED`, read
`last_error` and resume.

## Frontend

### Blank page, console shows a module error

```bash
cd frontend && rm -rf node_modules/.vite && npm run dev
```

### `/api` requests 404

The backend is not running, or is on a different port. The Vite proxy targets
`http://127.0.0.1:8000`; change it in `vite.config.js` if yours differs.

### Charts do not render

`lightweight-charts` needs a container with a measurable width. If the panel is
inside a `display: none` parent at mount, it renders at zero width — mount it
only when visible.

## Tests

### Integration tests all skip

Expected without PostgreSQL. They skip rather than fail so `pytest` always
runs. Start the database and re-run.

### `ruff` fails on line length

Limit is 100. `ruff check --fix` handles imports and simple cases; long strings
need manual wrapping.
