# Prajwal Trading Platform

An AI-assisted research and **paper-trading** platform for Indian equities:
historical data management, a configurable strategy engine, signal generation,
simulated execution with real transaction costs, backtesting with
overfitting checks, and a professional dark trading terminal.

> ### Paper trading only
> Live order execution is **disabled and not implemented** in this build.
> `assert_live_execution_allowed()` raises unconditionally, the only execution
> adapter is the simulator, and PostgreSQL enforces `CHECK (execution_mode =
> 'PAPER')` on `orders` and `positions`. No environment variable, API call, UI
> action or AI output can place a real order. See [docs/SECURITY.md](docs/SECURITY.md).

---

## Status

Phase 1 (equity) foundation is built and running locally. Current state,
including what is **not** done, is tracked in [PROJECT_STATUS.md](PROJECT_STATUS.md).

| Area | State |
|---|---|
| Backend API (FastAPI, 95 routes across 15 routers) | Working |
| PostgreSQL schema (56 tables, partitioned candles) | Working, migrated |
| Auth + RBAC (5 roles, 39 permissions) | Working |
| Indicator library (19 indicators) | Working, look-ahead tested |
| Strategy engine (20 strategies) | Working |
| Signal engine + risk engine | Working |
| Paper trading engine | Working, verified end-to-end |
| Backtesting + metrics + overfitting checks | Working |
| React frontend (29 routes) | Working |
| SQLite historical importer | Implemented; **not yet run against the real 180 GB file** |
| Zerodha Kite Connect | Implemented; **blocked on API credentials** |
| Claude AI research | Implemented; **blocked on `ANTHROPIC_API_KEY`** |
| Live market data WebSocket | **Not implemented** (needs broker credentials) |
| F&O module | **Not implemented** — Phase 9 by design |
| Background workers (`backend/app/workers/`) | **Empty placeholder** — Phase 8 |
| VPS deployment, Nginx, HTTPS, backups (`infra/`) | **Empty placeholder** — Phase 8 |

Tests: **243 backend**, **18 frontend**, all passing.

---

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | **3.12** | `make setup` calls `python3.12` explicitly |
| Node | 18+ (20 tested) | |
| PostgreSQL | 14+ (16 tested) | Or use the bundled Docker service |
| Redis | 7 | Or use the bundled Docker service |
| Docker | optional | Only needed if you don't run Postgres/Redis natively |

---

## Quick start (local)

**1. Clone and enter the project**

```bash
git clone <this repo> && cd prajwal_trad
```

**2. Create your environment file**

```bash
cp .env.example .env
```

**3. Generate a secret** and put it in `.env` as `SECRET_KEY`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

**4. Create the database** (adjust the port to your PostgreSQL instance):

```bash
psql -p 5432 -d postgres \
  -c "CREATE ROLE trading LOGIN PASSWORD 'trading' CREATEDB;" \
  -c "CREATE DATABASE prajwal_trading OWNER trading;"
```

**5. Install everything** (creates `backend/.venv`, installs pip + npm deps):

```bash
make setup
```

**6. Apply migrations and seed reference data:**

```bash
make migrate && make seed
```

**7. Load clearly-labelled synthetic candles** so the UI has something to show:

```bash
cd backend && .venv/bin/python -m scripts.load_demo_data --days 60
```

**8. Run the two servers in separate terminals:**

```bash
make backend     # terminal 1
```

```bash
make frontend    # terminal 2
```

| What | Where |
|---|---|
| UI | http://localhost:5173 |
| API docs (Swagger) | http://localhost:8000/docs |
| API docs (ReDoc) | http://localhost:8000/redoc |
| Safety status | http://localhost:8000/api/v1/safety |
| Health check | http://localhost:8000/api/v1/health |

The seeded admin password is written to
`backend/.seed_admin_credentials.txt` (gitignored, mode 600). Move it to a
password manager and delete the file.

### Don't have PostgreSQL or Redis locally?

```bash
make infra-up        # or: docker compose up -d
```

This starts PostgreSQL on **5433** and Redis on **6380** to avoid clashing with
local installs. Update `POSTGRES_PORT=5433` and `REDIS_PORT=6380` in `.env` to
match, then continue from step 6.

```bash
make infra-down      # stop them again (volumes are kept)
```

> `docker-compose.yml` is local development infrastructure only. Production
> deployment (Nginx, HTTPS, workers, backups) is Phase 8 and is intentionally
> not configured yet.

