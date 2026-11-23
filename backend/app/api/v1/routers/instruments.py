"""Instruments, sectors and watchlists."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_session, page_params, require
from app.core.exceptions import ConflictError, NotFoundError
from app.core.market_calendar import now_ist
from app.models.instrument import Instrument, Sector, Watchlist, WatchlistItem
from app.schemas.common import Message, Page, PageParams
from app.services import audit

router = APIRouter(tags=["Instruments"])


def _instrument_out(i: Instrument) -> dict:
    return {
        "id": str(i.id),
        "tradingsymbol": i.tradingsymbol,
        "name": i.name,
        "exchange": i.exchange,
        "segment": i.segment,
        "isin": i.isin,
        "instrument_token": i.instrument_token,
        "sector": i.sector.name if i.sector else None,
        "lot_size": i.lot_size,
        "tick_size": float(i.tick_size) if i.tick_size is not None else None,
        "last_price": float(i.last_price) if i.last_price is not None else None,
        "avg_daily_volume": i.avg_daily_volume,
        "is_active": i.is_active,
        "is_tradable": i.is_tradable,
        "is_demo": bool((i.meta or {}).get("is_demo")),
    }


@router.get("/instruments", dependencies=[Depends(require("instrument:read"))])
def list_instruments(
    db: Session = Depends(db_session),
    params: PageParams = Depends(page_params),
    q: str | None = Query(None, description="Search by symbol or company name"),
    exchange: str | None = None,
    segment: str | None = None,
    sector: str | None = None,
    is_active: bool | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    min_volume: int | None = None,
) -> Page:
    stmt = select(Instrument)
    count_stmt = select(func.count()).select_from(Instrument)

    filters = []
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(
            or_(Instrument.tradingsymbol.ilike(pattern), Instrument.name.ilike(pattern))
        )
    if exchange:
        filters.append(Instrument.exchange == exchange.upper())
    if segment:
        filters.append(Instrument.segment == segment.upper())
    if is_active is not None:
        filters.append(Instrument.is_active.is_(is_active))
    if min_price is not None:
        filters.append(Instrument.last_price >= min_price)
    if max_price is not None:
        filters.append(Instrument.last_price <= max_price)
    if min_volume is not None:
        filters.append(Instrument.avg_daily_volume >= min_volume)
    if sector:
        stmt = stmt.join(Sector, isouter=True)
        count_stmt = count_stmt.join(Sector, Instrument.sector_id == Sector.id, isouter=True)
        filters.append(Sector.name == sector)

    for f in filters:
        stmt = stmt.where(f)
        count_stmt = count_stmt.where(f)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Instrument.tradingsymbol).offset(params.offset).limit(params.page_size)
    ).all()
    return Page(
        items=[_instrument_out(i) for i in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/instruments/{instrument_id}", dependencies=[Depends(require("instrument:read"))])
def get_instrument(instrument_id: uuid.UUID, db: Session = Depends(db_session)) -> dict:
    instrument = db.get(Instrument, instrument_id)
    if instrument is None:
        raise NotFoundError("Instrument not found.")
    return _instrument_out(instrument)


@router.get("/sectors", dependencies=[Depends(require("instrument:read"))])
def list_sectors(db: Session = Depends(db_session)) -> list[dict]:
    rows = db.scalars(select(Sector).order_by(Sector.name)).all()
    return [{"id": str(s.id), "name": s.name, "industry": s.industry} for s in rows]


# --- Watchlists -----------------------------------------------------------


class WatchlistCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = None
    color: str | None = None


class WatchlistItemAdd(BaseModel):
    instrument_id: uuid.UUID
    note: str | None = None


def _watchlist_out(w: Watchlist) -> dict:
    return {
        "id": str(w.id),
        "name": w.name,
        "description": w.description,
        "color": w.color,
        "is_default": w.is_default,
        "item_count": len(w.items),
        "items": [
            {
                "id": str(item.id),
                "instrument": _instrument_out(item.instrument),
                "note": item.note,
                "sort_order": item.sort_order,
            }
            for item in sorted(w.items, key=lambda x: x.sort_order)
        ],
    }


@router.get("/watchlists", dependencies=[Depends(require("watchlist:read"))])
def list_watchlists(user=Depends(current_user), db: Session = Depends(db_session)) -> list[dict]:
    rows = db.scalars(
        select(Watchlist).where(Watchlist.user_id == user.id).order_by(Watchlist.name)
    ).all()
    return [_watchlist_out(w) for w in rows]


@router.post("/watchlists", status_code=201, dependencies=[Depends(require("watchlist:write"))])
def create_watchlist(
    payload: WatchlistCreate,
    user=Depends(current_user),
    db: Session = Depends(db_session),
) -> dict:
    if db.scalar(
        select(Watchlist).where(Watchlist.user_id == user.id, Watchlist.name == payload.name)
    ):
        raise ConflictError(f"You already have a watchlist named '{payload.name}'.")
    watchlist = Watchlist(
        user_id=user.id,
        name=payload.name,
        description=payload.description,
        color=payload.color,
    )
    db.add(watchlist)
    audit.record(db, action="watchlist.create", user_id=user.id, entity_type="watchlist")
    db.commit()
    db.refresh(watchlist)
    return _watchlist_out(watchlist)


@router.post(
    "/watchlists/{watchlist_id}/items",
    status_code=201,
    dependencies=[Depends(require("watchlist:write"))],
)
def add_watchlist_item(
    watchlist_id: uuid.UUID,
    payload: WatchlistItemAdd,
    user=Depends(current_user),
    db: Session = Depends(db_session),
) -> dict:
    watchlist = db.get(Watchlist, watchlist_id)
    if watchlist is None or watchlist.user_id != user.id:
        raise NotFoundError("Watchlist not found.")
    if db.get(Instrument, payload.instrument_id) is None:
        raise NotFoundError("Instrument not found.")
    if any(item.instrument_id == payload.instrument_id for item in watchlist.items):
        raise ConflictError("That instrument is already in this watchlist.")

    db.add(
        WatchlistItem(
            watchlist_id=watchlist.id,
            instrument_id=payload.instrument_id,
            note=payload.note,
            sort_order=len(watchlist.items),
            added_at=now_ist(),
        )
    )
    db.commit()
    db.refresh(watchlist)
    return _watchlist_out(watchlist)


@router.delete(
    "/watchlists/{watchlist_id}/items/{item_id}",
    dependencies=[Depends(require("watchlist:write"))],
)
def remove_watchlist_item(
    watchlist_id: uuid.UUID,
    item_id: uuid.UUID,
    user=Depends(current_user),
    db: Session = Depends(db_session),
) -> Message:
    watchlist = db.get(Watchlist, watchlist_id)
    if watchlist is None or watchlist.user_id != user.id:
        raise NotFoundError("Watchlist not found.")
    item = db.get(WatchlistItem, item_id)
    if item is None or item.watchlist_id != watchlist.id:
        raise NotFoundError("Watchlist item not found.")
    db.delete(item)
    db.commit()
    return Message(message="Removed from watchlist.")


@router.delete("/watchlists/{watchlist_id}", dependencies=[Depends(require("watchlist:write"))])
def delete_watchlist(
    watchlist_id: uuid.UUID,
    user=Depends(current_user),
    db: Session = Depends(db_session),
) -> Message:
    watchlist = db.get(Watchlist, watchlist_id)
    if watchlist is None or watchlist.user_id != user.id:
        raise NotFoundError("Watchlist not found.")
    audit.record(
        db, action="watchlist.delete", user_id=user.id,
        entity_type="watchlist", entity_id=watchlist.id,
        before={"name": watchlist.name, "items": len(watchlist.items)},
    )
    db.delete(watchlist)
    db.commit()
    return Message(message="Watchlist deleted.")
