"""Signals: listing, explanation and manual generation."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_session, page_params, require
from app.core.enums import SignalState
from app.core.exceptions import NotFoundError
from app.core.market_calendar import now_ist
from app.engines.risk import RiskEngine, get_default_profile
from app.engines.signal_engine import SignalEngine
from app.models.instrument import Instrument
from app.models.signal import SignalHistory, TradingSignal
from app.models.strategy import StrategyConfig
from app.schemas.common import Message, Page, PageParams
from app.services import audit

router = APIRouter(prefix="/signals", tags=["Signals"])


def _signal_out(s: TradingSignal, instrument: Instrument | None = None) -> dict:
    return {
        "id": str(s.id),
        "instrument_id": str(s.instrument_id),
        "tradingsymbol": instrument.tradingsymbol if instrument else None,
        "exchange": s.exchange,
        "module": s.module,
        "strategy_config_id": str(s.strategy_config_id) if s.strategy_config_id else None,
        "direction": s.direction,
        "entry_price": float(s.entry_price),
        "stop_loss": float(s.stop_loss),
        "target": float(s.target),
        "risk_reward": float(s.risk_reward) if s.risk_reward else None,
        "suggested_quantity": s.suggested_quantity,
        "timeframe": s.timeframe,
        "candle_ts": s.candle_ts.isoformat(),
        "generated_at": s.generated_at.isoformat(),
        "expires_at": s.expires_at.isoformat() if s.expires_at else None,
        "state": s.state,
        "confidence": float(s.confidence) if s.confidence else None,
        "entry_reason": s.entry_reason,
        "rejection_reason": s.rejection_reason,
        "data_source": s.data_source,
        "data_age_seconds": s.data_age_seconds,
        "is_backtest": s.is_backtest,
    }


@router.get("", dependencies=[Depends(require("signal:read"))])
def list_signals(
    db: Session = Depends(db_session),
    params: PageParams = Depends(page_params),
    state: SignalState | None = None,
    instrument_id: uuid.UUID | None = None,
    strategy_config_id: uuid.UUID | None = None,
    direction: str | None = None,
    on_date: date | None = Query(None, alias="date"),
    include_backtest: bool = False,
) -> Page:
    stmt = select(TradingSignal, Instrument).join(
        Instrument, Instrument.id == TradingSignal.instrument_id
    )
    count_stmt = select(func.count()).select_from(TradingSignal)

    filters = []
    if not include_backtest:
        filters.append(TradingSignal.is_backtest.is_(False))
    if state:
        filters.append(TradingSignal.state == str(state))
    if instrument_id:
        filters.append(TradingSignal.instrument_id == instrument_id)
    if strategy_config_id:
        filters.append(TradingSignal.strategy_config_id == strategy_config_id)
    if direction:
        filters.append(TradingSignal.direction == direction.upper())
    if on_date:
        filters.append(func.date(TradingSignal.generated_at) == on_date)

    for f in filters:
        stmt = stmt.where(f)
        count_stmt = count_stmt.where(f)

    total = db.scalar(count_stmt) or 0
    rows = db.execute(
        stmt.order_by(TradingSignal.generated_at.desc())
        .offset(params.offset)
        .limit(params.page_size)
    ).all()
    return Page(
        items=[_signal_out(s, i) for s, i in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/{signal_id}", dependencies=[Depends(require("signal:read"))])
def get_signal(signal_id: uuid.UUID, db: Session = Depends(db_session)) -> dict:
    """Full detail including the condition-by-condition explanation."""
    signal = db.get(TradingSignal, signal_id)
    if signal is None:
        raise NotFoundError("Signal not found.")
    instrument = db.get(Instrument, signal.instrument_id)
    history = db.scalars(
        select(SignalHistory)
        .where(SignalHistory.signal_id == signal.id)
        .order_by(SignalHistory.changed_at)
    ).all()

    return {
        **_signal_out(signal, instrument),
        "conditions": signal.conditions,
        "confirmations": signal.confirmations,
        "market_context": signal.market_context,
        "risk_validation": signal.risk_validation,
        "history": [
            {
                "from_state": h.from_state,
                "to_state": h.to_state,
                "changed_at": h.changed_at.isoformat(),
                "reason": h.reason,
                "actor": h.actor,
            }
            for h in history
        ],
    }


class GenerateRequest(BaseModel):
    strategy_config_id: uuid.UUID
    instrument_id: uuid.UUID


@router.post("/generate", dependencies=[Depends(require("signal:manage"))])
def generate_signal(
    payload: GenerateRequest,
    user=Depends(current_user),
    db: Session = Depends(db_session),
) -> dict:
    """Evaluate one strategy against one instrument right now.

    Honest about freshness: on stored historical data this reports that the
    data is stale rather than producing a signal that looks live.
    """
    config = db.get(StrategyConfig, payload.strategy_config_id)
    if config is None:
        raise NotFoundError("Strategy configuration not found.")
    instrument = db.get(Instrument, payload.instrument_id)
    if instrument is None:
        raise NotFoundError("Instrument not found.")

    engine = SignalEngine(db, RiskEngine(db, get_default_profile(db)))
    result = engine.evaluate(config, instrument, as_of=now_ist())

    audit.record(
        db, action="signal.manual_generate", user_id=user.id,
        entity_type="strategy_config", entity_id=config.id,
        after={"produced": result.produced_signal}, commit=True,
    )
    return {
        "produced_signal": result.produced_signal,
        "reason": result.reason,
        "conditions": result.conditions,
        "signal": _signal_out(result.signal, instrument) if result.signal else None,
    }


@router.post("/{signal_id}/cancel", dependencies=[Depends(require("signal:manage"))])
def cancel_signal(
    signal_id: uuid.UUID,
    reason: str = "Cancelled by user.",
    user=Depends(current_user),
    db: Session = Depends(db_session),
) -> Message:
    signal = db.get(TradingSignal, signal_id)
    if signal is None:
        raise NotFoundError("Signal not found.")
    previous = signal.state
    signal.state = SignalState.CANCELLED
    db.add(
        SignalHistory(
            signal_id=signal.id,
            from_state=previous,
            to_state=SignalState.CANCELLED,
            changed_at=now_ist(),
            reason=reason,
            actor=str(user.username),
        )
    )
    audit.record(
        db, action="signal.cancel", user_id=user.id, entity_type="signal",
        entity_id=signal.id, before={"state": previous}, severity="WARNING",
    )
    db.commit()
    return Message(message="Signal cancelled.")


@router.post("/expire-stale", dependencies=[Depends(require("signal:manage"))])
def expire_stale(db: Session = Depends(db_session)) -> dict:
    count = SignalEngine(db).expire_stale_signals()
    return {"expired": count}
