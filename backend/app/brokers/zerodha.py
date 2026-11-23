"""Zerodha Kite Connect adapter.

STATUS: BLOCKED ON CREDENTIALS.

The interface is complete and the request shapes follow the published Kite
Connect v3 HTTP API. What is *not* here is a verified round trip, because that
needs a funded account with an active API subscription.

Rather than invent plausible responses, every method raises `FeatureBlockedError`
with the specific missing dependency when credentials are absent. When
KITE_API_KEY, KITE_API_SECRET and KITE_ACCESS_TOKEN are supplied the calls run
for real - and must then be verified against the live API before anything
depends on them. See docs/BROKER_INTEGRATION.md.

Deliberate limits:

* This adapter is read-only. It has no `place_order`. Order placement lives in
  `ExecutionAdapter`, and the live one is not implemented.
* No credential is ever logged, stored in the database, or returned by an API
  route.
"""

from __future__ import annotations

from datetime import date, datetime

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.brokers.base import (
    BrokerCapabilities,
    ConnectionStatus,
    MarketDataAdapter,
)
from app.core.config import settings
from app.core.exceptions import BrokerError, FeatureBlockedError
from app.core.logging import get_logger

log = get_logger(__name__)

KITE_BASE_URL = "https://api.kite.trade"
KITE_API_VERSION = "3"

# Kite's documented intervals. Our timeframes that are not in this list are
# produced by resampling minute data, never requested from the broker.
INTERVAL_MAP = {
    "1m": "minute",
    "3m": "3minute",
    "5m": "5minute",
    "10m": "10minute",
    "15m": "15minute",
    "30m": "30minute",
    "1h": "60minute",
    "1d": "day",
}

MISSING_CREDENTIALS = (
    "Zerodha Kite Connect credentials are not configured. Set KITE_API_KEY, "
    "KITE_API_SECRET and KITE_ACCESS_TOKEN in the environment. This feature is "
    "blocked until a Kite Connect subscription is active - it is not simulated."
)


class ZerodhaAdapter(MarketDataAdapter):
    name = "zerodha"

    def __init__(self, *, timeout: float = 10.0) -> None:
        self.api_key = settings.KITE_API_KEY
        self.access_token = settings.KITE_ACCESS_TOKEN
        self.timeout = timeout

    # -- status ----------------------------------------------------------

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.access_token)

    def capabilities(self) -> BrokerCapabilities:
        return BrokerCapabilities(
            historical_data=True,
            live_feed=True,
            order_placement=False,      # not exposed by this adapter, by design
            margins=True,
            holdings=True,
            max_instruments_per_subscription=3000,
            historical_days_per_request=60,   # minute data: Kite caps the window
            rate_limit_per_second=3,
        )

    def status(self) -> ConnectionStatus:
        if not self.configured:
            return ConnectionStatus(
                connected=False,
                broker=self.name,
                message="Not connected.",
                credentials_present=False,
                capabilities=self.capabilities(),
                blocked_reason=MISSING_CREDENTIALS,
            )
        try:
            profile = self._get("/user/profile")
            return ConnectionStatus(
                connected=True,
                broker=self.name,
                message=f"Connected as {profile.get('user_shortname', 'unknown')}.",
                credentials_present=True,
                capabilities=self.capabilities(),
            )
        except BrokerError as exc:
            return ConnectionStatus(
                connected=False,
                broker=self.name,
                message=str(exc),
                credentials_present=True,
                capabilities=self.capabilities(),
            )

    # -- http ------------------------------------------------------------

    def _headers(self) -> dict:
        return {
            "X-Kite-Version": KITE_API_VERSION,
            "Authorization": f"token {self.api_key}:{self.access_token}",
        }

    def _require_credentials(self) -> None:
        if not self.configured:
            raise FeatureBlockedError(
                MISSING_CREDENTIALS,
                details={
                    "missing": [
                        key
                        for key, value in (
                            ("KITE_API_KEY", self.api_key),
                            ("KITE_ACCESS_TOKEN", self.access_token),
                        )
                        if not value
                    ],
                    "docs": "docs/BROKER_INTEGRATION.md",
                },
            )

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _get(self, path: str, params: dict | None = None) -> dict:
        self._require_credentials()
        try:
            with httpx.Client(base_url=KITE_BASE_URL, timeout=self.timeout) as client:
                response = client.get(path, headers=self._headers(), params=params)
        except httpx.TransportError as exc:
            log.warning("kite_transport_error", path=path, error=str(exc))
            raise

        if response.status_code == 403:
            raise BrokerError(
                "Kite rejected the access token (403). Access tokens expire daily; "
                "re-run the login flow to obtain a new one.",
                details={"path": path},
            )
        if response.status_code == 429:
            raise BrokerError(
                "Kite rate limit exceeded. Reduce request frequency "
                f"(limit is ~{self.capabilities().rate_limit_per_second}/second).",
                details={"path": path},
            )
        if response.status_code >= 400:
            raise BrokerError(
                f"Kite returned HTTP {response.status_code}.",
                details={"path": path, "body": response.text[:500]},
            )

        payload = response.json()
        if payload.get("status") != "success":
            raise BrokerError(
                payload.get("message", "Kite reported a failure."),
                details={"path": path, "error_type": payload.get("error_type")},
            )
        return payload.get("data", {})

    # -- market data -----------------------------------------------------

    def fetch_instruments(self, exchange: str | None = None) -> list[dict]:
        """Kite serves the instrument dump as CSV, not JSON."""
        self._require_credentials()
        path = f"/instruments/{exchange}" if exchange else "/instruments"
        with httpx.Client(base_url=KITE_BASE_URL, timeout=60.0) as client:
            response = client.get(path, headers=self._headers())
        if response.status_code >= 400:
            raise BrokerError(
                f"Instrument download failed with HTTP {response.status_code}.",
                details={"path": path},
            )

        import csv
        import io

        return list(csv.DictReader(io.StringIO(response.text)))

    def fetch_historical(
        self,
        instrument_token: int,
        *,
        start: date | datetime,
        end: date | datetime,
        interval: str,
    ) -> list[dict]:
        kite_interval = INTERVAL_MAP.get(interval)
        if kite_interval is None:
            raise BrokerError(
                f"Kite does not serve the {interval} interval directly. "
                "Request 1m and resample.",
                details={"supported": sorted(INTERVAL_MAP)},
            )
        data = self._get(
            f"/instruments/historical/{instrument_token}/{kite_interval}",
            params={
                "from": _fmt(start),
                "to": _fmt(end),
                "oi": 0,
            },
        )
        return [
            {
                "ts": row[0],
                "open": row[1],
                "high": row[2],
                "low": row[3],
                "close": row[4],
                "volume": row[5],
            }
            for row in data.get("candles", [])
        ]

    def quote(self, instrument_tokens: list[int]) -> dict[int, dict]:
        if not instrument_tokens:
            return {}
        data = self._get("/quote", params={"i": [str(t) for t in instrument_tokens]})
        return {int(payload["instrument_token"]): payload for payload in data.values()}

    def margins(self) -> dict:
        return self._get("/user/margins")

    def holdings(self) -> list[dict]:
        result = self._get("/portfolio/holdings")
        return result if isinstance(result, list) else []


def _fmt(value: date | datetime) -> str:
    return (
        value.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(value, datetime)
        else value.strftime("%Y-%m-%d")
    )
