"""Risk profiles, limits, utilisation, breaches and the kill switch."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_session, require
from app.core.exceptions import NotFoundError
from app.engines.risk import RiskEngine, get_default_profile
from app.models.risk import DailyRiskState, RiskLimitBreach, RiskProfile
from app.schemas.common import Message
from app.services import audit

router = APIRouter(prefix="/risk", tags=["Risk Management"])


def _profile_out(p: RiskProfile) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "description": p.description,
        "is_default": p.is_default,
        "capital": float(p.capital),
        "max_risk_per_trade_pct": float(p.max_risk_per_trade_pct),
        "max_daily_loss_pct": float(p.max_daily_loss_pct),
        "max_open_positions": p.max_open_positions,
        "max_trades_per_day": p.max_trades_per_day,
        "max_total_exposure_pct": float(p.max_total_exposure_pct),
        "max_sector_exposure_pct": float(p.max_sector_exposure_pct),
        "max_capital_utilisation_pct": float(p.max_capital_utilisation_pct),
        "max_position_size_pct": float(p.max_position_size_pct),
        "assumed_leverage": float(p.assumed_leverage),
        "use_broker_margin_when_available": p.use_broker_margin_when_available,
        "kill_switch_enabled": p.kill_switch_enabled,
    }


@router.get("/profiles", dependencies=[Depends(require("risk:read"))])
def list_profiles(db: Session = Depends(db_session)) -> list[dict]:
    return [_profile_out(p) for p in db.scalars(select(RiskProfile)).all()]


class RiskProfileUpdate(BaseModel):
    capital: float | None = Field(None, gt=0)
    max_risk_per_trade_pct: float | None = Field(None, gt=0, le=100)
    max_daily_loss_pct: float | None = Field(None, gt=0, le=100)
    max_open_positions: int | None = Field(None, ge=1, le=200)
    max_trades_per_day: int | None = Field(None, ge=1, le=1000)
    max_total_exposure_pct: float | None = Field(None, gt=0, le=1000)
    max_sector_exposure_pct: float | None = Field(None, gt=0, le=1000)
    max_capital_utilisation_pct: float | None = Field(None, gt=0, le=1000)
    max_position_size_pct: float | None = Field(None, gt=0, le=100)
    assumed_leverage: float | None = Field(None, ge=1, le=20)


@router.patch("/profiles/{profile_id}", dependencies=[Depends(require("risk:write"))])
def update_profile(
    profile_id: uuid.UUID,
    payload: RiskProfileUpdate,
    user=Depends(current_user),
    db: Session = Depends(db_session),
) -> dict:
    profile = db.get(RiskProfile, profile_id)
    if profile is None:
        raise NotFoundError("Risk profile not found.")

    before = _profile_out(profile)
    changes = payload.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(profile, key, value)

    audit.record(
        db, action="risk.limits_changed", user_id=user.id, entity_type="risk_profile",
        entity_id=profile.id, before=before, after=changes, severity="WARNING",
    )
    db.commit()
    db.refresh(profile)
    return _profile_out(profile)


@router.get("/utilisation", dependencies=[Depends(require("risk:read"))])
def utilisation(db: Session = Depends(db_session)) -> dict:
    engine = RiskEngine(db, get_default_profile(db))
    return engine.utilisation()


@router.get("/breaches", dependencies=[Depends(require("risk:read"))])
def breaches(limit: int = 100, db: Session = Depends(db_session)) -> list[dict]:
    """Blocks are as informative as trades: a quiet strategy may simply have
    been stopped by risk all day."""
    rows = db.scalars(
        select(RiskLimitBreach).order_by(RiskLimitBreach.occurred_at.desc()).limit(limit)
    ).all()
    return [
        {
            "id": str(b.id),
            "limit_name": b.limit_name,
            "limit_value": float(b.limit_value) if b.limit_value is not None else None,
            "actual_value": float(b.actual_value) if b.actual_value is not None else None,
            "occurred_at": b.occurred_at.isoformat(),
            "action_taken": b.action_taken,
            "signal_id": str(b.signal_id) if b.signal_id else None,
            "details": b.details,
        }
        for b in rows
    ]


@router.get("/daily-state", dependencies=[Depends(require("risk:read"))])
def daily_states(limit: int = 30, db: Session = Depends(db_session)) -> list[dict]:
    rows = db.scalars(
        select(DailyRiskState).order_by(DailyRiskState.trade_date.desc()).limit(limit)
    ).all()
    return [
        {
            "trade_date": s.trade_date.isoformat(),
            "realised_pnl": float(s.realised_pnl),
            "unrealised_pnl": float(s.unrealised_pnl),
            "charges_paid": float(s.charges_paid),
            "trades_taken": s.trades_taken,
            "open_positions": s.open_positions,
            "deployed_capital": float(s.deployed_capital),
            "trading_halted": s.trading_halted,
            "halt_reason": s.halt_reason,
        }
        for s in rows
    ]


@router.post("/kill-switch", dependencies=[Depends(require("risk:killswitch"))])
def kill_switch(
    active: bool,
    reason: str = "",
    user=Depends(current_user),
    db: Session = Depends(db_session),
) -> Message:
    """Emergency stop: blocks all new entries immediately.

    Open positions keep being monitored and exited - the switch stops new risk,
    it does not walk away from existing risk.
    """
    engine = RiskEngine(db, get_default_profile(db))
    engine.set_kill_switch(active, reason=reason or f"Set by {user.username}.")
    audit.record(
        db, action="risk.kill_switch", user_id=user.id, entity_type="risk_profile",
        after={"active": active, "reason": reason}, severity="CRITICAL", commit=True,
    )
    return Message(
        message=(
            "Kill switch ENGAGED. No new positions will be opened. Open positions "
            "continue to be monitored and exited."
            if active
            else "Kill switch released. New positions may be opened again."
        )
    )
