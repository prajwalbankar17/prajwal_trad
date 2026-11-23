"""Paper positions, orders and trade history.

Every route here operates on simulated trades. There is no order-placement
endpoint for live execution in this API, by design.
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_session, page_params, require
from app.core import safety
from app.core.enums import ExitReason, PositionStatus
from app.core.exceptions import NotFoundError
from app.engines.paper_trading import PaperTradingEngine
from app.engines.risk import RiskEngine, get_default_profile
from app.models.instrument import Instrument
from app.models.portfolio import Portfolio
from app.models.signal import TradingSignal
from app.models.trading import ExitRecord, Order, Position, TradeExecution
from app.schemas.common import Page, PageParams
from app.services import audit
from app.services import candles as candle_service

router = APIRouter(prefix="/trading", tags=["Paper Trading"])


def _position_out(p: Position, instrument: Instrument | None = None) -> dict:
    return {
        "id": str(p.id),
        "execution_mode": p.execution_mode,
        "module": p.module,
        "instrument_id": str(p.instrument_id),
        "tradingsymbol": instrument.tradingsymbol if instrument else None,
        "direction": p.direction,
        "product": p.product,
        "quantity": p.quantity,
        "remaining_quantity": p.remaining_quantity,
        "entry_price": float(p.entry_price),
        "entry_time": p.entry_time.isoformat(),
        "exit_price": float(p.exit_price) if p.exit_price is not None else None,
        "exit_time": p.exit_time.isoformat() if p.exit_time else None,
        "exit_reason": p.exit_reason,
        "stop_loss": float(p.stop_loss),
        "initial_stop_loss": float(p.initial_stop_loss),
        "target": float(p.target),
        "trailing_stop_active": p.trailing_stop_active,
        "status": p.status,
        "gross_pnl": float(p.gross_pnl),
        "charges": float(p.charges),
        "net_pnl": float(p.net_pnl),
        "unrealised_pnl": float(p.unrealised_pnl),
        "max_favourable_excursion": float(p.max_favourable_excursion),
        "max_adverse_excursion": float(p.max_adverse_excursion),
        "capital_deployed": float(p.capital_deployed),
        "trade_date": p.trade_date.isoformat(),
    }


@router.get("/positions", dependencies=[Depends(require("trade:read"))])
def list_positions(
    db: Session = Depends(db_session),
    params: PageParams = Depends(page_params),
    status: PositionStatus | None = None,
    open_only: bool = False,
    on_date: date | None = Query(None, alias="date"),
) -> Page:
    stmt = select(Position, Instrument).join(
        Instrument, Instrument.id == Position.instrument_id
    )
    count_stmt = select(func.count()).select_from(Position)

    filters = [Position.is_backtest.is_(False)]
    if open_only:
        filters.append(
            Position.status.in_([PositionStatus.OPEN, PositionStatus.PARTIALLY_CLOSED])
        )
    elif status:
        filters.append(Position.status == str(status))
    if on_date:
        filters.append(Position.trade_date == on_date)

    for f in filters:
        stmt = stmt.where(f)
        count_stmt = count_stmt.where(f)

    total = db.scalar(count_stmt) or 0
    rows = db.execute(
        stmt.order_by(Position.entry_time.desc())
        .offset(params.offset)
        .limit(params.page_size)
    ).all()
    return Page(
        items=[_position_out(p, i) for p, i in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/positions/{position_id}", dependencies=[Depends(require("trade:read"))])
def get_position(position_id: uuid.UUID, db: Session = Depends(db_session)) -> dict:
    position = db.get(Position, position_id)
    if position is None:
        raise NotFoundError("Position not found.")
    instrument = db.get(Instrument, position.instrument_id)
    executions = db.scalars(
        select(TradeExecution)
        .where(TradeExecution.position_id == position.id)
        .order_by(TradeExecution.executed_at)
    ).all()
    exits = db.scalars(
        select(ExitRecord).where(ExitRecord.position_id == position.id)
    ).all()
    orders = db.scalars(select(Order).where(Order.position_id == position.id)).all()

    return {
        **_position_out(position, instrument),
        "charge_breakdown": position.charge_breakdown,
        "executions": [
            {
                "side": e.side,
                "leg": e.leg,
                "quantity": e.quantity,
                "price": float(e.price),
                "requested_price": float(e.requested_price) if e.requested_price else None,
                "slippage": float(e.slippage),
                "charges": float(e.charges),
                "executed_at": e.executed_at.isoformat(),
            }
            for e in executions
        ],
        "exits": [
            {
                "quantity": x.quantity,
                "exit_price": float(x.exit_price),
                "exit_time": x.exit_time.isoformat(),
                "reason": x.reason,
                "gross_pnl": float(x.gross_pnl),
                "charges": float(x.charges),
                "net_pnl": float(x.net_pnl),
                "is_partial": x.is_partial,
            }
            for x in exits
        ],
        "orders": [
            {
                "id": str(o.id),
                "side": o.side,
                "order_type": o.order_type,
                "quantity": o.quantity,
                "average_price": float(o.average_price) if o.average_price else None,
                "status": o.status,
                "execution_mode": o.execution_mode,
                "simulation": o.simulation,
            }
            for o in orders
        ],
    }


class EnterRequest(BaseModel):
    signal_id: uuid.UUID
    portfolio_id: uuid.UUID | None = None


@router.post("/positions/enter", dependencies=[Depends(require("trade:manage"))])
def enter_position(
    payload: EnterRequest,
    user=Depends(current_user),
    db: Session = Depends(db_session),
) -> dict:
    """Open a PAPER position from a validated signal.

    This can only ever create a simulated position - see `/safety`.
    """
    signal = db.get(TradingSignal, payload.signal_id)
    if signal is None:
        raise NotFoundError("Signal not found.")

    portfolio = (
        db.get(Portfolio, payload.portfolio_id)
        if payload.portfolio_id
        else db.scalar(select(Portfolio).where(Portfolio.is_default.is_(True)))
    )
    engine = PaperTradingEngine(db, RiskEngine(db, get_default_profile(db)))
    result = engine.enter_from_signal(signal, portfolio=portfolio)

    audit.record(
        db, action="paper_trade.enter", user_id=user.id, entity_type="signal",
        entity_id=signal.id, after={"created": result.created, "reason": result.reason},
        commit=True,
    )
    return {
        "created": result.created,
        "reason": result.reason,
        "execution_mode": safety.execution_mode(),
        "position": _position_out(result.position) if result.position else None,
    }


class ExitRequest(BaseModel):
    exit_price: float | None = None
    quantity: int | None = None
    reason: str = "MANUAL"


@router.post("/positions/{position_id}/exit", dependencies=[Depends(require("trade:manage"))])
def exit_position(
    position_id: uuid.UUID,
    payload: ExitRequest,
    user=Depends(current_user),
    db: Session = Depends(db_session),
) -> dict:
    position = db.get(Position, position_id)
    if position is None:
        raise NotFoundError("Position not found.")

    price = payload.exit_price
    if price is None:
        candle = candle_service.latest_candle(db, position.instrument_id)
        if candle is None:
            raise NotFoundError("No price available to exit at; supply exit_price.")
        price = float(candle["close"])

    engine = PaperTradingEngine(db, RiskEngine(db, get_default_profile(db)))
    engine.close_position(
        position,
        exit_price=price,
        reason=ExitReason(payload.reason) if payload.reason in ExitReason.__members__.values()
        else ExitReason.MANUAL,
        quantity=payload.quantity,
        note=f"Closed by {user.username}.",
    )
    audit.record(
        db, action="paper_trade.exit", user_id=user.id, entity_type="position",
        entity_id=position.id, after={"exit_price": price}, severity="WARNING",
    )
    db.commit()
    db.refresh(position)
    return _position_out(position)


@router.post("/positions/monitor", dependencies=[Depends(require("trade:manage"))])
def monitor(db: Session = Depends(db_session)) -> dict:
    """Run one monitoring pass over every open position.

    Runs regardless of module activation: an open position is never abandoned.
    """
    engine = PaperTradingEngine(db, RiskEngine(db, get_default_profile(db)))
    results = engine.monitor_positions()
    return {"checked": len(results), "results": results}


@router.get("/history", dependencies=[Depends(require("trade:read"))])
def trade_history(
    db: Session = Depends(db_session),
    params: PageParams = Depends(page_params),
    start: date | None = None,
    end: date | None = None,
) -> Page:
    stmt = select(Position, Instrument).join(
        Instrument, Instrument.id == Position.instrument_id
    )
    count_stmt = select(func.count()).select_from(Position)
    filters = [Position.is_backtest.is_(False), Position.status == PositionStatus.CLOSED]
    if start:
        filters.append(Position.trade_date >= start)
    if end:
        filters.append(Position.trade_date <= end)
    for f in filters:
        stmt = stmt.where(f)
        count_stmt = count_stmt.where(f)

    total = db.scalar(count_stmt) or 0
    rows = db.execute(
        stmt.order_by(Position.exit_time.desc()).offset(params.offset).limit(params.page_size)
    ).all()
    return Page(
        items=[_position_out(p, i) for p, i in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )
