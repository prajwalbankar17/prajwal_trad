# Deployment

> **Status: not implemented.** Phase 8 was deferred so local development could
> be completed first. This is the plan, not a description of something that
> exists. `docker-compose.yml` in the repository root is **local development
> infrastructure only** — it has no Nginx, no HTTPS, no workers and no backups.

## Prerequisite

Move long-running work out of FastAPI `BackgroundTasks` into Celery workers.
Running a multi-hour import inside an API worker is acceptable for one
developer on a laptop and wrong on a server. Celery is already a dependency;
the worker module is not written.

## Target topology

```
Internet
   │  443 (HTTPS)
┌──▼──────────────────────────────────────────┐
│ Nginx — TLS termination, rate limiting      │
│   /          → frontend static build         │
│   /api       → api:8000                      │
└──┬────────────────────────┬─────────────────┘
   │                        │
┌──▼────────┐  ┌────────────▼──────┐  ┌──────────────┐
│ api       │  │ worker (Celery)   │  │ scheduler    │
│ uvicorn   │  │ imports,backtests │  │ square-off,  │
│           │  │                   │  │ snapshots    │
└──┬────────┘  └────────┬──────────┘  └──────┬───────┘
   └────────────┬───────┴────────────────────┘
      ┌─────────▼─────────┐   ┌───────────────┐
      │ PostgreSQL 16     │   │ Redis         │
      │ private network   │   │ private       │
      └───────────────────┘   └───────────────┘
```

Neither PostgreSQL nor Redis is exposed publicly.

## Sizing

Driven by **disk**, not CPU.

| | Minimum | Comfortable |
|---|---|---|
| vCPU | 4 | 8 |
| RAM | 8 GB | 16 GB |
| Disk | 400 GB SSD | 600 GB+ SSD |

PostgreSQL will use roughly 1.3–1.6× the SQLite source size. **Measure after a
trial import before committing to a plan** — the specification is explicit
about not buying infrastructure before measuring, and that is the right call.

## Checklist

**Infrastructure**
- [ ] Dockerfiles for api, worker, scheduler; frontend built to static assets
- [ ] `docker-compose.prod.yml` with health checks and `restart: unless-stopped`
- [ ] Nginx config: TLS, HSTS, gzip, static caching, `/api` proxy
- [ ] Let's Encrypt with automated renewal
- [ ] UFW: 22, 80, 443 only
- [ ] PostgreSQL and Redis bound to the internal network

**Configuration**
- [ ] Production `.env`, never committed, mode 600
- [ ] `ENVIRONMENT=production`, `DEBUG=false`, `LOG_JSON=true`
- [ ] Fresh 64-byte `SECRET_KEY`
- [ ] `BACKEND_CORS_ORIGINS` set to the real domain only
- [ ] Verify `/api/v1/safety` still reports paper-only after deployment

**Reliability**
- [ ] `restart: unless-stopped` on every service
- [ ] Health checks wired to the compose healthcheck
- [ ] Log rotation
- [ ] Disk-space alerting — the most likely failure with this dataset
- [ ] Database connection and queue-length monitoring

**Backups**
- [ ] Nightly `pg_dump` to off-server storage
- [ ] **Restore verification** — a backup that has never been restored is not a
      backup. Restore to a scratch database monthly and check row counts
- [ ] Documented recovery procedure with a measured RTO
- [ ] `.env` backed up separately and securely

**Validation**
- [ ] 24/7 runtime observed across a full trading week
- [ ] Verified it keeps running with the developer laptop switched off
- [ ] Market open and square-off observed end to end
- [ ] Restart recovery: no lost positions, daily risk state intact

## Operational notes

- **Timezone.** Keep the server in UTC and let the application handle
  Asia/Kolkata. Mixed server timezones are a recurring source of off-by-one
  session bugs.
- **Scheduler.** Square-off must run even if the strategy engine is down. It is
  a separate service for that reason.
- **Resource limits.** Give the worker a memory cap so a large backtest cannot
  starve the live monitoring services.
- **Deploys during market hours.** Don't. If unavoidable, square off first.

## What stays true in production

Live execution remains disabled. Deployment changes where the code runs, not
what it is allowed to do. Enabling live trading is a separate, reviewed project
with its own validation — see `SECURITY.md`.
