"""Strategy library, configurations, combinations and module activation."""

from __future__ import annotations

import uuid
from datetime import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_session, require
from app.core.exceptions import NotFoundError, ValidationError
from app.core.market_calendar import now_ist
from app.models.strategy import (
    Strategy,
    StrategyCombination,
    StrategyCombinationLeg,
    StrategyConfig,
    StrategyExecutionLog,
    StrategyVersion,
    TradingModuleState,
)
from app.schemas.common import Message
from app.services import audit
from app.strategies.registry import catalogue

router = APIRouter(tags=["Strategies"])


# --- Library --------------------------------------------------------------


@router.get("/strategies/catalogue", dependencies=[Depends(require("strategy:read"))])
def strategy_catalogue() -> list[dict]:
    """The implemented strategies, straight from the registry."""
    return catalogue()


@router.get("/strategies", dependencies=[Depends(require("strategy:read"))])
def list_strategies(
    db: Session = Depends(db_session),
    category: str | None = None,
    module: str | None = None,
) -> list[dict]:
    stmt = select(Strategy)
    if category:
        stmt = stmt.where(Strategy.category == category.upper())
    if module:
        stmt = stmt.where(Strategy.module == module.upper())
    rows = db.scalars(stmt.order_by(Strategy.category, Strategy.name)).all()

    blocked = {c["code"]: c.get("blocked_reason") for c in catalogue()}
    return [
        {
            "id": str(s.id),
            "code": s.code,
            "name": s.name,
            "category": s.category,
            "module": s.module,
            "description": s.description,
            "is_active": s.is_active,
            "is_research_only": s.is_research_only,
            "default_timeframe": s.default_timeframe,
            "supported_timeframes": s.supported_timeframes,
            "default_parameters": s.default_parameters,
            "parameter_schema": s.parameter_schema,
            "blocked_reason": blocked.get(s.code),
        }
        for s in rows
    ]


@router.post(
    "/strategies/{strategy_id}/activate",
    dependencies=[Depends(require("strategy:activate"))],
)
def set_strategy_active(
    strategy_id: uuid.UUID,
    active: bool,
    user=Depends(current_user),
    db: Session = Depends(db_session),
) -> dict:
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise NotFoundError("Strategy not found.")

    blocked = {c["code"]: c.get("blocked_reason") for c in catalogue()}.get(strategy.code)
    if active and blocked:
        raise ValidationError(
            f"'{strategy.name}' cannot be activated: {blocked}",
            details={"code": strategy.code},
        )

    before = strategy.is_active
    strategy.is_active = active
    audit.record(
        db,
        action="strategy.activate" if active else "strategy.deactivate",
        user_id=user.id,
        entity_type="strategy",
        entity_id=strategy.id,
        before={"is_active": before},
        after={"is_active": active},
        severity="WARNING",
    )
    db.commit()
    return {"id": str(strategy.id), "code": strategy.code, "is_active": strategy.is_active}


# --- Configurations -------------------------------------------------------


class StrategyConfigIn(BaseModel):
    strategy_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=150)
    timeframe: str = "5m"
    parameters: dict = Field(default_factory=dict)
    instrument_ids: list[uuid.UUID] = Field(default_factory=list)
    watchlist_id: uuid.UUID | None = None
    universe_filter: dict = Field(default_factory=dict)
    stop_loss_type: str = "PERCENT"
    stop_loss_value: float = 1.0
    target_type: str = "RR"
    target_value: float = 2.0
    trailing_stop_enabled: bool = False
    trailing_stop_value: float | None = None
    min_risk_reward: float = 1.5
    session_start: time = time(9, 20)
    session_end: time = time(15, 0)
    square_off_time: time = time(15, 15)
    max_signals_per_day: int = 10
    allow_repeat_signal_same_candle: bool = False
    is_enabled: bool = False


def _config_out(c: StrategyConfig) -> dict:
    return {
        "id": str(c.id),
        "name": c.name,
        "strategy": {
            "id": str(c.strategy_id),
            "code": c.strategy.code if c.strategy else None,
            "name": c.strategy.name if c.strategy else None,
            "category": c.strategy.category if c.strategy else None,
        },
        "is_enabled": c.is_enabled,
        "timeframe": c.timeframe,
        "parameters": c.parameters,
        "instrument_ids": c.instrument_ids,
        "watchlist_id": str(c.watchlist_id) if c.watchlist_id else None,
        "stop_loss_type": c.stop_loss_type,
        "stop_loss_value": float(c.stop_loss_value),
        "target_type": c.target_type,
        "target_value": float(c.target_value),
        "trailing_stop_enabled": c.trailing_stop_enabled,
        "trailing_stop_value": (
            float(c.trailing_stop_value) if c.trailing_stop_value is not None else None
        ),
        "min_risk_reward": float(c.min_risk_reward),
        "session_start": c.session_start.isoformat(),
        "session_end": c.session_end.isoformat(),
        "square_off_time": c.square_off_time.isoformat(),
        "max_signals_per_day": c.max_signals_per_day,
        "allow_repeat_signal_same_candle": c.allow_repeat_signal_same_candle,
    }


