# Broker Integration

## Status: blocked on credentials

The Zerodha Kite Connect adapter is **written** against the published v3 HTTP
API. What is missing is a **verified round trip**, which needs a funded account
with an active API subscription.

Rather than invent plausible responses, every method raises
`FeatureBlockedError` naming the missing variables when credentials are absent.
Nothing is simulated.

## Architecture

Two separate interfaces, deliberately:

```
MarketDataAdapter (read)            ExecutionAdapter (write)
├── status()                        ├── place_order()
├── capabilities()                  ├── cancel_order()
├── fetch_instruments()             └── order_status()
├── fetch_historical()              │
├── quote()                         ├── PaperExecutionAdapter  ← the only one
├── margins()                       └── LiveExecutionAdapter   ← all methods raise
└── holdings()
```

`ZerodhaAdapter` implements only the read side. **It has no `place_order`
method at all.** The platform never imports a vendor SDK directly.

## Setting up Kite Connect

1. Create an app at <https://developers.kite.trade/> (there is a monthly fee).
2. Put the API key and secret in `.env`:

   ```
   KITE_API_KEY=your_key
   KITE_API_SECRET=your_secret
   ```

3. Complete the login flow to obtain a `request_token`, exchange it for an
   `access_token`, and set:

   ```
   KITE_ACCESS_TOKEN=your_access_token
   ```

4. Restart the backend and check **Broker Connections → Test connection**, or:

   ```bash
   curl localhost:8000/api/v1/broker/status
   ```

> **Access tokens expire daily.** The adapter detects HTTP 403 and returns a
> clear message saying to re-run the login flow. Automating that refresh is a
> pending item.

## Documented limits

| Limit | Value | Where it matters |
|---|---|---|
| Rate limit | ~3 requests/second | Historical backfill must be throttled. |
| Historical window | ~60 days per request for minute data | Backfill loops in windows. |
| WebSocket subscription | ~3,000 instruments | Matches the target universe, with no headroom. |

`ZerodhaAdapter.capabilities()` reports these so callers can plan rather than
discover them at runtime. **Verify them against current Kite documentation** —
they change.

## Interval mapping

Kite's intervals differ from ours. Timeframes not in the map are produced by
resampling 1m data, never requested from the broker:

| Ours | Kite |
|---|---|
| 1m | `minute` |
| 3m | `3minute` |
| 5m | `5minute` |
| 10m | `10minute` |
| 15m | `15minute` |
| 30m | `30minute` |
| 1h | `60minute` |
| 1d | `day` |

Requesting an unmapped interval raises rather than silently substituting one.

## Error handling

| Condition | Behaviour |
|---|---|
| No credentials | `FeatureBlockedError` listing exactly which variables are unset |
| HTTP 403 | `BrokerError` explaining that access tokens expire daily |
| HTTP 429 | `BrokerError` naming the rate limit |
| Network failure | Retried with exponential backoff, 3 attempts, then raised |
| `status != "success"` | `BrokerError` with Kite's own message and error type |

## Security

- Credentials come from the environment only.
- No token, secret or password is written to the database.
  `broker_connections` stores `has_credentials` and a masked client code.
- No credential is logged; `redact()` and the logging processor cover it.
- No credential is returned by any API route.

## Adding another broker (e.g. Kotak Neo)

1. Write `app/brokers/kotak_neo.py` implementing `MarketDataAdapter`.
2. Register it in `MARKET_DATA_ADAPTERS` in `app/brokers/factory.py`.
3. Set `BROKER_NAME=kotak_neo`.

Nothing in the strategy, signal, risk or paper engines changes. That is the
point of the abstraction.

**Do not** add a `place_order` method to a market-data adapter. Execution is a
separate interface, and in this build it is paper only.

## What is not implemented

- **Live WebSocket feed.** Tick streaming, live candle construction, heartbeats
  and reconnection. Blocked on credentials.
- **Automated access-token refresh.**
- **Instrument master sync** to replace auto-created instruments with real
  tokens, lot sizes and ISINs.
- **Live execution.** Not a gap — a deliberate exclusion. See `SECURITY.md`.
