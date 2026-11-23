"""Broker abstraction.

The platform talks to this interface, never to a vendor SDK. Swapping Zerodha
for Kotak Neo means adding an adapter, not touching the strategy, signal, risk
or paper engines.

Execution is split deliberately:

* `MarketDataAdapter` - read-only: instruments, historical candles, quotes,
  the live feed.
* `ExecutionAdapter` - places orders. `PaperExecutionAdapter` is the only
  implementation in this build. A live adapter does not exist, and
  `assert_live_execution_allowed()` guards the boundary where one would plug in.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.core.exceptions import FeatureBlockedError
from app.core.safety import assert_live_execution_allowed


@dataclass
class BrokerCapabilities:
    historical_data: bool = False
    live_feed: bool = False
    order_placement: bool = False
    margins: bool = False
    holdings: bool = False
    max_instruments_per_subscription: int = 0
    historical_days_per_request: int = 0
    rate_limit_per_second: int = 0


@dataclass
class ConnectionStatus:
    connected: bool
    broker: str
    message: str
    credentials_present: bool = False
    token_expires_at: datetime | None = None
    capabilities: BrokerCapabilities = field(default_factory=BrokerCapabilities)
    blocked_reason: str | None = None

    def as_dict(self) -> dict:
        return {
            "connected": self.connected,
            "broker": self.broker,
            "message": self.message,
            "credentials_present": self.credentials_present,
            "token_expires_at": (
                self.token_expires_at.isoformat() if self.token_expires_at else None
            ),
            "capabilities": self.capabilities.__dict__,
            "blocked_reason": self.blocked_reason,
        }


@dataclass
class OrderRequest:
    tradingsymbol: str
    exchange: str
    side: str
    quantity: int
    order_type: str = "MARKET"
    product: str = "MIS"
    price: float | None = None
    trigger_price: float | None = None
    tag: str | None = None


@dataclass
class OrderResponse:
    order_id: str
    status: str
    message: str = ""
    average_price: float | None = None
    filled_quantity: int = 0
    is_simulated: bool = True


class MarketDataAdapter(ABC):
    name: str = "base"

    @abstractmethod
    def status(self) -> ConnectionStatus: ...

    @abstractmethod
    def capabilities(self) -> BrokerCapabilities: ...

    @abstractmethod
    def fetch_instruments(self, exchange: str | None = None) -> list[dict]: ...

    @abstractmethod
    def fetch_historical(
        self,
        instrument_token: int,
        *,
        start: date | datetime,
        end: date | datetime,
        interval: str,
    ) -> list[dict]: ...

    @abstractmethod
    def quote(self, instrument_tokens: list[int]) -> dict[int, dict]: ...

    def margins(self) -> dict:
        raise FeatureBlockedError(f"{self.name} does not expose margin information.")

    def holdings(self) -> list[dict]:
        raise FeatureBlockedError(f"{self.name} does not expose holdings.")


class ExecutionAdapter(ABC):
    name: str = "base"
    is_paper: bool = True

    @abstractmethod
    def place_order(self, request: OrderRequest) -> OrderResponse: ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> OrderResponse: ...

    @abstractmethod
    def order_status(self, order_id: str) -> OrderResponse: ...


class LiveExecutionAdapter(ExecutionAdapter):
    """Placeholder for a future live adapter.

    Every method raises. It exists so the architecture is explicit about where
    live execution *would* attach, and so no one can mistake the absence of a
    live adapter for an oversight. Implementing this requires a separate,
    reviewed authorisation step - see docs/SECURITY.md.
    """

    name = "live"
    is_paper = False

    def place_order(self, request: OrderRequest) -> OrderResponse:
        assert_live_execution_allowed()
        raise AssertionError("unreachable")  # pragma: no cover

    def cancel_order(self, order_id: str) -> OrderResponse:
        assert_live_execution_allowed()
        raise AssertionError("unreachable")  # pragma: no cover

    def order_status(self, order_id: str) -> OrderResponse:
        assert_live_execution_allowed()
        raise AssertionError("unreachable")  # pragma: no cover


def redact(value: str | None, *, keep: int = 4) -> str:
    """Never log a token. This is what goes in a log line instead."""
    if not value:
        return ""
    return f"{'*' * max(len(value) - keep, 0)}{value[-keep:]}" if len(value) > keep else "****"


def summarise_for_log(payload: dict[str, Any]) -> dict[str, Any]:
    sensitive = {"access_token", "api_secret", "api_key", "request_token", "password"}
    return {
        key: (redact(str(value)) if key in sensitive else value)
        for key, value in payload.items()
    }
