"""AI research routes.

Everything here is read-only research. The AI cannot place, modify or cancel an
order; it has no tools and no database handle. Every call is recorded with its
prompt version, model, token usage and estimated cost.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.client import ClaudeClient, validate_output
from app.ai.prompts import ANALYSE_BACKTEST, BY_NAME, EXPLAIN_SIGNAL
from app.api.deps import current_user, db_session, require
from app.core.exceptions import NotFoundError
from app.models.ai import AIAnalysis, AIUsageLog
from app.models.backtest import BacktestJob, BacktestResult
from app.models.instrument import Instrument
from app.models.signal import TradingSignal
from app.models.strategy import StrategyConfig
from app.services import audit

router = APIRouter(prefix="/ai", tags=["AI Research"])


@router.get("/status")
def ai_status(db: Session = Depends(db_session)) -> dict:
    return ClaudeClient(db).status()


@router.get("/prompts", dependencies=[Depends(require("ai:read"))])
def list_prompts() -> list[dict]:
    return [
        {"name": p.name, "version": p.version, "task": p.task, "system": p.system}
        for p in BY_NAME.values()
    ]


def _analysis_out(analysis: AIAnalysis) -> dict:
    validation = validate_output(analysis)
    return {
        "id": str(analysis.id),
        "task": analysis.task,
        "model": analysis.model,
        "created_at": analysis.created_at.isoformat(),
        "output_text": analysis.output_text,
        "error": analysis.error,
        "is_research_only": True,
        "label": validation["label"],
        "validation": validation,
        "input_context": analysis.input_context,
    }


@router.post("/explain-signal/{signal_id}", dependencies=[Depends(require("ai:run"))])
def explain_signal(
    signal_id: uuid.UUID, user=Depends(current_user), db: Session = Depends(db_session)
) -> dict:
    signal = db.get(TradingSignal, signal_id)
    if signal is None:
        raise NotFoundError("Signal not found.")
    instrument = db.get(Instrument, signal.instrument_id)
    config = (
        db.get(StrategyConfig, signal.strategy_config_id)
        if signal.strategy_config_id
        else None
    )

    conditions = "\n".join(
        f"  - {c['name']}: {'PASS' if c['passed'] else 'FAIL'} - {c['detail']}"
        for c in (signal.conditions or {}).get("checks", [])
    ) or "  (none recorded)"

    context = {
        "symbol": instrument.tradingsymbol if instrument else "unknown",
        "strategy": config.strategy.code if config and config.strategy else "unknown",
        "direction": signal.direction,
        "entry": float(signal.entry_price),
        "stop_loss": float(signal.stop_loss),
        "target": float(signal.target),
        "risk_reward": float(signal.risk_reward) if signal.risk_reward else "n/a",
        "timeframe": signal.timeframe,
        "conditions": conditions,
        "indicators": str((signal.market_context or {}).get("indicators", {})),
    }

    analysis = ClaudeClient(db).run(
        EXPLAIN_SIGNAL, context, user_id=user.id, related_signal_id=signal.id
    )
    audit.record(
        db, action="ai.explain_signal", user_id=user.id, entity_type="signal",
        entity_id=signal.id, commit=True,
    )
    return _analysis_out(analysis)


@router.post("/analyse-backtest/{job_id}", dependencies=[Depends(require("ai:run"))])
def analyse_backtest(
    job_id: uuid.UUID, user=Depends(current_user), db: Session = Depends(db_session)
) -> dict:
    job = db.get(BacktestJob, job_id)
    if job is None:
        raise NotFoundError("Backtest job not found.")

    results = db.scalars(
        select(BacktestResult).where(BacktestResult.job_id == job.id)
    ).all()
    overall = next((r for r in results if r.scope == "OVERALL"), None)
    windows = [r for r in results if r.scope == "WINDOW"]

    def summarise(r: BacktestResult) -> str:
        return (
            f"trades={r.total_trades} win_rate={float(r.win_rate):.2f}% "
            f"gross_profit={float(r.gross_profit):.2f} gross_loss={float(r.gross_loss):.2f} "
            f"charges={float(r.total_charges):.2f} net={float(r.net_profit):.2f} "
            f"profit_factor={r.profit_factor} max_dd_pct={float(r.max_drawdown_pct):.2f} "
            f"sharpe={r.sharpe_ratio}"
        )

    context = {
        "strategy": ", ".join(job.strategy_config_ids),
        "start": job.start_date.isoformat(),
        "end": job.end_date.isoformat(),
        "instrument_count": len(job.instrument_ids),
        "skipped": len((job.data_coverage or {}).get("skipped", [])),
        "metrics": summarise(overall) if overall else "no results",
        "windows": "\n".join(f"{w.window}: {summarise(w)}" for w in windows) or "not split",
    }

    analysis = ClaudeClient(db).run(
        ANALYSE_BACKTEST, context, user_id=user.id, related_backtest_job_id=job.id
    )
    return _analysis_out(analysis)


@router.get("/analyses", dependencies=[Depends(require("ai:read"))])
def list_analyses(limit: int = 50, db: Session = Depends(db_session)) -> list[dict]:
    rows = db.scalars(
        select(AIAnalysis).order_by(AIAnalysis.created_at.desc()).limit(limit)
    ).all()
    return [_analysis_out(a) for a in rows]


@router.get("/usage", dependencies=[Depends(require("ai:read"))])
def usage(db: Session = Depends(db_session)) -> dict:
    totals = db.execute(
        select(
            func.count(AIUsageLog.id),
            func.coalesce(func.sum(AIUsageLog.input_tokens), 0),
            func.coalesce(func.sum(AIUsageLog.output_tokens), 0),
            func.coalesce(func.sum(AIUsageLog.estimated_cost_usd), 0),
        )
    ).one()
    recent = db.scalars(
        select(AIUsageLog).order_by(AIUsageLog.called_at.desc()).limit(25)
    ).all()
    return {
        "total_calls": totals[0],
        "total_input_tokens": int(totals[1]),
        "total_output_tokens": int(totals[2]),
        "total_estimated_cost_usd": round(float(totals[3]), 4),
        "note": "Costs are estimates from published rates, not billing data.",
        "recent": [
            {
                "called_at": u.called_at.isoformat(),
                "model": u.model,
                "input_tokens": u.input_tokens,
                "output_tokens": u.output_tokens,
                "estimated_cost_usd": float(u.estimated_cost_usd),
                "latency_ms": u.latency_ms,
                "success": u.success,
            }
            for u in recent
        ],
    }
