"""Portfolios, holdings and snapshots."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_session, require
from app.core.exceptions import NotFoundError
from app.models.instrument import Instrument
from app.models.portfolio import Holding, Portfolio, PortfolioSnapshot

router = APIRouter(prefix="/portfolio", tags=["Portfolio"])


def _portfolio_out(p: Portfolio) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "description": p.description,
        "execution_mode": p.execution_mode,
        "is_default": p.is_default,
        "starting_capital": float(p.starting_capital),
        "current_capital": float(p.current_capital),
        "available_capital": float(p.available_capital),
        "deployed_capital": float(p.deployed_capital),
        "realised_pnl": float(p.realised_pnl),
        "unrealised_pnl": float(p.unrealised_pnl),
        "total_charges": float(p.total_charges),
        "return_pct": round(
            float(p.realised_pnl) / float(p.starting_capital) * 100, 4
        ) if float(p.starting_capital) else 0.0,
    }


@router.get("", dependencies=[Depends(require("portfolio:read"))])
def list_portfolios(user=Depends(current_user), db: Session = Depends(db_session)) -> list[dict]:
    rows = db.scalars(select(Portfolio).where(Portfolio.user_id == user.id)).all()
    return [_portfolio_out(p) for p in rows]


@router.get("/{portfolio_id}/holdings", dependencies=[Depends(require("portfolio:read"))])
def holdings(portfolio_id: uuid.UUID, db: Session = Depends(db_session)) -> list[dict]:
    rows = db.execute(
        select(Holding, Instrument)
        .join(Instrument, Instrument.id == Holding.instrument_id)
        .where(Holding.portfolio_id == portfolio_id)
    ).all()
    return [
        {
            "tradingsymbol": i.tradingsymbol,
            "quantity": h.quantity,
            "average_price": float(h.average_price),
            "last_price": float(h.last_price) if h.last_price else None,
            "unrealised_pnl": float(h.unrealised_pnl),
            "source": h.source,
        }
        for h, i in rows
    ]


@router.get("/{portfolio_id}/snapshots", dependencies=[Depends(require("portfolio:read"))])
def snapshots(
    portfolio_id: uuid.UUID, limit: int = 180, db: Session = Depends(db_session)
) -> list[dict]:
    if db.get(Portfolio, portfolio_id) is None:
        raise NotFoundError("Portfolio not found.")
    rows = db.scalars(
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.portfolio_id == portfolio_id)
        .order_by(PortfolioSnapshot.snapshot_date.desc())
        .limit(limit)
    ).all()
    return [
        {
            "date": s.snapshot_date.isoformat(),
            "equity": float(s.equity),
            "realised_pnl": float(s.realised_pnl),
            "unrealised_pnl": float(s.unrealised_pnl),
            "charges": float(s.charges),
            "open_positions": s.open_positions,
            "drawdown_pct": float(s.drawdown_pct),
        }
        for s in reversed(rows)
    ]
