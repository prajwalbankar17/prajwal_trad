"""Dashboard aggregates.

Every money figure here is PAPER trading, after costs. The response says so
explicitly so the UI can label it and nobody mistakes it for a live account.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import db_session, require
from app.core import safety
from app.core.enums import PositionStatus, SignalState
from app.core.market_calendar import market_status, now_ist
from app.engines.risk import RiskEngine, get_default_profile
from app.models.instrument import Instrument
from app.models.market_data import DataAvailability
from app.models.portfolio import Portfolio
from app.models.signal import TradingSignal
from app.models.strategy import Strategy, StrategyConfig, TradingModuleState
from app.models.trading import Position

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("", dependencies=[Depends(require("trade:read"))])
def dashboard(db: Session = Depends(db_session)) -> dict:
    now = now_ist()
    today = now.date()

    portfolio = db.scalar(select(Portfolio).where(Portfolio.is_default.is_(True)))
    profile = get_default_profile(db)
    risk = RiskEngine(db, profile)
    utilisation = risk.utilisation()

    closed_today = db.scalars(
        select(Position).where(
            Position.is_backtest.is_(False),
            Position.trade_date == today,
            Position.status == PositionStatus.CLOSED,
        )
    ).all()
    open_positions = db.scalars(
        select(Position).where(
            Position.is_backtest.is_(False),
            Position.status.in_([PositionStatus.OPEN, PositionStatus.PARTIALLY_CLOSED]),
        )
    ).all()

    all_closed = db.scalars(
        select(Position).where(
            Position.is_backtest.is_(False), Position.status == PositionStatus.CLOSED
        )
    ).all()
    wins = [p for p in all_closed if float(p.net_pnl) > 0]
    losses = [p for p in all_closed if float(p.net_pnl) < 0]

    realised_today = sum(float(p.net_pnl) for p in closed_today)
    unrealised = sum(float(p.unrealised_pnl) for p in open_positions)

    active_signals = (
        db.scalar(
            select(func.count())
            .select_from(TradingSignal)
            .where(
                TradingSignal.is_backtest.is_(False),
                TradingSignal.state.in_([SignalState.GENERATED, SignalState.VALIDATED]),
            )
        )
        or 0
    )
    signals_today = (
        db.scalar(
            select(func.count())
            .select_from(TradingSignal)
            .where(
                TradingSignal.is_backtest.is_(False),
                TradingSignal.generated_at >= now - timedelta(days=1),
            )
        )
        or 0
    )

    recent = db.execute(
        select(Position, Instrument)
        .join(Instrument, Instrument.id == Position.instrument_id)
        .where(Position.is_backtest.is_(False))
        .order_by(Position.entry_time.desc())
        .limit(10)
    ).all()

    modules = db.scalars(select(TradingModuleState)).all()

    return {
        "execution_mode": safety.execution_mode(),
        "is_paper_trading": True,
        "disclaimer": (
            "All capital and P&L figures below are SIMULATED paper trading, "
            "net of modelled brokerage, taxes and slippage. No real orders exist."
        ),
        "market": {
            "status": market_status(),
            "server_time_ist": now.isoformat(),
            "feed_connected": False,
        },
        "capital": {
            "total_capital": float(portfolio.starting_capital) if portfolio else 0.0,
            "current_capital": float(portfolio.current_capital) if portfolio else 0.0,
            "available_capital": float(portfolio.available_capital) if portfolio else 0.0,
            "used_capital": float(portfolio.deployed_capital) if portfolio else 0.0,
            "total_charges_paid": float(portfolio.total_charges) if portfolio else 0.0,
        },
        "pnl": {
            "today_realised": round(realised_today, 2),
            "today_unrealised": round(unrealised, 2),
            "today_total": round(realised_today + unrealised, 2),
            "all_time_realised": round(
                float(portfolio.realised_pnl) if portfolio else 0.0, 2
            ),
            "note": "Net of charges. Gross figures are available per position.",
        },
        "trades": {
            "total": len(all_closed),
            "winning": len(wins),
            "losing": len(losses),
            "win_rate": round(len(wins) / len(all_closed) * 100, 2) if all_closed else 0.0,
            "today": len(closed_today),
            "open_positions": len(open_positions),
        },
        "strategies": {
            "total": db.scalar(select(func.count()).select_from(Strategy)) or 0,
            "active": db.scalar(
                select(func.count()).select_from(Strategy).where(Strategy.is_active.is_(True))
            )
            or 0,
            "configured": db.scalar(select(func.count()).select_from(StrategyConfig)) or 0,
            "enabled_configs": db.scalar(
                select(func.count())
                .select_from(StrategyConfig)
                .where(StrategyConfig.is_enabled.is_(True))
            )
            or 0,
        },
        "signals": {"active": active_signals, "last_24h": signals_today},
        "risk": utilisation,
        "modules": [
            {"module": m.module, "is_active": m.is_active} for m in modules
        ],
        "data": {
            "instruments": db.scalar(select(func.count()).select_from(Instrument)) or 0,
            "instruments_with_usable_data": db.scalar(
                select(func.count())
                .select_from(DataAvailability)
                .where(DataAvailability.is_usable.is_(True))
            )
            or 0,
        },
        "recent_trades": [
            {
                "id": str(p.id),
                "tradingsymbol": i.tradingsymbol,
                "direction": p.direction,
                "quantity": p.quantity,
                "entry_price": float(p.entry_price),
                "exit_price": float(p.exit_price) if p.exit_price else None,
                "status": p.status,
                "net_pnl": float(p.net_pnl),
                "entry_time": p.entry_time.isoformat(),
            }
            for p, i in recent
        ],
    }
