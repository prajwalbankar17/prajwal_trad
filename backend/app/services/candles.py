"""Candle access.

The single place the rest of the platform reads price history from. It knows
which physical table holds which timeframe, and resamples minutes when a
higher intraday timeframe is not stored.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.enums import TIMEFRAME_MINUTES, Timeframe
from app.core.exceptions import ValidationError
from app.core.market_calendar import IST, to_ist
from app.marketdata.aggregation import Candle, candles_to_frame, resample

DAILY_TIMEFRAMES = {Timeframe.D1, Timeframe.W1, Timeframe.MO1}

# Parameters are cast explicitly: PostgreSQL cannot infer the type of a bare
# NULL placeholder, and these queries pass NULL for an absent date bound.
_INTRADAY_SQL = text(
    """
    SELECT ts, open, high, low, close, volume
    FROM intraday_candles
    WHERE instrument_id = CAST(:iid AS uuid)
      AND timeframe = CAST(:tf AS varchar)
      AND (CAST(:start AS timestamptz) IS NULL OR ts >= CAST(:start AS timestamptz))
      AND (CAST(:end AS timestamptz) IS NULL OR ts <= CAST(:end AS timestamptz))
    ORDER BY ts
    """
)

_INTRADAY_TAIL_SQL = text(
    """
    SELECT ts, open, high, low, close, volume FROM (
        SELECT ts, open, high, low, close, volume
        FROM intraday_candles
        WHERE instrument_id = CAST(:iid AS uuid)
          AND timeframe = CAST(:tf AS varchar)
          AND (CAST(:end AS timestamptz) IS NULL OR ts <= CAST(:end AS timestamptz))
        ORDER BY ts DESC
        LIMIT :limit
    ) t ORDER BY ts
    """
)

_DAILY_SQL = text(
    """
    SELECT ts, open, high, low, close, volume
    FROM daily_candles
    WHERE instrument_id = CAST(:iid AS uuid)
      AND timeframe = CAST(:tf AS varchar)
      AND (CAST(:start AS timestamptz) IS NULL OR ts >= CAST(:start AS timestamptz))
      AND (CAST(:end AS timestamptz) IS NULL OR ts <= CAST(:end AS timestamptz))
    ORDER BY ts
    """
)


def _to_frame(rows) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
    frame = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True).dt.tz_convert(IST)
    for col in ("open", "high", "low", "close"):
        frame[col] = frame[col].astype(float)
    frame["volume"] = frame["volume"].astype("int64")
    return frame.reset_index(drop=True)


def load_candles(
    db: Session,
    instrument_id: uuid.UUID,
    timeframe: str,
    *,
    start: datetime | date | None = None,
    end: datetime | date | None = None,
    limit: int | None = None,
) -> pd.DataFrame:
    """Load candles for one instrument.

    Minute data is stored once at 1m; anything above it (and below daily) is
    resampled on read, so a 15m request never silently returns stale
    pre-aggregated rows.
    """
    start_dt = _as_datetime(start, end_of_day=False)
    end_dt = _as_datetime(end, end_of_day=True)

    if timeframe in DAILY_TIMEFRAMES:
        rows = db.execute(
            _DAILY_SQL,
            {"iid": str(instrument_id), "tf": str(timeframe), "start": start_dt, "end": end_dt},
        ).all()
        return _to_frame(rows)

    if timeframe not in TIMEFRAME_MINUTES:
        raise ValidationError(f"Unsupported timeframe: {timeframe}")

    minutes = TIMEFRAME_MINUTES[timeframe]
    if limit is not None and start_dt is None:
        # Pull enough 1m rows to build `limit` target candles, plus headroom
        # for partial sessions.
        tail = limit * minutes + minutes * 5
        rows = db.execute(
            _INTRADAY_TAIL_SQL,
            {"iid": str(instrument_id), "tf": str(Timeframe.M1), "end": end_dt, "limit": tail},
        ).all()
    else:
        rows = db.execute(
            _INTRADAY_SQL,
            {
                "iid": str(instrument_id),
                "tf": str(Timeframe.M1),
                "start": start_dt,
                "end": end_dt,
            },
        ).all()

    frame = _to_frame(rows)
    if frame.empty or timeframe == Timeframe.M1:
        return frame.tail(limit).reset_index(drop=True) if limit else frame

    candles = [
        Candle(
            ts=row.ts,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=int(row.volume),
        )
        for row in frame.itertuples()
    ]
    aggregated = resample(candles, timeframe, include_partial=False)
    out = candles_to_frame(aggregated)
    return out.tail(limit).reset_index(drop=True) if limit else out


def _as_datetime(value: datetime | date | None, *, end_of_day: bool) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return to_ist(value)
    moment = datetime.combine(value, datetime.min.time(), tzinfo=IST)
    return moment + timedelta(days=1) - timedelta(microseconds=1) if end_of_day else moment


def latest_candle(db: Session, instrument_id: uuid.UUID, timeframe: str = "1m") -> dict | None:
    frame = load_candles(db, instrument_id, timeframe, limit=1)
    if frame.empty:
        return None
    row = frame.iloc[-1]
    return {
        "ts": row["ts"].isoformat(),
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "volume": int(row["volume"]),
    }


def data_age_seconds(db: Session, instrument_id: uuid.UUID, now: datetime) -> int | None:
    """How stale the newest candle is. The signal engine refuses to act on data
    older than its freshness threshold rather than treating it as live."""
    latest = latest_candle(db, instrument_id)
    if latest is None:
        return None
    ts = to_ist(datetime.fromisoformat(latest["ts"]))
    return int((to_ist(now) - ts).total_seconds())
