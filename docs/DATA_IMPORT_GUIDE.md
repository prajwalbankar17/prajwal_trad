# Data Import Guide

Importing a large historical SQLite candle database (~180 GB, 1-minute equity
candles from ~2022).

> **Status:** the importer is written and unit-tested. It has **not yet been
> run against the real file.** Expect to adjust `COLUMN_ALIASES` once you see
> the actual schema.

## Constraints that shaped the design

| Constraint | How it is handled |
|---|---|
| 180 GB cannot fit in RAM | Streamed cursors with bounded `arraysize`; memory stays flat whether the file is 2 GB or 400 GB. |
| An import takes hours | Progress is a `(symbol, last_ts)` cursor committed with each batch. A power cut costs one batch, not one week. |
| Re-running must not duplicate | `INSERT ... ON CONFLICT (ts, instrument_id, timeframe) DO NOTHING`. Duplicates are counted, not assumed away. |
| The schema is unknown | It is **inspected**, never assumed. Column names are matched against known aliases and the mapping is reported before a single row is written. |
| Bad rows exist | Validated and counted into `data_import_failures` with a sample. Never silently repaired, never dropped without a record. |

## Step 1 — Inspect before importing

```bash
curl -X POST localhost:8000/api/v1/market-data/imports/inspect \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"source_path":"/absolute/path/to/equity_1min.sqlite"}'
```

The file is opened **read-only**. Nothing is written. You get back:

- `layout` — `single_table` (a symbol column exists) or `table_per_symbol`
- `table_count` and a preview of table names
- `column_map` — what the importer would use for ts/open/high/low/close/volume
- `symbol_column`
- `row_estimate` for the probe table
- `sample_rows`
- `warnings`

The UI does this on **Market Data → Data Imports**, and the Start button stays
disabled until an inspection succeeds.

### If the mapping is wrong

Add the real column names to `COLUMN_ALIASES` in
`app/marketdata/sqlite_importer.py`:

```python
COLUMN_ALIASES = {
    "ts": ("ts", "timestamp", "date", "datetime", "your_column_here"),
    ...
}
```

Do not edit the query builder — aliases are the only place that should change.

## Step 2 — Start the import

```bash
curl -X POST localhost:8000/api/v1/market-data/imports \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
        "name": "Equity 1m history",
        "source_path": "/absolute/path/to/equity_1min.sqlite",
        "timeframe": "1m",
        "create_missing_instruments": true,
        "batch_size": 50000
      }'
```

`symbols` may be supplied to import a subset first — strongly recommended for
a trial run:

```json
{"symbols": ["RELIANCE", "TCS", "HDFCBANK"]}
```

## Step 3 — Watch, and resume if needed

`GET /market-data/imports/{job_id}` reports symbols completed, rows read,
inserted, skipped as duplicates and rejected, plus the resume cursor.

If it stops for any reason:

```bash
curl -X POST localhost:8000/api/v1/market-data/imports/{job_id}/resume \
  -H "Authorization: Bearer $TOKEN"
```

It continues from the stored cursor. Resuming a completed job is a no-op.

## Step 4 — Check what you actually got

```bash
curl "localhost:8000/api/v1/market-data/quality/{instrument_id}?timeframe=1m" \
  -H "Authorization: Bearer $TOKEN"
```

Returns records, first/last date, expected vs present sessions, missing session
dates, **thin sessions** (present but far short of 375 one-minute candles —
these look complete to a naive count and are a common source of silent gaps),
invalid OHLC rows, duplicates and a completeness percentage.

`GET /market-data/quality/summary` gives platform-wide totals, and
`GET /market-data/availability` lists every instrument/timeframe with an
`is_usable` flag (≥ 90% session coverage).

**Do not assume all 3,000 stocks have complete coverage.** The backtester
reports which instruments it skipped, and the availability table is what it
checks.

## Capacity planning

| | |
|---|---|
| Source file | ~180 GB |
| Available disk | ~500 GB |
| Expected growth | beyond 300 GB |

PostgreSQL will use **more** space than the SQLite source: row headers, the
primary-key index and the `(instrument_id, timeframe, ts)` index all cost. Plan
for roughly 1.3–1.6× the source size, so 230–290 GB for a 180 GB import.

Before importing the whole thing:

1. Import 3–5 symbols and measure the real ratio with
   `SELECT pg_size_pretty(pg_total_relation_size('intraday_candles'));`
2. Extrapolate, and confirm it fits with headroom for WAL and backups.
3. Only then run the full import.

If space is tight, options in order of preference: import a subset of the
universe; import a shorter history; drop the secondary index during the import
and rebuild afterwards (fastest, but the table is unqueryable until it finishes).

## Partition maintenance

`intraday_candles` has yearly partitions for 2018–2031 plus a DEFAULT. Rows
whose `ts` falls outside every range land in DEFAULT rather than failing the
import — check it after a large import:

```sql
SELECT count(*) FROM intraday_candles_default;
```

Anything in there indicates a timestamp-parsing problem worth investigating.

## Performance expectations

With `batch_size=50000` on local SSD, expect roughly 50,000–150,000 rows per
second depending on hardware. 180 GB is on the order of several hours. Run it
in a terminal that survives a disconnect (`tmux`, `screen`, or `nohup`), or
move it to a Celery worker first — see the pending items in `PROJECT_STATUS.md`.

## Incremental updates

Re-running an import against the same file imports only rows newer than what is
already stored, because the conflict clause skips existing ones. For a daily
top-up, create a new job with the same path; the duplicate count tells you how
much overlap there was.
