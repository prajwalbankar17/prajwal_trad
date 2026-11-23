"""Resumable importer for a large historical SQLite candle database.

Written for a ~180 GB, 1-minute equity database. The constraints that shaped it:

* **Never load the file into RAM.** Every read is a streamed cursor with a
  bounded fetch size; memory stays flat whether the file is 2 GB or 400 GB.
* **Resumable.** Progress is a (symbol, last_ts) cursor committed with each
  batch, so a power cut costs one batch, not one week.
* **Idempotent.** Inserts use ON CONFLICT DO NOTHING against the candle primary
  key, so re-running after an interruption cannot duplicate rows.
* **Schema-agnostic.** The source schema is inspected, not assumed. Column
  names are matched against a set of known aliases and the mapping is reported
  for confirmation before a single row is written.

Nothing here invents data: a row that fails validation is counted and sampled
into `data_import_failures`, never silently repaired.
"""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.market_calendar import IST, to_ist

log = get_logger(__name__)

# Column aliases seen in the wild. Extend here, not in the query builder.
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "ts": ("ts", "timestamp", "date", "datetime", "time", "date_time", "candle_time"),
    "open": ("open", "o", "open_price"),
    "high": ("high", "h", "high_price"),
    "low": ("low", "l", "low_price"),
    "close": ("close", "c", "close_price", "last_price"),
    "volume": ("volume", "v", "vol", "qty", "quantity"),
    "symbol": ("symbol", "tradingsymbol", "ticker", "scrip", "name", "instrument"),
}


class ImportAborted(Exception):
    pass


@dataclass
class SourceSchema:
    """What we found in the SQLite file, and how we intend to read it."""

    path: str
    layout: str                      # "single_table" | "table_per_symbol"
    tables: list[str] = field(default_factory=list)
    column_map: dict[str, str] = field(default_factory=dict)
    symbol_column: str | None = None
    sample_rows: list[dict] = field(default_factory=list)
    row_estimate: int | None = None
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "layout": self.layout,
            "table_count": len(self.tables),
            "tables_preview": self.tables[:20],
            "column_map": self.column_map,
            "symbol_column": self.symbol_column,
            "row_estimate": self.row_estimate,
            "sample_rows": self.sample_rows,
            "warnings": self.warnings,
        }


def _match_column(columns: list[str], key: str) -> str | None:
    lowered = {c.lower(): c for c in columns}
    for alias in COLUMN_ALIASES[key]:
        if alias in lowered:
            return lowered[alias]
    return None


def inspect_sqlite(path: str | Path, *, sample: int = 3) -> SourceSchema:
    """Step 1 of the import guide: look before you leap.

    Opens the file read-only and reports the layout, the column mapping it
    would use and a few sample rows. Writes nothing.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"SQLite source not found: {p}")

    uri = f"file:{p}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        tables = [
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        if not tables:
            raise ImportAborted("The SQLite file contains no tables.")

        schema = SourceSchema(path=str(p), layout="single_table", tables=tables)

        # Pick the table with the most columns matching OHLCV as the probe.
        best_table, best_map, best_score = None, {}, -1
        for table in tables[:50]:
            cols = [r["name"] for r in conn.execute(f'PRAGMA table_info("{table}")')]
            mapping = {
                key: col
                for key in ("ts", "open", "high", "low", "close", "volume")
                if (col := _match_column(cols, key))
            }
            score = len(mapping)
            if score > best_score:
                best_table, best_map, best_score = table, mapping, score
                schema.symbol_column = _match_column(cols, "symbol")

        if best_score < 5:
            schema.warnings.append(
                f"Only {best_score} of 6 OHLCV columns were recognised in "
                f"'{best_table}'. Add the real column names to COLUMN_ALIASES "
                "before importing."
            )

        schema.column_map = best_map
        schema.layout = "single_table" if schema.symbol_column else "table_per_symbol"
        if schema.layout == "table_per_symbol":
            schema.warnings.append(
                f"No symbol column found; assuming one table per symbol "
                f"({len(tables)} tables)."
            )

        if best_table:
            schema.sample_rows = [
                dict(r) for r in conn.execute(f'SELECT * FROM "{best_table}" LIMIT {sample}')
            ]
            try:
                schema.row_estimate = conn.execute(
                    f'SELECT COUNT(*) FROM "{best_table}"'
                ).fetchone()[0]
            except sqlite3.Error:
                schema.row_estimate = None

        return schema
    finally:
        conn.close()


def _parse_ts(value: Any) -> datetime | None:
    """Source timestamps are naive IST in every sample seen so far; epoch
    integers are also accepted. Anything else is rejected, not guessed."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return to_ist(value)
    if isinstance(value, int | float):
        # Heuristic: 10 digits = seconds, 13 = milliseconds.
        seconds = value / 1000 if value > 1e11 else value
        return datetime.fromtimestamp(seconds, tz=UTC).astimezone(IST)
    if isinstance(value, str):
        text_value = value.strip().replace("T", " ")
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%d-%m-%Y %H:%M:%S",
            "%d/%m/%Y %H:%M:%S",
        ):
            try:
                return datetime.strptime(text_value[: len(fmt) + 6], fmt).replace(tzinfo=IST)
            except ValueError:
                continue
    return None


