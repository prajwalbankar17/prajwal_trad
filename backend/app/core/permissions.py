"""The permission catalogue.

Permission codes are declared once, here, and seeded into the `permissions`
table. Routes depend on a code (`require("strategy:activate")`); they never
check a role name, so a new custom role needs no code change.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionDef:
    code: str
    resource: str
    action: str
    description: str
    is_sensitive: bool = False


def _p(resource: str, action: str, description: str, sensitive: bool = False) -> PermissionDef:
    return PermissionDef(f"{resource}:{action}", resource, action, description, sensitive)


PERMISSIONS: list[PermissionDef] = [
    # Instruments & market data
    _p("instrument", "read", "View instruments and the universe"),
    _p("instrument", "write", "Create or edit instruments"),
    _p("watchlist", "read", "View watchlists"),
    _p("watchlist", "write", "Create or edit watchlists"),
    _p("marketdata", "read", "View historical and live market data"),
    _p("marketdata", "import", "Start and manage data imports", True),
    _p("marketdata", "quality", "Run and view data-quality reports"),
    # Strategies
    _p("strategy", "read", "View strategies and configurations"),
    _p("strategy", "write", "Create or edit strategy configurations"),
    _p("strategy", "activate", "Enable or disable a strategy", True),
    _p("combination", "read", "View strategy combinations"),
    _p("combination", "write", "Create or edit strategy combinations"),
    # Signals & trading
    _p("signal", "read", "View generated signals"),
    _p("signal", "manage", "Cancel or expire signals", True),
    _p("trade", "read", "View paper positions and trade history"),
    _p("trade", "manage", "Exit or adjust a paper position", True),
    _p("module", "activate", "Activate or deactivate a trading module", True),
    # Risk
    _p("risk", "read", "View risk profiles and utilisation"),
    _p("risk", "write", "Edit risk limits", True),
    _p("risk", "killswitch", "Operate the emergency kill switch", True),
    # Backtesting
    _p("backtest", "read", "View backtests and results"),
    _p("backtest", "run", "Start a backtest"),
    _p("backtest", "delete", "Delete a backtest job", True),
    # Portfolio
    _p("portfolio", "read", "View portfolios and holdings"),
    _p("portfolio", "write", "Edit portfolio settings"),
    # AI
    _p("ai", "read", "View AI research output"),
    _p("ai", "run", "Run an AI research task", True),
    # Broker
    _p("broker", "read", "View broker connection status"),
    _p("broker", "connect", "Connect or disconnect a broker", True),
    # System
    _p("notification", "read", "View notifications"),
    _p("notification", "write", "Edit notification preferences"),
    _p("report", "read", "View reports"),
    _p("system", "monitor", "View system monitoring"),
    _p("system", "settings", "Edit system settings", True),
    _p("audit", "read", "View audit logs"),
    _p("user", "read", "View users"),
    _p("user", "write", "Create or edit users", True),
    _p("role", "read", "View roles and permissions"),
    _p("role", "write", "Create or edit roles and permissions", True),
]

ALL_CODES: set[str] = {p.code for p in PERMISSIONS}


def _codes(*resources: str, actions: tuple[str, ...] | None = None) -> set[str]:
    return {
        p.code
        for p in PERMISSIONS
        if p.resource in resources and (actions is None or p.action in actions)
    }


READ_ONLY: set[str] = {p.code for p in PERMISSIONS if p.action == "read"}

# Seed roles. These are starting points stored as rows - an admin can edit any
# of them, and add custom roles, from the UI.
ROLE_SEEDS: dict[str, dict] = {
    "Super Admin": {
        "description": "Full access, including user and role administration.",
        "priority": 100,
        "permissions": ALL_CODES,
    },
    "Admin": {
        "description": "Operates the platform; cannot manage roles or system secrets.",
        "priority": 80,
        "permissions": ALL_CODES - {"role:write", "system:settings"},
    },
    "Manager": {
        "description": "Runs strategies, risk and paper trading; no user administration.",
        "priority": 60,
        "permissions": (
            READ_ONLY
            | _codes("strategy", "combination", "watchlist", "backtest", "portfolio")
            | {"strategy:activate", "module:activate", "trade:manage", "signal:manage"}
            | {"risk:write", "risk:killswitch", "ai:run", "notification:write"}
        )
        - {"user:write", "role:write", "system:settings", "broker:connect"},
    },
    "Analyst": {
        "description": "Research: strategies, backtests and AI analysis. No live controls.",
        "priority": 40,
        "permissions": READ_ONLY
        | {"backtest:run", "strategy:write", "combination:write", "watchlist:write", "ai:run"},
    },
    "Viewer": {
        "description": "Read-only access to dashboards, signals and reports.",
        "priority": 20,
        "permissions": READ_ONLY,
    },
}
