"""v1 API aggregator."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routers import (
    ai,
    auth,
    backtesting,
    broker,
    dashboard,
    instruments,
    market_data,
    notifications,
    portfolio,
    risk,
    signals,
    strategies,
    system,
    trading,
    users,
)

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(dashboard.router)
api_router.include_router(instruments.router)
api_router.include_router(market_data.router)
api_router.include_router(strategies.router)
api_router.include_router(signals.router)
api_router.include_router(trading.router)
api_router.include_router(risk.router)
api_router.include_router(backtesting.router)
api_router.include_router(portfolio.router)
api_router.include_router(ai.router)
api_router.include_router(broker.router)
api_router.include_router(notifications.router)
api_router.include_router(users.router)