---

## Command reference

### Make targets

Run these from the **project root**.

| Command | What it does |
|---|---|
| `make help` | List the targets with their descriptions |
| `make setup` | Create `backend/.venv` (Python 3.12), install backend and frontend dependencies |
| `make migrate` | Apply Alembic migrations (`alembic upgrade head`) |
| `make revision m="..."` | Autogenerate a migration from model changes |
| `make seed` | Seed permissions, roles, admin user, strategies, risk profile |
| `make backend` | Run the API with reload on :8000 |
| `make frontend` | Run the UI on :5173 |
| `make test` | Run the backend test suite |
| `make lint` | Ruff over `app`, `tests`, `scripts` |
| `make infra-up` | Start the Docker Postgres + Redis |
| `make infra-down` | Stop the Docker infrastructure |

### Backend (run from `backend/`)

Every command uses the project venv directly, so no `activate` step is needed.

```bash
.venv/bin/uvicorn app.main:app --reload --port 8000   # API server
.venv/bin/pytest                                      # all 243 tests
.venv/bin/pytest tests/unit                           # unit tests only
.venv/bin/pytest tests/integration                    # integration tests (need the DB)
.venv/bin/pytest tests/unit/test_indicators.py -v     # one file, verbose
.venv/bin/pytest -k causal                            # tests matching a name
.venv/bin/pytest --collect-only -q                    # count tests without running
.venv/bin/ruff check app tests scripts                # lint
.venv/bin/ruff check --fix app tests scripts          # lint and autofix
```

**Migrations**

```bash
.venv/bin/alembic upgrade head                        # apply everything
.venv/bin/alembic current                             # which revision is applied
.venv/bin/alembic history                             # list revisions
.venv/bin/alembic downgrade -1                        # roll back one revision
.venv/bin/alembic revision --autogenerate -m "msg"    # generate from models
```

**Seeding and demo data**

```bash
.venv/bin/python -m scripts.seed                      # roles, permissions, admin, strategies
.venv/bin/python -m scripts.load_demo_data --days 60  # synthetic candles (source='MOCK')
.venv/bin/python -m scripts.load_demo_data --days 120 --seed 42
.venv/bin/python -m scripts.load_demo_data --purge    # delete every synthetic candle
```

### Frontend (run from `frontend/`)

```bash
npm install          # install dependencies
npm run dev          # dev server on :5173
npm run build        # production build to dist/
npm run preview      # serve the production build
npm test             # 18 Vitest tests
npm run lint         # ESLint over src
```

### Importing the real historical data

The 180 GB SQLite import is driven through the API, not a CLI script, so it is
resumable and auditable. Inspect the source schema **before** importing — the
column mapping is read, not assumed:

```
POST /api/v1/market-data/imports/inspect    # read the source table layout
POST /api/v1/market-data/imports            # start a resumable import job
GET  /api/v1/market-data/imports            # list jobs
GET  /api/v1/market-data/imports/{job_id}   # job progress and failures
POST /api/v1/market-data/imports/{job_id}/resume
GET  /api/v1/market-data/quality/summary    # coverage and gaps after import
```

Put the source file in `data/sqlite_source/` (gitignored). Full walkthrough:
[docs/DATA_IMPORT_GUIDE.md](docs/DATA_IMPORT_GUIDE.md).

---

## Folder structure

