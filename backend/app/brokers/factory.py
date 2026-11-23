"""Adapter selection.

The rest of the platform asks for "the market data adapter" and "the execution
adapter" and gets whatever is configured - with the hard guarantee that the
execution adapter is always the paper one in this build.
"""

from __future__ import annotations

from app.brokers.base import ExecutionAdapter, MarketDataAdapter
from app.brokers.paper import PaperExecutionAdapter
from app.brokers.zerodha import ZerodhaAdapter
from app.core.config import settings

MARKET_DATA_ADAPTERS: dict[str, type[MarketDataAdapter]] = {
    "zerodha": ZerodhaAdapter,
    # "kotak_neo": KotakNeoAdapter,   # future - see docs/BROKER_INTEGRATION.md
}


def get_market_data_adapter(name: str | None = None) -> MarketDataAdapter:
    broker = (name or settings.BROKER_NAME).lower()
    adapter_cls = MARKET_DATA_ADAPTERS.get(broker)
    if adapter_cls is None:
        raise ValueError(
            f"No market-data adapter for '{broker}'. "
            f"Available: {sorted(MARKET_DATA_ADAPTERS)}"
        )
    return adapter_cls()


def get_execution_adapter() -> ExecutionAdapter:
    """Always paper.

    This is not configurable. A live adapter is not implemented, and routing
    here is one of the places that keeps a config change from becoming a real
    order.
    """
    return PaperExecutionAdapter()