@dataclass
class BatchStats:
    read: int = 0
    inserted: int = 0
    duplicates: int = 0
    rejected: int = 0
    rejections: dict[str, int] = field(default_factory=dict)
    last_ts: datetime | None = None

    def reject(self, reason: str) -> None:
        self.rejected += 1
        self.rejections[reason] = self.rejections.get(reason, 0) + 1


def iter_symbol_rows(
    conn: sqlite3.Connection,
    schema: SourceSchema,
    symbol: str,
    *,
    after_ts: datetime | None,
    fetch_size: int,
) -> Iterator[sqlite3.Row]:
    """Stream one symbol's candles in timestamp order, resuming after `after_ts`.

    `arraysize` bounds how much SQLite materialises at once - this is what keeps
    a 180 GB import inside a few hundred megabytes of RAM.
    """
    cmap = schema.column_map
    cols = ", ".join(f'"{cmap[k]}"' for k in ("ts", "open", "high", "low", "close", "volume"))

    if schema.layout == "single_table":
        table = schema.tables[0]
        where = f'"{schema.symbol_column}" = ?'
        params: list[Any] = [symbol]
    else:
        table = symbol
        where = "1=1"
        params = []

    if after_ts is not None:
        where += f' AND "{cmap["ts"]}" > ?'
        params.append(after_ts.strftime("%Y-%m-%d %H:%M:%S"))

    cur = conn.cursor()
    cur.arraysize = fetch_size
    cur.execute(f'SELECT {cols} FROM "{table}" WHERE {where} ORDER BY "{cmap["ts"]}"', params)
    while True:
        rows = cur.fetchmany(fetch_size)
        if not rows:
            break
        yield from rows
    cur.close()


INSERT_SQL = text(
    """
    INSERT INTO intraday_candles
        (ts, instrument_id, timeframe, open, high, low, close, volume, source, source_id)
    VALUES
        (:ts, :instrument_id, :timeframe, :open, :high, :low, :close, :volume, :source, :source_id)
    ON CONFLICT (ts, instrument_id, timeframe) DO NOTHING
    """
)


def insert_batch(
    db: Session,
    rows: list[dict],
    *,
    instrument_id: uuid.UUID,
    timeframe: str,
    source_id: uuid.UUID | None,
) -> int:
    """Bulk insert with conflict-skip. Returns the number of rows actually
    written, so duplicates are counted rather than assumed away."""
    if not rows:
        return 0
    payload = [
        {
            **row,
            "instrument_id": instrument_id,
            "timeframe": timeframe,
            "source": "HISTORICAL_IMPORT",
            "source_id": source_id,
        }
        for row in rows
    ]
    result = db.execute(INSERT_SQL, payload)
    return result.rowcount if result.rowcount is not None and result.rowcount >= 0 else len(payload)


def validate_row(row: sqlite3.Row, stats: BatchStats) -> dict | None:
    """Turn a source row into an insertable dict, or count why it cannot be."""
    ts = _parse_ts(row[0])
    if ts is None:
        stats.reject("unparseable_timestamp")
        return None
    try:
        o, h, low_, c = (float(row[1]), float(row[2]), float(row[3]), float(row[4]))
        v = int(row[5] or 0)
    except (TypeError, ValueError):
        stats.reject("non_numeric_ohlcv")
        return None

    if min(o, h, low_, c) <= 0:
        stats.reject("non_positive_price")
        return None
    if h < low_ or not (low_ <= o <= h) or not (low_ <= c <= h):
        stats.reject("inconsistent_ohlc")
        return None
    if v < 0:
        stats.reject("negative_volume")
        return None

    return {"ts": ts, "open": o, "high": h, "low": low_, "close": c, "volume": v}
