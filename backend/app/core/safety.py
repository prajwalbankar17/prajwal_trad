"""Execution safety guards.

THE RULE: this build is PAPER TRADING ONLY.

`assert_live_execution_allowed()` raises unconditionally. There is no
configuration value, environment variable, AI tool call, or API endpoint that
makes it return. Enabling live execution requires a deliberate code change plus
a live broker adapter that does not exist in Phase 1 - which is exactly the
point: a config typo, a stray migration, or an AI agent cannot turn real money
on.
"""

from __future__ import annotations

from app.core.config import settings
from app.core.exceptions import LiveExecutionForbidden

PAPER_ONLY_BUILD = True

LIVE_EXECUTION_NOT_IMPLEMENTED = (
    "Live order execution is disabled in this build. Phase 1 is paper trading "
    "only; no live broker execution adapter exists. Enabling it requires an "
    "explicit, reviewed code change and a separately validated live adapter."
)


def assert_live_execution_allowed() -> None:
    """Always raises. Called at every order-placement boundary."""
    raise LiveExecutionForbidden(
        LIVE_EXECUTION_NOT_IMPLEMENTED,
        details={
            "paper_only_build": PAPER_ONLY_BUILD,
            "live_trading_enabled_setting": settings.LIVE_TRADING_ENABLED,
            "execution_mode_setting": settings.EXECUTION_MODE,
        },
    )


def execution_mode() -> str:
    """The only execution mode this build can actually perform."""
    return "paper"


def safety_status() -> dict:
    """Surfaced on the dashboard and on /health so the state is never a guess."""
    return {
        "paper_only_build": PAPER_ONLY_BUILD,
        "effective_execution_mode": execution_mode(),
        "live_order_placement_possible": False,
        "live_trading_enabled_setting": settings.LIVE_TRADING_ENABLED,
        "allow_live_order_placement_setting": settings.ALLOW_LIVE_ORDER_PLACEMENT,
        "note": LIVE_EXECUTION_NOT_IMPLEMENTED,
    }
