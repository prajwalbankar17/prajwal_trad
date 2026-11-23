"""The paper-only guarantee.

If any of these ever fail, the build can place a real order. They are the most
important tests in the repository.
"""

from __future__ import annotations

import pytest

from app.brokers.base import LiveExecutionAdapter, OrderRequest, redact
from app.brokers.factory import get_execution_adapter
from app.brokers.paper import PaperExecutionAdapter
from app.core import safety
from app.core.exceptions import LiveExecutionForbidden


def test_assert_live_execution_always_raises():
    with pytest.raises(LiveExecutionForbidden):
        safety.assert_live_execution_allowed()


def test_live_execution_raises_even_if_settings_are_flipped(monkeypatch):
    """Config alone must never be enough."""
    monkeypatch.setattr(safety.settings, "LIVE_TRADING_ENABLED", True)
    monkeypatch.setattr(safety.settings, "ALLOW_LIVE_ORDER_PLACEMENT", True)
    monkeypatch.setattr(safety.settings, "EXECUTION_MODE", "live")

    with pytest.raises(LiveExecutionForbidden):
        safety.assert_live_execution_allowed()
    assert safety.execution_mode() == "paper"
    assert safety.safety_status()["live_order_placement_possible"] is False


def test_execution_mode_is_always_paper():
    assert safety.execution_mode() == "paper"


def test_factory_only_ever_returns_the_paper_adapter():
    adapter = get_execution_adapter()
    assert isinstance(adapter, PaperExecutionAdapter)
    assert adapter.is_paper


def test_live_adapter_methods_all_raise():
    adapter = LiveExecutionAdapter()
    request = OrderRequest(
        tradingsymbol="TEST", exchange="NSE", side="BUY", quantity=1, price=100
    )
    for call in (
        lambda: adapter.place_order(request),
        lambda: adapter.cancel_order("x"),
        lambda: adapter.order_status("x"),
    ):
        with pytest.raises(LiveExecutionForbidden):
            call()


def test_paper_order_is_marked_simulated():
    adapter = PaperExecutionAdapter()
    response = adapter.place_order(
        OrderRequest(
            tradingsymbol="TEST", exchange="NSE", side="BUY", quantity=10, price=100
        )
    )
    assert response.is_simulated
    assert response.order_id.startswith("PAPER-")
    assert "no order was sent" in response.message.lower()


def test_redact_hides_all_but_the_last_characters():
    assert redact("supersecrettoken").endswith("oken")
    assert "supersecret" not in redact("supersecrettoken")
    assert redact("") == ""
    assert redact("ab") == "****"


def test_sensitive_keys_are_redacted_in_logs():
    from app.core.logging import _redact

    event = {"access_token": "abc123", "api_secret": "shh", "symbol": "RELIANCE"}
    cleaned = _redact(None, "", dict(event))
    assert cleaned["access_token"] == "***REDACTED***"
    assert cleaned["api_secret"] == "***REDACTED***"
    assert cleaned["symbol"] == "RELIANCE"
