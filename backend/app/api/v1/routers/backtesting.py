"""Backtesting: quick runs, advanced runs, results and comparison."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_session, require
from app.core.exceptions import NotFoundError, ValidationError
from app.db.session import session_scope
from app.engines.backtest import BacktestConfig, BacktestEngine
from app.models.backtest import BacktestJob, BacktestResult, BacktestTrade
from app.models.instrument import Instrument
from app.models.market_data import DataAvailability
from app.models.strategy import StrategyConfig
from app.schemas.common import Message
from app.services import audit

router = APIRouter(prefix="/backtests", tags=["Backtesting"])


class BacktestRequest(BaseModel):
    name: str
    mode: str = Field("QUICK", pattern="^(QUICK|ADVANCED)$")
    strategy_config_ids: list[uuid.UUID] = Field(..., min_length=1)
    instrument_ids: list[uuid.UUID] = Field(..., min_length=1)
    timeframe: str = "5m"
    start_date: date
    end_date: date
    initial_capital: float = 1_000_000
    risk_per_trade_pct: float = 1.0
    include_charges: bool = True
    slippage_pct: float = 0.05
    out_of_sample_pct: float | None = Field(None, ge=0, le=60)


def _job_out(job: BacktestJob) -> dict:
    return {
        "id": str(job.id),
        "name": job.name,
        "mode": job.mode,
        "status": job.status,
        "timeframe": job.timeframe,
        "start_date": job.start_date.isoformat(),
        "end_date": job.end_date.isoformat(),
        "initial_capital": float(job.initial_capital),
        "include_charges": job.include_charges,
        "slippage_pct": float(job.slippage_pct),
        "progress_pct": float(job.progress_pct),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "duration_seconds": job.duration_seconds,
        "data_coverage": job.data_coverage,
        "warnings": job.warnings,
        "error": job.error,
    }


def _result_out(r: BacktestResult) -> dict:
    return {
        "id": str(r.id),
        "scope": r.scope,
        "scope_ref": r.scope_ref,
        "window": r.window,
        "total_trades": r.total_trades,
        "winning_trades": r.winning_trades,
        "losing_trades": r.losing_trades,
        "win_rate": float(r.win_rate),
        "gross_profit": float(r.gross_profit),
        "gross_loss": float(r.gross_loss),
        "total_charges": float(r.total_charges),
        "net_profit": float(r.net_profit),
        "profit_factor": float(r.profit_factor) if r.profit_factor is not None else None,
        "expectancy": float(r.expectancy) if r.expectancy is not None else None,
        "average_profit": float(r.average_profit),
        "average_loss": float(r.average_loss),
        "average_rr": float(r.average_rr) if r.average_rr is not None else None,
        "max_drawdown": float(r.max_drawdown),
        "max_drawdown_pct": float(r.max_drawdown_pct),
        "sharpe_ratio": float(r.sharpe_ratio) if r.sharpe_ratio is not None else None,
        "sortino_ratio": float(r.sortino_ratio) if r.sortino_ratio is not None else None,
        "max_consecutive_wins": r.max_consecutive_wins,
        "max_consecutive_losses": r.max_consecutive_losses,
        "avg_mae": float(r.avg_mae) if r.avg_mae is not None else None,
        "avg_mfe": float(r.avg_mfe) if r.avg_mfe is not None else None,
        "monthly_performance": r.monthly_performance,
        "overfitting_flags": r.overfitting_flags,
        "notes": (r.metrics_extra or {}).get("notes", []),
    }


@router.post("", status_code=201, dependencies=[Depends(require("backtest:run"))])
def create_backtest(
    payload: BacktestRequest,
    background: BackgroundTasks,
    user=Depends(current_user),
    db: Session = Depends(db_session),
) -> dict:
    if payload.end_date <= payload.start_date:
        raise ValidationError("end_date must be after start_date.")

    for config_id in payload.strategy_config_ids:
        if db.get(StrategyConfig, config_id) is None:
            raise NotFoundError(f"Strategy configuration {config_id} not found.")

    # Report coverage up front rather than silently testing on fewer names.
    usable = set(
        db.scalars(
            select(DataAvailability.instrument_id).where(
                DataAvailability.instrument_id.in_(payload.instrument_ids),
                DataAvailability.is_usable.is_(True),
            )
        ).all()
    )
    missing = [str(i) for i in payload.instrument_ids if i not in usable]

    job = BacktestJob(
        name=payload.name,
        user_id=user.id,
        mode=payload.mode,
        strategy_config_ids=[str(c) for c in payload.strategy_config_ids],
        instrument_ids=[str(i) for i in payload.instrument_ids],
        timeframe=payload.timeframe,
        start_date=payload.start_date,
        end_date=payload.end_date,
        initial_capital=payload.initial_capital,
        include_charges=payload.include_charges,
        slippage_pct=payload.slippage_pct,
        validation=(
            {"out_of_sample_pct": payload.out_of_sample_pct}
            if payload.out_of_sample_pct
            else {}
        ),
        config={"risk_per_trade_pct": payload.risk_per_trade_pct},
        warnings=(
            [
                f"{len(missing)} of {len(payload.instrument_ids)} instruments have no "
                "usable data recorded and will likely be skipped."
            ]
            if missing
            else []
        ),
    )
    db.add(job)
    audit.record(
        db, action="backtest.create", user_id=user.id, entity_type="backtest_job",
    )
    db.commit()
    db.refresh(job)

    background.add_task(_run_backtest, job.id, payload.risk_per_trade_pct)
    return _job_out(job)


def _run_backtest(job_id: uuid.UUID, risk_per_trade_pct: float) -> None:
    with session_scope() as db:
        job = db.get(BacktestJob, job_id)
        engine = BacktestEngine(
            db,
            BacktestConfig(
                initial_capital=float(job.initial_capital),
                risk_per_trade_pct=risk_per_trade_pct,
                slippage_pct=float(job.slippage_pct),
                include_charges=job.include_charges,
            ),
        )
        engine.run_job(job)


@router.get("", dependencies=[Depends(require("backtest:read"))])
def list_backtests(limit: int = 50, db: Session = Depends(db_session)) -> list[dict]:
    rows = db.scalars(
        select(BacktestJob).order_by(BacktestJob.created_at.desc()).limit(limit)
    ).all()
    return [_job_out(j) for j in rows]


@router.get("/{job_id}", dependencies=[Depends(require("backtest:read"))])
def get_backtest(job_id: uuid.UUID, db: Session = Depends(db_session)) -> dict:
    job = db.get(BacktestJob, job_id)
    if job is None:
        raise NotFoundError("Backtest job not found.")
    results = db.scalars(
        select(BacktestResult).where(BacktestResult.job_id == job.id)
    ).all()
    overall = next((r for r in results if r.scope == "OVERALL"), None)
    return {
        **_job_out(job),
        "overall": _result_out(overall) if overall else None,
        "equity_curve": overall.equity_curve if overall else [],
        "breakdowns": [_result_out(r) for r in results if r.scope != "OVERALL"],
    }


@router.get("/{job_id}/trades", dependencies=[Depends(require("backtest:read"))])
def backtest_trades(
    job_id: uuid.UUID, limit: int = 500, db: Session = Depends(db_session)
) -> list[dict]:
    rows = db.execute(
        select(BacktestTrade, Instrument)
        .join(Instrument, Instrument.id == BacktestTrade.instrument_id)
        .where(BacktestTrade.job_id == job_id)
        .order_by(BacktestTrade.entry_time)
        .limit(limit)
    ).all()
    return [
        {
            "tradingsymbol": i.tradingsymbol,
            "direction": t.direction,
            "quantity": t.quantity,
            "entry_time": t.entry_time.isoformat(),
            "entry_price": float(t.entry_price),
            "exit_time": t.exit_time.isoformat() if t.exit_time else None,
            "exit_price": float(t.exit_price) if t.exit_price else None,
            "exit_reason": t.exit_reason,
            "stop_loss": float(t.stop_loss),
            "target": float(t.target),
            "gross_pnl": float(t.gross_pnl),
            "charges": float(t.charges),
            "net_pnl": float(t.net_pnl),
            "mae": float(t.mae),
            "mfe": float(t.mfe),
            "conditions": t.conditions,
        }
        for t, i in rows
    ]


@router.get("/compare/", dependencies=[Depends(require("backtest:read"))])
def compare(job_ids: str, db: Session = Depends(db_session)) -> dict:
    """Side-by-side comparison. Flags when trade counts differ enough that the
    comparison is not apples to apples."""
    ids = [uuid.UUID(part.strip()) for part in job_ids.split(",") if part.strip()]
    rows = []
    for job_id in ids:
        job = db.get(BacktestJob, job_id)
        if job is None:
            continue
        overall = db.scalar(
            select(BacktestResult).where(
                BacktestResult.job_id == job_id, BacktestResult.scope == "OVERALL"
            )
        )
        if overall:
            rows.append({"job": _job_out(job), "result": _result_out(overall)})

    caveats = []
    counts = [r["result"]["total_trades"] for r in rows]
    if counts and max(counts) > 3 * max(min(counts), 1):
        caveats.append(
            "Trade counts differ by more than 3x; these runs are not directly "
            "comparable on profit alone."
        )
    if any(r["result"]["total_trades"] < 30 for r in rows):
        caveats.append("At least one run has fewer than 30 trades - too few to rank.")

    return {"runs": rows, "caveats": caveats}


@router.delete("/{job_id}", dependencies=[Depends(require("backtest:delete"))])
def delete_backtest(
    job_id: uuid.UUID, user=Depends(current_user), db: Session = Depends(db_session)
) -> Message:
    job = db.get(BacktestJob, job_id)
    if job is None:
        raise NotFoundError("Backtest job not found.")
    audit.record(
        db, action="backtest.delete", user_id=user.id, entity_type="backtest_job",
        entity_id=job.id, before={"name": job.name}, severity="WARNING",
    )
    db.delete(job)
    db.commit()
    return Message(message="Backtest deleted.")