```
prajwal_trad/
├── Makefile                      all developer commands
├── docker-compose.yml            local Postgres (:5433) + Redis (:6380)
├── .env.example                  every setting, documented; copy to .env
├── PROJECT_STATUS.md             what is done, pending, blocked
│
├── backend/
│   ├── requirements.txt
│   ├── pyproject.toml            ruff + pytest configuration
│   ├── alembic.ini
│   ├── .venv/                    created by `make setup` (gitignored)
│   │
│   ├── app/
│   │   ├── main.py               FastAPI app, middleware, exception handlers
│   │   ├── core/                 config, logging, security, enums, exceptions,
│   │   │                         permissions, charges, market_calendar, safety
│   │   ├── db/                   SQLAlchemy session, declarative base, Redis client
│   │   ├── models/               56 tables across 10 domain modules:
│   │   │                         instrument, market_data, strategy, signal,
│   │   │                         trading, risk, backtest, portfolio, ai, system
│   │   ├── schemas/              Pydantic request/response models (auth, common)
│   │   ├── api/
│   │   │   ├── deps.py           auth + permission dependencies
│   │   │   └── v1/
│   │   │       ├── router.py     mounts the 15 routers
│   │   │       └── routers/      system, auth, dashboard, instruments,
│   │   │                         market_data, strategies, signals, trading,
│   │   │                         risk, backtesting, portfolio, ai, broker,
│   │   │                         notifications, users          (95 routes)
│   │   ├── services/             auth, audit, candles, data_import, data_quality
│   │   ├── strategies/
│   │   │   ├── base.py           BaseStrategy contract + SignalProposal
│   │   │   ├── registry.py       database code -> class mapping
│   │   │   ├── indicators/       19 indicators: trend, momentum,
│   │   │   │                     volatility, volume, levels
│   │   │   └── library/          20 strategies in 4 categories:
│   │   │                         price_action (5), indicator_based (8),
│   │   │                         intraday (5), volume_based (2)
│   │   ├── engines/              risk, signal_engine, combination,
│   │   │                         execution (shared fills), paper_trading,
│   │   │                         backtest, metrics
│   │   ├── brokers/              base abstraction, factory, paper, zerodha
│   │   ├── marketdata/           aggregation, resumable sqlite_importer
│   │   ├── ai/                   Claude client and versioned prompts
│   │   └── workers/              (empty) background jobs — Phase 8
│   │
│   ├── alembic/versions/         d6a740e46dc8 initial schema
│   │                             0002 yearly intraday partitions
│   ├── scripts/                  seed.py, load_demo_data.py
│   └── tests/                    243 tests
│       ├── unit/                 indicators(31) strategies(108) aggregation(21)
│       │                         metrics(15) security(14) execution(13)
│       │                         charges(8) risk_sizing(8) safety(8)
│       ├── integration/          test_api.py(10), test_engines_db.py(7)
│       └── conftest.py           fixtures: session, client, seeded auth
│
├── frontend/
│   ├── package.json              vite, react 18, tailwind, vitest
│   ├── vite.config.js            dev server + /api proxy
│   ├── tailwind.config.js        dark terminal theme tokens
│   └── src/
│       ├── main.jsx              entry point
│       ├── App.jsx               29 routes, guarded by permission
│       ├── api/client.js         axios client with refresh-token rotation
│       ├── store/auth.js         Zustand auth store
│       ├── lib/format.js         Indian number/currency formatting
│       ├── styles/index.css      Tailwind layers and theme
│       ├── components/
│       │   ├── layout/           AppLayout, Sidebar, Topbar, navigation
│       │   ├── ui/               Panel, StatTile, Badge, StateBadge, Loading,
│       │   │                     EmptyState, ErrorState, Toggle, PageHeader,
│       │   │                     PaperTradingBanner, BlockedFeature
│       │   ├── tables/           DataTable (search, sort, paginate, CSV)
│       │   └── charts/           CandleChart (candles, volume, crosshair)
│       ├── pages/
│       │   ├── auth/             Login
│       │   ├── dashboard/        Dashboard
│       │   ├── equity/           Overview, Signals, SignalDetail,
│       │   │                     Positions, TradeHistory
│       │   ├── strategies/       StrategyLibrary, StrategyConfigs
│       │   ├── backtesting/      RunBacktest, BacktestHistory, BacktestDetail
│       │   ├── marketdata/       HistoricalData, DataImports, DataQuality
│       │   ├── instruments/      Instruments
│       │   ├── risk/             RiskManagement
│       │   └── misc/index.jsx    13 remaining screens (portfolio, ai, broker,
│       │                         fno, system, audit, users, settings, …)
│       └── test/                 18 Vitest tests + setup
│
├── docs/                         18 documents (see below)
├── data/                         gitignored working data
│   ├── sqlite_source/            put the 180 GB source file here
│   ├── exports/                  CSV exports
│   └── logs/                     application logs
└── infra/                        (empty) nginx + postgres config — Phase 8
```

---

## How the pieces fit

```
Historical SQLite ──┐
                    ├──> intraday_candles (partitioned) ──> candle service
Broker historical ──┘                                            │
                                                                 v
                                              strategy (pure, no DB, no risk)
                                                                 │
                                                       SignalProposal
                                                                 v
                                      signal engine ── risk engine ── rejected
                                                                 │
                                                           VALIDATED
                                                                 v
                                        paper trading engine ──> Position
                                                                 │
                                        monitor: stop / target / square-off
```

