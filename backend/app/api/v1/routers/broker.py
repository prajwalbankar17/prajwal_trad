"""Broker connection status.

Read-only. There is no order-placement route. Credentials are never accepted
over the API, returned by it, or written to the database - they come from the
environment only.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_session, require
from app.brokers.factory import MARKET_DATA_ADAPTERS, get_market_data_adapter
from app.core import safety
from app.core.config import settings
from app.core.exceptions import BrokerError, FeatureBlockedError
from app.models.system import BrokerConnection
from app.services import audit

router = APIRouter(prefix="/broker", tags=["Broker"])


@router.get("/status")
def broker_status(db: Session = Depends(db_session)) -> dict:
    adapter = get_market_data_adapter()
    status = adapter.status()

    return {
        "market_data": status.as_dict(),
        "execution": {
            "adapter": "paper",
            "is_simulated": True,
            **safety.safety_status(),
        },
        "available_adapters": sorted(MARKET_DATA_ADAPTERS),
        "configured_broker": settings.BROKER_NAME,
    }


@router.get("/connections", dependencies=[Depends(require("broker:read"))])
def list_connections(db: Session = Depends(db_session)) -> list[dict]:
    rows = db.scalars(select(BrokerConnection)).all()
    return [
        {
            "id": str(c.id),
            "broker_name": c.broker_name,
            "client_code_masked": c.client_code_masked,
            "is_active": c.is_active,
            "has_credentials": c.has_credentials,
            "connection_status": c.connection_status,
            "last_connected_at": (
                c.last_connected_at.isoformat() if c.last_connected_at else None
            ),
            "last_error": c.last_error,
            "capabilities": c.capabilities,
        }
        for c in rows
    ]


@router.post("/connect", dependencies=[Depends(require("broker:connect"))])
def connect(user=Depends(current_user), db: Session = Depends(db_session)) -> dict:
    """Verify the configured broker credentials by calling the broker.

    Credentials come from the environment. If they are missing, this reports
    the feature as blocked rather than pretending to connect.
    """
    adapter = get_market_data_adapter()
    status = adapter.status()

    connection = db.scalar(
        select(BrokerConnection).where(
            BrokerConnection.user_id == user.id,
            BrokerConnection.broker_name == adapter.name,
        )
    )
    if connection is None:
        connection = BrokerConnection(user_id=user.id, broker_name=adapter.name)
        db.add(connection)

    connection.has_credentials = status.credentials_present
    connection.connection_status = "CONNECTED" if status.connected else "DISCONNECTED"
    connection.is_active = status.connected
    connection.last_error = None if status.connected else status.message
    connection.capabilities = status.capabilities.__dict__

    audit.record(
        db, action="broker.connect_attempt", user_id=user.id,
        entity_type="broker_connection",
        after={"broker": adapter.name, "connected": status.connected},
        severity="WARNING", commit=True,
    )

    if not status.credentials_present:
        raise FeatureBlockedError(
            status.blocked_reason or "Broker credentials are not configured.",
            details={"docs": "docs/BROKER_INTEGRATION.md"},
        )
    if not status.connected:
        raise BrokerError(status.message)
    return status.as_dict()


@router.get("/margins", dependencies=[Depends(require("broker:read"))])
def margins() -> dict:
    """Live margin from the broker. Blocked without credentials - never
    estimated, because an estimated margin is how a position gets rejected at
    the exchange."""
    return get_market_data_adapter().margins()
