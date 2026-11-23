# Security

## The paper-only guarantee

Live order execution is **disabled and not implemented**. Five independent
mechanisms enforce this; defeating one is not enough.

### 1. An unconditional guard

`app/core/safety.py`:

```python
def assert_live_execution_allowed() -> None:
    """Always raises. Called at every order-placement boundary."""
    raise LiveExecutionForbidden(...)
```

There is no branch. No setting makes it return.
`test_live_execution_raises_even_if_settings_are_flipped` sets
`LIVE_TRADING_ENABLED=True`, `ALLOW_LIVE_ORDER_PLACEMENT=True` and
`EXECUTION_MODE="live"` and asserts it still raises.

### 2. No live adapter exists

`LiveExecutionAdapter` is a placeholder whose every method raises. It exists so
the attachment point is explicit and the absence cannot be mistaken for an
oversight.

### 3. Hardcoded adapter selection

```python
def get_execution_adapter() -> ExecutionAdapter:
    return PaperExecutionAdapter()
```

It takes no argument. Configuration cannot change it.

### 4. Database constraints

```sql
CHECK (execution_mode = 'PAPER')   -- on orders and positions
```

Even a code bug cannot record a live order. Verified by
`test_orders_table_rejects_live_execution_mode`.

### 5. No API surface

There is no route that places an order with a broker. The Zerodha adapter
implements only the read side and has no `place_order` method at all.
`test_no_live_order_route_exists` scans the OpenAPI schema and asserts it.

### Enabling live trading later

It requires, deliberately: writing a real `ExecutionAdapter`, removing the
unconditional raise, changing the factory, dropping two database constraints,
adding API routes and permissions, and separately validating the whole path
with a funded account. That is a reviewed project, not a config change — which
is the point.

---

## Authentication

- **bcrypt** (cost 12) used directly. passlib was dropped: unmaintained since
  2020 and it emits a spurious version error against bcrypt ≥ 4.1.
- Passwords over 72 bytes are **rejected**, not truncated — truncation makes
  two different long passwords interchangeable.
- Strength rule: minimum length plus at least three of lowercase, uppercase,
  digit, symbol.
- **JWT** access tokens (30 min) and refresh tokens (7 days), HS256.
- **Refresh rotation**: the presented refresh token is retired as it is
  exchanged. Sessions are tracked by `jti` and revocable.
- **Account lockout**: 15 minutes after 5 failed attempts.
- **No account enumeration**: an unknown user and a wrong password return the
  same message.
- Changing a password ends every other session.
- The frontend shares a **single in-flight refresh** across concurrent 401s, so
  parallel queries cannot rotate the token ten times and log the user out.

## Authorisation

RBAC with permissions as **rows, not code**. 39 permissions
(`resource:action`), 5 seeded roles. Routes depend on a permission code:

```python
@router.post("/strategies/{id}/activate",
             dependencies=[Depends(require("strategy:activate"))])
```

No route checks a role name, so a new custom role needs no deployment.
Sensitive permissions are flagged (`is_sensitive`) for highlighting in the UI.

| Role | Scope |
|---|---|
| Super Admin | Everything, including roles |
| Admin | Operations; not roles or system secrets |
| Manager | Strategies, risk, paper trading; no user admin, no broker connect |
| Analyst | Research: strategies, backtests, AI. No live controls |
| Viewer | Read-only |

## Secrets

- **Everything from the environment.** `.env` is gitignored; `.env.example` is
  the template and contains no values.
- **No credential is ever stored in the database.** `broker_connections` holds
  a `has_credentials` boolean and a masked client code — never a token, secret
  or password.
- **No credential is returned by the API.** `system_settings` rows flagged
  `is_sensitive` render as `***REDACTED***`.
- **No credential reaches a log.** `app/core/logging.py` has a redaction
  processor over a list of sensitive keys, asserted by
  `test_sensitive_keys_are_redacted_in_logs`.
- `redact()` masks all but the last four characters anywhere a token must be
  referred to.

## Audit logging

Append-only by policy and by construction: `app/services/audit.py` exposes only
`record()`. There is no update or delete helper and no route that modifies a
row. Recorded: sign-in/out, failed attempts, lockouts, password changes, user
and role changes, strategy activation, module activation, risk-limit changes,
kill-switch operation, broker connection attempts, trade actions, AI runs.

Severity escalates: role permission changes and kill-switch operations are
`CRITICAL`.

## AI boundaries

Claude receives text and returns text. It has **no tools, no database handle,
no shell, no order interface**. It cannot place orders, change risk limits,
modify credentials, delete records, execute SQL or bypass paper-trading
controls. Every call is recorded with prompt version, model, context, output,
tokens and cost. Output passes a deterministic validator that flags
overconfident or instruction-shaped language.

## Transport and infrastructure

Phase 1 is local development: HTTP on localhost, CORS restricted to the
configured origins. For Phase 8 — HTTPS termination at Nginx, HSTS, PostgreSQL
and Redis bound to a private network only, firewalled host, rate limiting at
the proxy, secrets from the environment or a secret manager. See
`DEPLOYMENT.md`. **None of this is implemented yet.**

## Reporting

This is a private project. If you find a security problem, fix it on a branch
and note it in `PROJECT_STATUS.md` under Known Issues.