@router.get("/strategy-configs", dependencies=[Depends(require("strategy:read"))])
def list_configs(db: Session = Depends(db_session), enabled_only: bool = False) -> list[dict]:
    stmt = select(StrategyConfig)
    if enabled_only:
        stmt = stmt.where(StrategyConfig.is_enabled.is_(True))
    return [_config_out(c) for c in db.scalars(stmt.order_by(StrategyConfig.name)).all()]


@router.post(
    "/strategy-configs", status_code=201, dependencies=[Depends(require("strategy:write"))]
)
def create_config(
    payload: StrategyConfigIn,
    user=Depends(current_user),
    db: Session = Depends(db_session),
) -> dict:
    strategy = db.get(Strategy, payload.strategy_id)
    if strategy is None:
        raise NotFoundError("Strategy not found.")
    if payload.timeframe not in (strategy.supported_timeframes or []):
        raise ValidationError(
            f"'{strategy.name}' does not support the {payload.timeframe} timeframe.",
            details={"supported": strategy.supported_timeframes},
        )

    version = db.scalar(
        select(StrategyVersion)
        .where(StrategyVersion.strategy_id == strategy.id)
        .order_by(StrategyVersion.version.desc())
    )
    config = StrategyConfig(
        strategy_id=strategy.id,
        strategy_version_id=version.id if version else None,
        user_id=user.id,
        **payload.model_dump(exclude={"strategy_id"}),
    )
    db.add(config)
    audit.record(
        db, action="strategy_config.create", user_id=user.id,
        entity_type="strategy_config", after={"name": payload.name, "strategy": strategy.code},
    )
    db.commit()
    db.refresh(config)
    return _config_out(config)


@router.patch(
    "/strategy-configs/{config_id}", dependencies=[Depends(require("strategy:write"))]
)
def update_config(
    config_id: uuid.UUID,
    payload: dict,
    user=Depends(current_user),
    db: Session = Depends(db_session),
) -> dict:
    config = db.get(StrategyConfig, config_id)
    if config is None:
        raise NotFoundError("Strategy configuration not found.")

    before = _config_out(config)
    editable = {
        "name", "timeframe", "parameters", "instrument_ids", "watchlist_id",
        "universe_filter", "stop_loss_type", "stop_loss_value", "target_type",
        "target_value", "trailing_stop_enabled", "trailing_stop_value",
        "min_risk_reward", "max_signals_per_day", "allow_repeat_signal_same_candle",
        "is_enabled",
    }
    for key, value in payload.items():
        if key in editable:
            setattr(config, key, value)

    audit.record(
        db, action="strategy_config.update", user_id=user.id,
        entity_type="strategy_config", entity_id=config.id,
        before=before, after=payload,
        severity="WARNING" if "is_enabled" in payload else "INFO",
    )
    db.commit()
    db.refresh(config)
    return _config_out(config)


@router.delete(
    "/strategy-configs/{config_id}", dependencies=[Depends(require("strategy:write"))]
)
def delete_config(
    config_id: uuid.UUID, user=Depends(current_user), db: Session = Depends(db_session)
) -> Message:
    config = db.get(StrategyConfig, config_id)
    if config is None:
        raise NotFoundError("Strategy configuration not found.")
    audit.record(
        db, action="strategy_config.delete", user_id=user.id,
        entity_type="strategy_config", entity_id=config.id, before=_config_out(config),
        severity="WARNING",
    )
    db.delete(config)
    db.commit()
    return Message(message="Strategy configuration deleted.")


@router.get(
    "/strategy-configs/{config_id}/executions",
    dependencies=[Depends(require("strategy:read"))],
)
def config_executions(
    config_id: uuid.UUID, limit: int = 100, db: Session = Depends(db_session)
) -> list[dict]:
    """Why a strategy did or did not fire - the condition-level audit trail."""
    rows = db.scalars(
        select(StrategyExecutionLog)
        .where(StrategyExecutionLog.strategy_config_id == config_id)
        .order_by(StrategyExecutionLog.evaluated_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": str(r.id),
            "evaluated_at": r.evaluated_at.isoformat(),
            "candle_ts": r.candle_ts.isoformat() if r.candle_ts else None,
            "instrument_id": str(r.instrument_id) if r.instrument_id else None,
            "produced_signal": r.produced_signal,
            "conditions": r.conditions,
            "indicators": r.indicator_snapshot,
            "duration_ms": r.duration_ms,
            "error": r.error,
        }
        for r in rows
    ]


# --- Combinations ---------------------------------------------------------


class CombinationLegIn(BaseModel):
    strategy_config_id: uuid.UUID
    weight: float = 1.0
    is_mandatory: bool = False
    role: str | None = None


