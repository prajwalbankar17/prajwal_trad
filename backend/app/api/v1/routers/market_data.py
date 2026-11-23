"""Historical candles, imports, data quality and live market status."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_session, page_params, require
from app.core.enums import Timeframe
from app.core.exceptions import NotFoundError
from app.core.market_calendar import market_status, now_ist
from app.db.redis_client import Keys, get_json
from app.db.session import session_scope
from app.marketdata.sqlite_importer import inspect_sqlite
from app.models.instrument import Instrument
from app.models.market_data import DataAvailability, DataImportJob, DataQualityReport
from app.schemas.common import Page, PageParams
from app.services import audit, data_import, data_quality
from app.services import candles as candle_service

router = APIRouter(prefix="/market-data", tags=["Market Data"])


@router.get("/status")
def live_status(db: Session = Depends(db_session)) -> dict:
    """Market status plus live-feed health.

    `feed_connected` is false in this build: no broker WebSocket is running.
    Historical data is never reported as live.
    """
    heartbeat = get_json(Keys.FEED_HEARTBEAT)
    return {
        "market_status": market_status(),
        "server_time_ist": now_ist().isoformat(),
        "feed_connected": bool(heartbeat),
        "last_heartbeat": heartbeat,
        "data_mode": "HISTORICAL",
        "note": (
            "No live broker feed is connected in this build. Every price shown "
            "comes from stored historical or imported data and is labelled as such."
        ),
    }


@router.get("/candles", dependencies=[Depends(require("marketdata:read"))])
def get_candles(
    instrument_id: uuid.UUID,
    timeframe: Timeframe = Timeframe.M5,
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(db_session),
) -> dict:
    instrument = db.get(Instrument, instrument_id)
    if instrument is None:
        raise NotFoundError("Instrument not found.")

    frame = candle_service.load_candles(
        db, instrument_id, str(timeframe), start=start, end=end, limit=limit
    )
    return {
        "instrument": {
            "id": str(instrument.id),
            "tradingsymbol": instrument.tradingsymbol,
            "exchange": instrument.exchange,
            "is_demo": bool((instrument.meta or {}).get("is_demo")),
        },
        "timeframe": str(timeframe),
        "count": len(frame),
        "source": "MOCK" if (instrument.meta or {}).get("is_demo") else "HISTORICAL_IMPORT",
        "candles": [
            {
                "ts": row.ts.isoformat(),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "volume": int(row.volume),
            }
            for row in frame.itertuples()
        ],
    }


@router.get("/availability", dependencies=[Depends(require("marketdata:read"))])
def availability(
    db: Session = Depends(db_session),
    params: PageParams = Depends(page_params),
    usable_only: bool = False,
) -> Page:
    stmt = select(DataAvailability, Instrument).join(
        Instrument, Instrument.id == DataAvailability.instrument_id
    )
    if usable_only:
        stmt = stmt.where(DataAvailability.is_usable.is_(True))
    rows = db.execute(stmt.offset(params.offset).limit(params.page_size)).all()
    total = db.scalar(select(DataAvailability.id).limit(1)) and db.query(
        DataAvailability
    ).count()
    return Page(
        items=[
            {
                "instrument_id": str(a.instrument_id),
                "tradingsymbol": i.tradingsymbol,
                "timeframe": a.timeframe,
                "first_ts": a.first_ts.isoformat() if a.first_ts else None,
                "last_ts": a.last_ts.isoformat() if a.last_ts else None,
                "record_count": a.record_count,
                "completeness_pct": float(a.completeness_pct),
                "is_usable": a.is_usable,
            }
            for a, i in rows
        ],
        total=total or 0,
        page=params.page,
        page_size=params.page_size,
    )


# --- Imports --------------------------------------------------------------


class InspectRequest(BaseModel):
    source_path: str = Field(..., description="Path to the SQLite file on the server")


class ImportCreate(BaseModel):
    name: str
    source_path: str
    timeframe: str = "1m"
    symbols: list[str] | None = None
    create_missing_instruments: bool = True
    batch_size: int = Field(50_000, ge=1_000, le=500_000)


@router.post("/imports/inspect", dependencies=[Depends(require("marketdata:import"))])
def inspect_source(payload: InspectRequest) -> dict:
    """Step 1: read the SQLite schema without importing anything.

    Opens the file read-only and reports the layout, the column mapping it
    would use and sample rows, so the mapping can be confirmed before a
    multi-hour import starts.
    """
    schema = inspect_sqlite(payload.source_path)
    return schema.as_dict()


@router.post("/imports", status_code=201, dependencies=[Depends(require("marketdata:import"))])
def create_import(
    payload: ImportCreate,
    background: BackgroundTasks,
    user=Depends(current_user),
    db: Session = Depends(db_session),
) -> dict:
    job = data_import.create_job(
        db,
        name=payload.name,
        source_path=payload.source_path,
        timeframe=payload.timeframe,
        symbols=payload.symbols,
        create_missing_instruments=payload.create_missing_instruments,
        batch_size=payload.batch_size,
    )
    audit.record(
        db, action="marketdata.import_created", user_id=user.id,
        entity_type="data_import_job", entity_id=job.id,
        after={"source": payload.source_path, "symbols": job.total_symbols}, commit=True,
    )
    background.add_task(_run_import, job.id)
    return _job_out(job)


def _run_import(job_id: uuid.UUID) -> None:
    """Runs outside the request. A long import belongs in a worker; this
    background task is the single-process fallback for local development."""
    with session_scope() as db:
        data_import.run_job(db, job_id)


@router.post("/imports/{job_id}/resume", dependencies=[Depends(require("marketdata:import"))])
def resume_import(
    job_id: uuid.UUID, background: BackgroundTasks, db: Session = Depends(db_session)
) -> dict:
    job = db.get(DataImportJob, job_id)
    if job is None:
        raise NotFoundError("Import job not found.")
    background.add_task(_run_import, job.id)
    return {"message": "Import resumed from its stored cursor.", "job": _job_out(job)}


@router.get("/imports", dependencies=[Depends(require("marketdata:read"))])
def list_imports(db: Session = Depends(db_session)) -> list[dict]:
    rows = db.scalars(
        select(DataImportJob).order_by(DataImportJob.created_at.desc()).limit(100)
    ).all()
    return [_job_out(j) for j in rows]


@router.get("/imports/{job_id}", dependencies=[Depends(require("marketdata:read"))])
def get_import(job_id: uuid.UUID, db: Session = Depends(db_session)) -> dict:
    job = db.get(DataImportJob, job_id)
    if job is None:
        raise NotFoundError("Import job not found.")
    return _job_out(job, include_report=True)


def _job_out(job: DataImportJob, *, include_report: bool = False) -> dict:
    out = {
        "id": str(job.id),
        "name": job.name,
        "status": job.status,
        "source_path": job.source_path,
        "timeframe": job.timeframe,
        "total_symbols": job.total_symbols,
        "completed_symbols": job.completed_symbols,
        "progress_pct": round(
            job.completed_symbols / job.total_symbols * 100, 2
        ) if job.total_symbols else 0.0,
        "rows_read": job.rows_read,
        "rows_inserted": job.rows_inserted,
        "rows_skipped_duplicate": job.rows_skipped_duplicate,
        "rows_rejected": job.rows_rejected,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "last_error": job.last_error,
        "resumable": job.status in {"PAUSED", "FAILED", "QUEUED", "RUNNING"},
    }
    if include_report:
        out["report"] = job.report
        out["cursor"] = {
            "symbol_index": job.cursor.get("symbol_index"),
            "last_ts": job.cursor.get("last_ts"),
        }
    return out


# --- Data quality ---------------------------------------------------------


@router.get("/quality/summary", dependencies=[Depends(require("marketdata:quality"))])
def quality_summary(db: Session = Depends(db_session)) -> dict:
    return data_quality.platform_summary(db)


@router.get("/quality/{instrument_id}", dependencies=[Depends(require("marketdata:quality"))])
def quality_for_instrument(
    instrument_id: uuid.UUID,
    timeframe: str = "1m",
    persist: bool = False,
    db: Session = Depends(db_session),
) -> dict:
    if db.get(Instrument, instrument_id) is None:
        raise NotFoundError("Instrument not found.")
    result = data_quality.generate_report(db, instrument_id, timeframe, persist=persist)
    if isinstance(result, dict):
        return result
    return {
        "id": str(result.id),
        "instrument_id": str(result.instrument_id),
        "timeframe": result.timeframe,
        "generated_at": result.generated_at.isoformat(),
        "total_records": result.total_records,
        "earliest_date": result.earliest_date.isoformat() if result.earliest_date else None,
        "latest_date": result.latest_date.isoformat() if result.latest_date else None,
        "expected_sessions": result.expected_sessions,
        "present_sessions": result.present_sessions,
        "missing_sessions": result.missing_sessions,
        "duplicate_records": result.duplicate_records,
        "invalid_ohlc_records": result.invalid_ohlc_records,
        "completeness_pct": float(result.completeness_pct),
        "missing_ranges": result.missing_ranges,
    }


@router.get("/quality-reports", dependencies=[Depends(require("marketdata:quality"))])
def quality_reports(db: Session = Depends(db_session)) -> list[dict]:
    rows = db.scalars(
        select(DataQualityReport).order_by(DataQualityReport.generated_at.desc()).limit(100)
    ).all()
    return [
        {
            "id": str(r.id),
            "instrument_id": str(r.instrument_id) if r.instrument_id else None,
            "timeframe": r.timeframe,
            "generated_at": r.generated_at.isoformat(),
            "total_records": r.total_records,
            "completeness_pct": float(r.completeness_pct),
            "missing_sessions": r.missing_sessions,
        }
        for r in rows
    ]
