# Handover — session of 23 Nov 2026

Everything decided, found and changed in this session, in one place, so the
work can be picked up on another machine.

---

## 1. What this project is

An AI-assisted **paper-trading** platform for Indian equity markets: FastAPI
backend, PostgreSQL, React terminal UI. It backtests and paper-trades
strategies against historical candle data and applies real Indian transaction
costs.

**It cannot place a real order.** `backend/app/core/safety.py` raises at every
order-placement boundary, and the `orders` and `positions` tables carry a
database `CHECK` constraint allowing only `execution_mode = 'PAPER'`. That is
deliberate and is not a setting.

---

## 2. State of the build

| | |
|---|---|
| Backend | 107 Python files (89 under `app/`), 56 tables, 81 API paths, 20 strategies, 19 indicators |
| Frontend | 29 screens, dark terminal theme |
| Tests | **245 backend, 18 frontend — all passing** |
| Lint | clean |
| Deployment | **deliberately not done** — deferred by the user |
| Git | commit `c91f09f`, pushed to `github.com/prajwalbankar17/prajwal_trad` |

Running locally on the Mac right now: API on `:8000`, UI on `:5173`,
PostgreSQL 16 on port **5435**, Redis on 6379.

---

## 3. The database is empty, on purpose

It previously held synthetic demo data. All of it was removed this session:

- 112,500 `MOCK` candles and their `data_availability` rows
- 292 derived records — backtest trades and results, paper orders, positions,
  exits, signals, risk states
- 5 demo instruments (`DEMOTECH`, `DEMOBANK`, …)
- The portfolio was reset: `realised_pnl` 7,994.01 → **0.00**, capital back to
  the ₹10,00,000 starting value

Kept: users, roles, 39 permissions, 20 strategies, sectors, exchanges, and the
append-only `audit_logs`.

**There is now no market data of any kind in the database.** Nothing real and
nothing fake. The next data loaded will be the real historical data.

---

## 4. What we learned about the historical data

The project was specified as importing a **180 GB SQLite file**, and a SQLite
importer was built for it (`backend/app/marketdata/sqlite_importer.py`).

That turned out to be wrong. The data on Google Drive
(`My Drive / Indian Market Data / pgsql`) is a **PostgreSQL 17.11 data
directory** — `data/` and `log/` folders, ~185 GB. Not a SQLite file.

**Consequence: the SQLite importer is the wrong tool and will not be used.** A
PostgreSQL-to-PostgreSQL path is needed instead, and it has not been written
yet, because it must be written against the real schema rather than a guess.

### Why it cannot simply be copied to the Mac

| Problem | Detail |
|---|---|
| **Disk** | 185 GB needed; the Mac has **72 GB free** and no external disk |
| **Version** | The cluster is PG **17**; the Mac has PG **16** only. 16 cannot read a 17 data directory |
| **Platform** | A PostgreSQL data directory only runs on the OS and architecture that created it. This one is very likely Windows or Linux x86-64; the Mac is ARM64 |

A data directory is also not something you can run from Google Drive. Starting
a PostgreSQL server *writes* to its data directory, and a Drive mount provides
no real `fsync` or file locking — that corrupts clusters.

### Schema gaps found

Their schema (`candles`, `instruments`) does not match the project schema
(`intraday_candles`, `instruments`):

- `open_interest` exists in their candles; the project table **has no such
  column**. A migration will be needed. Dropping it silently would gut the F&O
  data.
- `lot_size` is absent from their instruments. Equity can default to 1, but for
  F&O a wrong lot size makes **position sizing wrong**. It will not be guessed.
- `instrument_id` types differ (theirs unknown, project uses `uuid`), so a
  mapping is required.
- `timeframe` labels are unknown — one description said `minute`/`daily`,
  another `1m`/`5m`/`15m`/`1d`. They cannot both be right.

Those descriptions came from an AI summary of the Drive folder and have **not
been verified against the database**. They are treated as hints only.

---

## 5. What to do on the Windows machine

Full step-by-step with every command: **`tools/source-export/README.md`**.

In short:

1. Check free space — about **200 GB** is needed
2. Install **PostgreSQL 17** for Windows
3. Download `Indian Market Data/pgsql` from Drive to a path with no spaces
4. Delete a stale `postmaster.pid` if present
5. Set `pg_hba.conf` to `trust` (the cluster's own password is unknown)
6. Start the server on port **5433** with `pg_ctl`
7. Run **`01_inspect.sql`** — finishes in seconds, reads only catalog metadata
8. Run **`03_export.sql`** — writes `instruments.csv` and `daily_candles.csv`

Then send back **`inspect_out.txt`**. That file is what the real importer gets
written from.

### The decision that is still open

The Windows laptop may have room for all 185 GB. If it does, there are two
options:

| | Where data lives | Where the platform runs | Trade-off |
|---|---|---|---|
| **A. Windows = data only** | Windows | Mac | Platform already built, tested and running on the Mac. Only a few GB move across. |
| **B. Everything on Windows** | Windows | Windows | No data transfer at all, but the platform has to be set up again there |

Option B needs Python 3.12, Node 20+, PostgreSQL 17, and **Redis** — which is
the awkward one on Windows (WSL2, Memurai or Docker Desktop). The virtualenv
and `node_modules` must be rebuilt; they are macOS-specific and are not in git.

---

## 6. A real bug this session found

Purging the demo data emptied tables that two tests had been quietly relying
on, which exposed that **both tests guarding the paper-only rule were passing
without testing it**:

- The `orders` test called `pytest.skip()` on an empty table — it reported
  green while asserting nothing at all.
- The `positions` test built an `INSERT` missing eleven `NOT NULL` columns, so
  it failed with `NotNullViolation` instead of reaching the `CHECK`. It would
  have passed with the paper-only constraint **deleted**.

Both now create their own instrument, assert on the constraint **by name**, and
are paired with a positive control proving the identical statement succeeds
with `execution_mode = 'PAPER'`. Test count went 243 → 245.

This is worth knowing because it is the single rule the whole platform rests
on, and for the life of the build it was unverified.

---

## 7. Still blocked, and on what

| Feature | Blocked by |
|---|---|
| Live market data | Broker credentials. `/market-data/status` reports `feed_connected: false` — no fake feed |
| Zerodha / Claude integration | Credentials. Both raise `FeatureBlockedError` naming the missing variable |
| F&O | Phase 9. Schema and module switch exist; showing equity candles as OI would be dishonest |
| Celery workers | Imports and backtests still run in `BackgroundTasks` — fine on a laptop, wrong for a server |
| Deployment | Deferred by the user. Plans exist in `docs/DEPLOYMENT.md` and `docs/VPS_SETUP.md`; nothing implemented |

---

## 8. The end-to-end test that is waiting on data

Once real candles are loaded:

1. Select stocks **dynamically** from real data — no hardcoded list
2. Split ₹1,00,000 across 5 of them
3. Signals → risk validation → paper orders → monitored exits
4. Real Indian charges: brokerage cap, STT on the correct leg, exchange
   transaction, SEBI, stamp duty, GST, IPFT
5. Report the net result, profit or loss

Nothing in that path is mocked, and a losing result will be reported as a
losing result.

---

## 9. Not committed yet

At the time of writing, these are uncommitted on `main`:

```
M  PROJECT_STATUS.md
M  README.md
M  backend/tests/integration/test_engines_db.py
M  docs/CHANGELOG.md
M  docs/TESTING.md
?? tools/
```

`tools/source-export/` holds the scripts the Windows machine needs, so it has
to be pushed before cloning there — otherwise the clone arrives without them.