The same `app/engines/execution.py` fills orders for both the paper engine and
the backtester, so a backtest and a paper trade of the same signal are filled
identically.

---

## Design decisions worth knowing

**Costs are not optional.** Every P&L figure is gross, charges and net, stored
and displayed separately. The charge model
(`app/core/charges.py`) implements brokerage caps, STT on the correct leg,
exchange fees, SEBI charges, stamp duty, GST and IPFT, and is parameterised
because the rates change.

**Slippage always hurts.** Buys fill above the reference price, sells below —
on entry *and* exit. When a single candle contains both the stop and the
target, the **stop is assumed first**, because without tick data we cannot know
and the honest choice understates results.

**Entries fill on the next bar's open**, never the signal bar's close.

**Indicators are causal, and tests prove it.** `test_indicator_is_causal`
truncates the series and asserts no past value changes; `test_evaluate_only_reads_rows_up_to_the_last`
does the same for all 20 strategies.

**Risk is independent of strategy.** A strategy proposes; the risk engine
decides whether and how large. Neither imports the other.

**Deactivating a module never abandons a position.** It stops new signals and
new entries. Stop-loss, target and exit processing continue until every
position is closed.

**Blocked beats faked.** Missing broker credentials or API key produce a
`FeatureBlockedError` naming the exact missing dependency — never a simulated
response. The F&O strategy is registered and documented but returns no signals,
because inventing open-interest data from equity candles would be worse than
having none.

---

## Documentation

| Document | Contents |
|---|---|
| [PROJECT_STATUS.md](PROJECT_STATUS.md) | Completed, in progress, pending, blocked, known issues |
| [docs/PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md) | What the platform is and who it is for |
| [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) | Functional and non-functional requirements |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layers, data flow, module boundaries |
| [docs/DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md) | All 56 tables, partitioning, indexing |
| [docs/STRATEGY_DOCUMENTATION.md](docs/STRATEGY_DOCUMENTATION.md) | All 20 strategies and their exact rules |
| [docs/BACKTESTING_GUIDE.md](docs/BACKTESTING_GUIDE.md) | Running backtests, reading results, avoiding self-deception |
| [docs/DATA_IMPORT_GUIDE.md](docs/DATA_IMPORT_GUIDE.md) | Importing the 180 GB SQLite database |
| [docs/BROKER_INTEGRATION.md](docs/BROKER_INTEGRATION.md) | Kite Connect setup and what is blocked |
| [docs/AI_INTEGRATION.md](docs/AI_INTEGRATION.md) | Claude integration and its hard limits |
| [docs/SECURITY.md](docs/SECURITY.md) | Auth, RBAC, secrets, the paper-only guarantee |
| [docs/API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md) | Route reference |
| [docs/TESTING.md](docs/TESTING.md) | What is tested and how to run it |
| [docs/DEVELOPMENT_ROADMAP.md](docs/DEVELOPMENT_ROADMAP.md) | Phases 0–9 |
| [docs/RISK_REGISTER.md](docs/RISK_REGISTER.md) | Technical and financial risks |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common local setup problems |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Phase 8 plan (not yet implemented) |
| [docs/VPS_SETUP.md](docs/VPS_SETUP.md) | Phase 8 server provisioning plan |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | Notable changes |

---

## Honest limitations

- **No live market data.** No broker WebSocket is connected. Every price in the
  UI comes from stored historical or demo data and is labelled as such.
- **The historical importer has not met the real file.** It is written and
  unit-covered, but the 180 GB SQLite database has not been imported yet.
  Inspect the schema first (`POST /market-data/imports/inspect`) — the column
  mapping is read, not assumed.
- **Demo data is a random walk.** `scripts/load_demo_data.py` writes rows with
  `source='MOCK'` and flags the instruments as demo. Backtests against it
  measure the engine, not an edge.
- **`backend/app/workers/` and `infra/` are empty.** They are placeholders for
  Phase 8 (background jobs, Nginx, HTTPS, backups), not working code.
- **No strategy here is known to be profitable.** All 20 are research
  candidates. The engine is built so you can find out honestly, including when
  the answer is no.

---

## Licence

Private project. Not investment advice. Trading involves risk of loss.
