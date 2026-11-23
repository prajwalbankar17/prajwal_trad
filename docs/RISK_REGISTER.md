# Risk Register

## Technical

| # | Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|---|
| T1 | Look-ahead bias makes a strategy look profitable when it is not | **Critical** — you trade something that cannot work | Medium without controls | Every indicator is causality-tested; all 20 strategies are tested for it; entries fill on the next bar's open; levels use strictly prior sessions |
| T2 | Transaction costs ignored or understated | **Critical** — a gross edge that nets negative | High in naive backtests | Full Indian charge model; slippage always adverse; gross/charges/net stored separately; never report net as gross |
| T3 | Overfitting to the sample | **High** — live results diverge | High | In-sample/out-of-sample split with explicit heuristics; small samples flagged; Sharpe suppressed below 20 observations |
| T4 | Accidental live order execution | **Critical** — real money lost | Low by construction | Five independent mechanisms (`SECURITY.md`), including database CHECK constraints and an unconditional raise |
| T5 | 180 GB import exhausts disk | High — the server stops | Medium | PostgreSQL needs ~1.3–1.6× the source. Trial import and measure before the full run (`DATA_IMPORT_GUIDE.md`) |
| T6 | Import interrupted after hours of work | Medium | Medium | Resumable cursor committed per batch; idempotent inserts; resume endpoint |
| T7 | Candle table too large to query | High | Medium | Yearly RANGE partitioning plus a composite index; higher timeframes resampled rather than stored |
| T8 | Stale data treated as live | **High** — trading on prices that no longer exist | Medium | Freshness guard refuses to signal on data older than the threshold; `data_source` and `data_age_seconds` on every signal; UI states plainly when no feed is connected |
| T9 | Incomplete data silently narrows a backtest | High — a "universe-wide" result over 40 names | High | `data_availability` gating; `data_coverage.skipped` reported; thin-session detection |
| T10 | Corporate actions distort price series | Medium | High over long histories | Tables and `adjusted_close` exist; **adjustment job not yet written** — a known gap |
| T11 | Long job blocks the API | Medium | High on a VPS | Known. Move to Celery before Phase 8 |
| T12 | Broker API changes or rate-limits | Medium | Medium | Adapter isolation; documented limits; backoff; clear 403/429 messages |
| T13 | Access token expires mid-session | Medium | **Certain** — Kite tokens expire daily | Detected and reported clearly; automated refresh is pending |
| T14 | Secrets leak via logs or API | **High** | Low | Redaction processor; no credential in the database; sensitive settings redacted on read; tested |
| T15 | Holiday list drifts from the exchange calendar | Medium — wrong session counts | High | `market_holidays` table preferred over the seed; `holiday_source()` reports which was used |

## Financial and operational

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| F1 | No strategy here is profitable | **High** — the likeliest outcome for any retail strategy set | The platform is built to find this out cheaply and unambiguously. All 20 are labelled research candidates |
| F2 | Broker leverage assumed and then withdrawn | High — rejected orders, forced square-off | `assumed_leverage` defaults to 1.0; broker margin used when available and the lower applies |
| F3 | Costs exceed expectations | Medium | Rates are parameterised; verify against your contract note |
| F4 | Kite Connect subscription cost | Low | Monthly fee; evaluate against usage |
| F5 | Claude API cost runs away | Low | Monthly budget enforced **before** each call; usage and estimated cost recorded and displayed |
| F6 | VPS cost grows with data | Medium | Measure after the real import before sizing. Disk, not CPU, is the constraint |
| F7 | Daily loss limit breached repeatedly | High | Hard halt on new entries; kill switch; every breach recorded |

## Accepted, with reasoning

| Decision | Accepted risk | Why |
|---|---|---|
| Stop assumed before target within one candle | Understates results | Without tick data it is unknowable; the conservative choice is the honest one |
| Minute data is the only stored intraday timeframe | Resampling cost on every read | Removes drift between stored and derived candles; the cost is small and bounded |
| Ticks not persisted by default | Cannot replay a tick-level session | Volume is enormous and the value is low for candle-based strategies |
| Order blocks not implemented in SMC | Incomplete versus some definitions | The definition is too contested to encode without inventing one |
| Demo data is a random walk | Could mislead if mistaken for real | Marked `source='MOCK'`, instruments flagged, labelled in the UI, purgeable |

## Review triggers

Revisit this register when: the real import completes (T5, T7, T9 become
measurable); broker credentials arrive (T8, T12, T13 become live);
Phase 8 begins (T11, T14); the first strategy shows a positive out-of-sample
result (T1, T2, T3 all deserve re-examination before believing it).
