"""Data-quality reporting.

Answers, per instrument and timeframe: how much do we actually have, where are
the holes, and is it safe to backtest on? The point is to make incomplete
coverage visible rather than let a backtest quietly run on 40 of 3,000 stocks.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.market_calendar import now_ist, trading_days_between
from app.models.instrument import MarketHoliday
from app.models.market_data import DataAvailability, DataQualityReport

# Expected 1-minute candles in one NSE equity session (09:15-15:30).
MINUTES_PER_SESSION = 375


def db_holidays(db: Session, exchange: str = "NSE") -> set[date]:
    rows = db.scalars(
        select(MarketHoliday.holiday_date).where(MarketHoliday.exchange == exchange)
    ).all()
    return set(rows)


def instrument_coverage(
    db: Session,
    instrument_id: uuid.UUID,
    timeframe: str = "1m",
    *,
    start: date | None = None,
    end: date | None = None,
) -> dict:
    """Coverage for one instrument. Uses a single grouped query rather than one
    query per day - at 3,000 instruments the difference is hours."""
    params = {"iid": str(instrument_id), "tf": timeframe}
    where_extra = ""
    if start:
        where_extra += " AND ts >= CAST(:start AS timestamptz)"
        params["start"] = start
    if end:
        where_extra += " AND ts < CAST(:end AS timestamptz)"
        params["end"] = end + timedelta(days=1)

    summary = db.execute(
        text(
            f"""
            SELECT COUNT(*)                       AS total,
                   MIN(ts)                        AS first_ts,
                   MAX(ts)                        AS last_ts,
                   COUNT(DISTINCT (ts AT TIME ZONE 'Asia/Kolkata')::date) AS sessions,
                   COUNT(*) FILTER (
                       WHERE high < low
                          OR open > high OR open < low
                          OR close > high OR close < low
                   )                              AS invalid_ohlc,
                   COUNT(*) FILTER (WHERE volume = 0) AS zero_volume
            FROM intraday_candles
            WHERE instrument_id = CAST(:iid AS uuid)
              AND timeframe = CAST(:tf AS varchar) {where_extra}
            """
        ),
        params,
    ).mappings().one()

    first_ts, last_ts = summary["first_ts"], summary["last_ts"]
    if summary["total"] == 0 or first_ts is None:
        return {
            "instrument_id": str(instrument_id),
            "timeframe": timeframe,
            "total_records": 0,
            "earliest_date": None,
            "latest_date": None,
            "expected_sessions": 0,
            "present_sessions": 0,
            "missing_sessions": 0,
            "completeness_pct": 0.0,
            "invalid_ohlc_records": 0,
            "zero_volume_records": 0,
            "is_usable": False,
            "note": "No data for this instrument/timeframe.",
        }

    holidays = db_holidays(db)
    expected_days = trading_days_between(first_ts.date(), last_ts.date(), holidays=holidays)
    present = int(summary["sessions"])
    expected = len(expected_days)

    return {
        "instrument_id": str(instrument_id),
        "timeframe": timeframe,
        "total_records": int(summary["total"]),
        "earliest_date": first_ts.date().isoformat(),
        "latest_date": last_ts.date().isoformat(),
        "expected_sessions": expected,
        "present_sessions": present,
        "missing_sessions": max(expected - present, 0),
        "completeness_pct": round(present / expected * 100, 3) if expected else 0.0,
        "invalid_ohlc_records": int(summary["invalid_ohlc"]),
        "zero_volume_records": int(summary["zero_volume"]),
        "is_usable": expected > 0 and present / expected >= 0.9,
        "holiday_source": "database" if holidays else "seed_list",
    }


def missing_sessions(
    db: Session, instrument_id: uuid.UUID, timeframe: str, start: date, end: date
) -> list[str]:
    """Trading days in [start, end] with no candle at all."""
    rows = db.execute(
        text(
            """
            SELECT DISTINCT (ts AT TIME ZONE 'Asia/Kolkata')::date AS d
            FROM intraday_candles
            WHERE instrument_id = CAST(:iid AS uuid) AND timeframe = CAST(:tf AS varchar)
              AND ts >= CAST(:start AS timestamptz) AND ts < CAST(:end AS timestamptz)
            """
        ),
        {
            "iid": str(instrument_id),
            "tf": timeframe,
            "start": start,
            "end": end + timedelta(days=1),
        },
    ).scalars().all()

    present = set(rows)
    expected = trading_days_between(start, end, holidays=db_holidays(db))
    return [d.isoformat() for d in expected if d not in present]


def thin_sessions(
    db: Session, instrument_id: uuid.UUID, start: date, end: date, *, min_ratio: float = 0.8
) -> list[dict]:
    """Sessions present but with far fewer than 375 one-minute candles - these
    look complete to a naive count and are a common source of silent gaps."""
    rows = db.execute(
        text(
            """
            SELECT (ts AT TIME ZONE 'Asia/Kolkata')::date AS d, COUNT(*) AS n
            FROM intraday_candles
            WHERE instrument_id = CAST(:iid AS uuid) AND timeframe = '1m'
              AND ts >= CAST(:start AS timestamptz) AND ts < CAST(:end AS timestamptz)
            GROUP BY 1
            HAVING COUNT(*) < :threshold
            ORDER BY 1
            """
        ),
        {
            "iid": str(instrument_id),
            "start": start,
            "end": end + timedelta(days=1),
            "threshold": int(MINUTES_PER_SESSION * min_ratio),
        },
    ).mappings().all()
    return [
        {
            "date": r["d"].isoformat(),
            "candles": int(r["n"]),
            "expected": MINUTES_PER_SESSION,
        }
        for r in rows
    ]


def duplicate_count(db: Session, instrument_id: uuid.UUID, timeframe: str) -> int:
    """Always zero while the primary key holds - reported so a schema change
    that loses the constraint is caught rather than assumed impossible."""
    return int(
        db.execute(
            text(
                """
                SELECT COALESCE(SUM(c - 1), 0) FROM (
                    SELECT COUNT(*) AS c
                    FROM intraday_candles
                    WHERE instrument_id = CAST(:iid AS uuid) AND timeframe = CAST(:tf AS varchar)
                    GROUP BY ts
                    HAVING COUNT(*) > 1
                ) d
                """
            ),
            {"iid": str(instrument_id), "tf": timeframe},
        ).scalar()
        or 0
    )


def generate_report(
    db: Session, instrument_id: uuid.UUID, timeframe: str = "1m", *, persist: bool = True
) -> DataQualityReport | dict:
    coverage = instrument_coverage(db, instrument_id, timeframe)
    gaps: list[str] = []
    thin: list[dict] = []

    if coverage["total_records"]:
        start = date.fromisoformat(coverage["earliest_date"])
        end = date.fromisoformat(coverage["latest_date"])
        gaps = missing_sessions(db, instrument_id, timeframe, start, end)
        if timeframe == "1m":
            thin = thin_sessions(db, instrument_id, start, end)

    if not persist:
        return {**coverage, "missing_session_dates": gaps[:200], "thin_sessions": thin[:200]}

    report = DataQualityReport(
        instrument_id=instrument_id,
        timeframe=timeframe,
        generated_at=now_ist(),
        total_records=coverage["total_records"],
        earliest_date=(
            date.fromisoformat(coverage["earliest_date"]) if coverage["earliest_date"] else None
        ),
        latest_date=(
            date.fromisoformat(coverage["latest_date"]) if coverage["latest_date"] else None
        ),
        expected_sessions=coverage["expected_sessions"],
        present_sessions=coverage["present_sessions"],
        missing_sessions=coverage["missing_sessions"],
        duplicate_records=duplicate_count(db, instrument_id, timeframe),
        invalid_ohlc_records=coverage["invalid_ohlc_records"],
        zero_volume_records=coverage["zero_volume_records"],
        completeness_pct=coverage["completeness_pct"],
        missing_ranges={"dates": gaps[:500], "thin_sessions": thin[:500]},
        details=coverage,
    )
    db.add(report)

    availability = db.scalar(
        select(DataAvailability).where(
            DataAvailability.instrument_id == instrument_id,
            DataAvailability.timeframe == timeframe,
        )
    )
    if availability is None:
        availability = DataAvailability(instrument_id=instrument_id, timeframe=timeframe)
        db.add(availability)
    availability.record_count = coverage["total_records"]
    availability.completeness_pct = coverage["completeness_pct"]
    availability.is_usable = coverage["is_usable"]
    db.commit()
    db.refresh(report)
    return report


def platform_summary(db: Session) -> dict:
    """Headline numbers for the Data Quality page."""
    total_rows = db.scalar(select(func.count()).select_from(DataAvailability)) or 0
    usable = (
        db.scalar(
            select(func.count())
            .select_from(DataAvailability)
            .where(DataAvailability.is_usable.is_(True))
        )
        or 0
    )
    candles = db.scalar(text("SELECT COUNT(*) FROM intraday_candles")) or 0
    daily = db.scalar(text("SELECT COUNT(*) FROM daily_candles")) or 0
    span = db.execute(
        text("SELECT MIN(ts) AS first_ts, MAX(ts) AS last_ts FROM intraday_candles")
    ).mappings().one()

    return {
        "instrument_timeframes_tracked": total_rows,
        "usable_instrument_timeframes": usable,
        "intraday_candle_rows": int(candles),
        "daily_candle_rows": int(daily),
        "earliest_intraday_ts": span["first_ts"].isoformat() if span["first_ts"] else None,
        "latest_intraday_ts": span["last_ts"].isoformat() if span["last_ts"] else None,
    }