class CombinationIn(BaseModel):
    name: str
    description: str | None = None
    logic: str = "WEIGHTED"
    min_confirmations: int = 2
    entry_threshold: float = 0.6
    exit_threshold: float = 0.4
    timeframe: str = "5m"
    legs: list[CombinationLegIn] = Field(..., min_length=2, max_length=5)


def _combination_out(c: StrategyCombination) -> dict:
    return {
        "id": str(c.id),
        "name": c.name,
        "description": c.description,
        "is_enabled": c.is_enabled,
        "logic": c.logic,
        "min_confirmations": c.min_confirmations,
        "entry_threshold": float(c.entry_threshold),
        "exit_threshold": float(c.exit_threshold),
        "timeframe": c.timeframe,
        "legs": [
            {
                "id": str(leg.id),
                "strategy_config_id": str(leg.strategy_config_id),
                "strategy": (
                    leg.strategy_config.strategy.code
                    if leg.strategy_config and leg.strategy_config.strategy
                    else None
                ),
                "weight": float(leg.weight),
                "is_mandatory": leg.is_mandatory,
                "role": leg.role,
            }
            for leg in sorted(c.legs, key=lambda item: item.sort_order)
        ],
    }


@router.get("/strategy-combinations", dependencies=[Depends(require("combination:read"))])
def list_combinations(db: Session = Depends(db_session)) -> list[dict]:
    rows = db.scalars(select(StrategyCombination).order_by(StrategyCombination.name)).all()
    return [_combination_out(c) for c in rows]


@router.post(
    "/strategy-combinations",
    status_code=201,
    dependencies=[Depends(require("combination:write"))],
)
def create_combination(
    payload: CombinationIn,
    user=Depends(current_user),
    db: Session = Depends(db_session),
) -> dict:
    combination = StrategyCombination(
        name=payload.name,
        description=payload.description,
        user_id=user.id,
        logic=payload.logic,
        min_confirmations=payload.min_confirmations,
        entry_threshold=payload.entry_threshold,
        exit_threshold=payload.exit_threshold,
        timeframe=payload.timeframe,
    )
    db.add(combination)
    db.flush()

    for order, leg in enumerate(payload.legs):
        if db.get(StrategyConfig, leg.strategy_config_id) is None:
            raise NotFoundError(f"Strategy configuration {leg.strategy_config_id} not found.")
        db.add(
            StrategyCombinationLeg(
                combination_id=combination.id,
                strategy_config_id=leg.strategy_config_id,
                weight=leg.weight,
                is_mandatory=leg.is_mandatory,
                role=leg.role,
                sort_order=order,
            )
        )
    audit.record(
        db, action="combination.create", user_id=user.id,
        entity_type="strategy_combination", entity_id=combination.id,
    )
    db.commit()
    db.refresh(combination)
    return _combination_out(combination)


# --- Module activation ----------------------------------------------------


@router.get("/trading-modules", dependencies=[Depends(require("strategy:read"))])
def list_modules(db: Session = Depends(db_session)) -> list[dict]:
    rows = db.scalars(select(TradingModuleState).order_by(TradingModuleState.module)).all()
    return [
        {
            "module": m.module,
            "is_active": m.is_active,
            "monitor_open_positions": m.monitor_open_positions,
            "deactivated_at": m.deactivated_at.isoformat() if m.deactivated_at else None,
            "reason": m.reason,
            "note": (
                "Deactivating stops new signals and new entries. Open positions "
                "continue to be monitored for stop-loss, target and exits."
            ),
        }
        for m in rows
    ]


@router.post("/trading-modules/{module}", dependencies=[Depends(require("module:activate"))])
def set_module_active(
    module: str,
    active: bool,
    reason: str | None = None,
    user=Depends(current_user),
    db: Session = Depends(db_session),
) -> dict:
    state = db.scalar(
        select(TradingModuleState).where(TradingModuleState.module == module.upper())
    )
    if state is None:
        raise NotFoundError(f"Trading module '{module}' not found.")

    before = state.is_active
    state.is_active = active
    # Never switched off: an open position is monitored to the end regardless.
    state.monitor_open_positions = True
    if not active:
        state.deactivated_at = now_ist()
        state.deactivated_by = user.id
        state.reason = reason or "Deactivated from the UI."

    audit.record(
        db,
        action="module.activate" if active else "module.deactivate",
        user_id=user.id,
        entity_type="trading_module",
        entity_id=state.module,
        before={"is_active": before},
        after={"is_active": active, "reason": reason},
        severity="WARNING",
    )
    db.commit()
    return {
        "module": state.module,
        "is_active": state.is_active,
        "monitor_open_positions": True,
        "message": (
            f"{state.module} module {'activated' if active else 'deactivated'}. "
            + ("" if active else "Open positions continue to be monitored and exited.")
        ),
    }
