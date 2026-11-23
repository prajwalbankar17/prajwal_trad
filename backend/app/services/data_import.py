"""Import job orchestration.

Owns the job row, the resume cursor and the final report. The low-level
streaming and validation live in `app.marketdata.sqlite_importer`.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import JobStatus
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.market_calendar import now_ist
from app.marketdata.sqlite_importer import (
    BatchStats,
    SourceSchema,
    insert_batch,
    inspect_sqlite,
    iter_symbol_rows,
    validate_row,
)
from app.models.instrument import Instrument, SymbolMapping
from app.models.market_data import (
    DataAvailability,
    DataImportFailure,
    DataImportJob,
    DataSource,
)

log = get_logger(__name__)


def list_source_symbols(schema: SourceSchema) -> list[str]:
    """Distinct symbols in the source. For a table-per-symbol layout the table
    names are the symbols."""
    if schema.layout == "table_per_symbol":
        return schema.tables

    conn = sqlite3.connect(f"file:{schema.path}?mode=ro", uri=True)
    try:
        table = schema.tables[0]
        rows = conn.execute(
            f'SELECT DISTINCT "{schema.symbol_column}" FROM "{table}" '
            f'ORDER BY "{schema.symbol_column}"'
        )
        return [r[0] for r in rows if r[0]]
    finally:
        conn.close()


def resolve_instrument(
    db: Session, source: str, source_symbol: str, *, create_missing: bool
) -> Instrument | None:
    """Source symbol -> instrument, via the mapping table first.

    Returns None when the symbol is unknown and `create_missing` is False, so
    the caller records it as a failure instead of inventing an instrument.
    """
    mapping = db.scalar(
        select(SymbolMapping).where(
            SymbolMapping.source == source, SymbolMapping.source_symbol == source_symbol
        )
    )
    if mapping:
        return db.get(Instrument, mapping.instrument_id)

    symbol = source_symbol.strip().upper()
    instrument = db.scalar(
        select(Instrument).where(
            Instrument.tradingsymbol == symbol, Instrument.exchange == "NSE"
        )
    )
    if instrument is None and create_missing:
        instrument = Instrument(
            tradingsymbol=symbol,
            name=symbol,
            exchange="NSE",
            segment="EQUITY",
            is_active=True,
            meta={"created_by": "historical_import", "source": source},
        )
        db.add(instrument)
        db.flush()

    if instrument is not None:
        db.add(
            SymbolMapping(
                instrument_id=instrument.id,
                source=source,
                source_symbol=source_symbol,
                note="Auto-mapped during import.",
            )
        )
        db.flush()
    return instrument


def create_job(
    db: Session,
    *,
    name: str,
    source_path: str,
    timeframe: str = "1m",
    symbols: list[str] | None = None,
    create_missing_instruments: bool = True,
    batch_size: int = 50_000,
) -> DataImportJob:
    path = Path(source_path)
    if not path.exists():
        raise ValidationError(f"SQLite source not found: {source_path}")

    schema = inspect_sqlite(path)
    if len(schema.column_map) < 6:
        raise ValidationError(
            "The source schema could not be mapped to OHLCV columns. "
            "Inspect it first via POST /market-data/imports/inspect.",
            details=schema.as_dict(),
        )

    source = db.scalar(select(DataSource).where(DataSource.uri == str(path)))
    if source is None:
        source = DataSource(
            name=f"sqlite:{path.name}",
            kind="HISTORICAL_IMPORT",
            uri=str(path),
            description="Historical 1-minute equity candles imported from a SQLite file.",
            meta=schema.as_dict(),
        )
        db.add(source)
        db.flush()

    all_symbols = symbols or list_source_symbols(schema)
    job = DataImportJob(
        name=name,
        source_id=source.id,
        source_path=str(path),
        timeframe=timeframe,
        status=JobStatus.QUEUED,
        total_symbols=len(all_symbols),
        cursor={"symbols": all_symbols, "symbol_index": 0, "last_ts": None},
        config={
            "schema": schema.as_dict(),
            "batch_size": batch_size,
            "create_missing_instruments": create_missing_instruments,
        },
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    log.info("import_job_created", job_id=str(job.id), symbols=len(all_symbols))
    return job


def run_job(db: Session, job_id: uuid.UUID, *, max_symbols: int | None = None) -> DataImportJob:
    """Run (or resume) an import job.

    Safe to call repeatedly: it always continues from the stored cursor.
    `max_symbols` bounds one invocation so a worker can yield between chunks.
    """
    job = db.get(DataImportJob, job_id)
    if job is None:
        raise NotFoundError(f"Import job {job_id} not found.")
    if job.status == JobStatus.COMPLETED:
        return job

    # Re-inspect rather than trusting the stored preview: the job row keeps a
    # short summary, and the file must still be readable to resume at all.
    schema = inspect_sqlite(job.source_path)

    batch_size = int(job.config.get("batch_size", 50_000))
    create_missing = bool(job.config.get("create_missing_instruments", True))
    source_name = f"sqlite:{Path(job.source_path).name}"

    cursor = dict(job.cursor)
    symbols: list[str] = cursor.get("symbols", [])
    index = int(cursor.get("symbol_index", 0))

    job.status = JobStatus.RUNNING
    job.started_at = job.started_at or now_ist()
    db.commit()

    conn = sqlite3.connect(f"file:{job.source_path}?mode=ro", uri=True)
    processed_this_run = 0
    try:
        while index < len(symbols):
            if max_symbols is not None and processed_this_run >= max_symbols:
                break

            symbol = symbols[index]
            instrument = resolve_instrument(
                db, source_name, symbol, create_missing=create_missing
            )
            if instrument is None:
                _record_failure(db, job, symbol, "unmapped_symbol")
                index += 1
                processed_this_run += 1
                _save_cursor(db, job, symbols, index, None)
                continue

            # `last_ts` applies only to the symbol we were interrupted inside.
            last_ts = _parse_cursor_ts(cursor.pop("last_ts", None))

            stats = _import_symbol(
                db,
                conn,
                schema,
                job,
                symbol=symbol,
                instrument=instrument,
                after_ts=last_ts,
                batch_size=batch_size,
            )

            _update_availability(db, instrument.id, job.timeframe, stats)
            index += 1
            processed_this_run += 1
            _save_cursor(db, job, symbols, index, None)

        if index >= len(symbols):
            job.status = JobStatus.COMPLETED
            job.finished_at = now_ist()
            job.report = build_report(db, job)
            log.info("import_job_completed", job_id=str(job.id), rows=job.rows_inserted)
        else:
            job.status = JobStatus.PAUSED
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.get(DataImportJob, job_id)
        job.status = JobStatus.FAILED
        job.last_error = f"{type(exc).__name__}: {exc}"
        db.commit()
        log.exception("import_job_failed", job_id=str(job_id))
        raise
    finally:
        conn.close()

    db.refresh(job)
    return job


def _parse_cursor_ts(value) -> datetime | None:
    return datetime.fromisoformat(value) if isinstance(value, str) else None


def _save_cursor(
    db: Session, job: DataImportJob, symbols: list[str], index: int, last_ts: datetime | None
) -> None:
    job.cursor = {
        "symbols": symbols,
        "symbol_index": index,
        "last_ts": last_ts.isoformat() if last_ts else None,
    }
    job.completed_symbols = index
    db.commit()


def _record_failure(db: Session, job: DataImportJob, symbol: str, reason: str, count: int = 1):
    db.add(
        DataImportFailure(job_id=job.id, source_symbol=symbol, reason=reason, row_count=count)
    )
    job.rows_rejected += count
    db.commit()


def _import_symbol(
    db: Session,
    conn: sqlite3.Connection,
    schema: SourceSchema,
    job: DataImportJob,
    *,
    symbol: str,
    instrument: Instrument,
    after_ts: datetime | None,
    batch_size: int,
) -> BatchStats:
    stats = BatchStats()
    buffer: list[dict] = []

    for row in iter_symbol_rows(
        conn, schema, symbol, after_ts=after_ts, fetch_size=batch_size
    ):
        stats.read += 1
        parsed = validate_row(row, stats)
        if parsed is None:
            continue
        buffer.append(parsed)
        stats.last_ts = parsed["ts"]

        if len(buffer) >= batch_size:
            _flush(db, job, buffer, instrument, stats)
            buffer = []

    if buffer:
        _flush(db, job, buffer, instrument, stats)

    for reason, count in stats.rejections.items():
        _record_failure(db, job, symbol, reason, count)

    log.info(
        "import_symbol_done",
        symbol=symbol,
        read=stats.read,
        inserted=stats.inserted,
        duplicates=stats.duplicates,
        rejected=stats.rejected,
    )
    return stats


def _flush(
    db: Session,
    job: DataImportJob,
    buffer: list[dict],
    instrument: Instrument,
    stats: BatchStats,
) -> None:
    inserted = insert_batch(
        db,
        buffer,
        instrument_id=instrument.id,
        timeframe=job.timeframe,
        source_id=job.source_id,
    )
    duplicates = len(buffer) - inserted
    stats.inserted += inserted
    stats.duplicates += max(duplicates, 0)

    job.rows_read += len(buffer)
    job.rows_inserted += inserted
    job.rows_skipped_duplicate += max(duplicates, 0)
    db.commit()


def _update_availability(
    db: Session, instrument_id: uuid.UUID, timeframe: str, stats: BatchStats
) -> None:
    row = db.scalar(
        select(DataAvailability).where(
            DataAvailability.instrument_id == instrument_id,
            DataAvailability.timeframe == timeframe,
        )
    )
    if row is None:
        row = DataAvailability(instrument_id=instrument_id, timeframe=timeframe)
        db.add(row)
    row.record_count = (row.record_count or 0) + stats.inserted
    if stats.last_ts and (row.last_ts is None or stats.last_ts > row.last_ts):
        row.last_ts = stats.last_ts
    row.is_usable = row.record_count > 0
    db.commit()


def build_report(db: Session, job: DataImportJob) -> dict:
    failures = db.scalars(
        select(DataImportFailure).where(DataImportFailure.job_id == job.id)
    ).all()
    by_reason: dict[str, int] = {}
    for f in failures:
        by_reason[f.reason] = by_reason.get(f.reason, 0) + f.row_count

    return {
        "symbols_total": job.total_symbols,
        "symbols_completed": job.completed_symbols,
        "rows_read": job.rows_read,
        "rows_inserted": job.rows_inserted,
        "rows_skipped_duplicate": job.rows_skipped_duplicate,
        "rows_rejected": job.rows_rejected,
        "rejection_reasons": by_reason,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }
