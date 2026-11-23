"""Indian market session handling in Asia/Kolkata.

Holiday lists are *data*, not code: the table below is a seed for offline work
and is overridden by the `market_holidays` table once populated from the broker
instrument/holiday feed. `is_trading_day()` consults the DB when a session is
passed, and falls back to the seed otherwise - and says which it used.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

PRE_OPEN_START = time(9, 0)
PRE_OPEN_END = time(9, 8)
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
POST_CLOSE_END = time(16, 0)

# Seed list only - verify against the exchange calendar each year.
SEED_HOLIDAYS_2025: set[date] = {
    date(2025, 2, 26), date(2025, 3, 14), date(2025, 3, 31), date(2025, 4, 10),
    date(2025, 4, 14), date(2025, 4, 18), date(2025, 5, 1), date(2025, 8, 15),
    date(2025, 8, 27), date(2025, 10, 2), date(2025, 10, 21), date(2025, 10, 22),
    date(2025, 11, 5), date(2025, 12, 25),
}
SEED_HOLIDAYS_2026: set[date] = {
    date(2026, 1, 26), date(2026, 3, 4), date(2026, 4, 3), date(2026, 5, 1),
    date(2026, 8, 15), date(2026, 10, 2), date(2026, 12, 25),
}
SEED_HOLIDAYS: set[date] = SEED_HOLIDAYS_2025 | SEED_HOLIDAYS_2026


def now_ist() -> datetime:
    return datetime.now(IST)


def to_ist(dt: datetime) -> datetime:
    """Naive datetimes are assumed to already be IST (that is how the historical
    SQLite source stores them); aware ones are converted."""
    return dt.replace(tzinfo=IST) if dt.tzinfo is None else dt.astimezone(IST)


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def is_seed_holiday(d: date) -> bool:
    return d in SEED_HOLIDAYS


def is_trading_day(d: date, *, holidays: set[date] | None = None) -> bool:
    """`holidays` should come from the DB when available; otherwise the seed is
    used and callers that care can check `holiday_source()`."""
    if is_weekend(d):
        return False
    return d not in (holidays if holidays is not None else SEED_HOLIDAYS)


def holiday_source(holidays: set[date] | None) -> str:
    return "database" if holidays is not None else "seed_list"


def session_bounds(d: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(d, MARKET_OPEN, tzinfo=IST),
        datetime.combine(d, MARKET_CLOSE, tzinfo=IST),
    )


def is_market_open(dt: datetime | None = None, *, holidays: set[date] | None = None) -> bool:
    dt = to_ist(dt or now_ist())
    if not is_trading_day(dt.date(), holidays=holidays):
        return False
    return MARKET_OPEN <= dt.time() < MARKET_CLOSE


def market_status(dt: datetime | None = None, *, holidays: set[date] | None = None) -> str:
    from app.core.enums import MarketStatus

    dt = to_ist(dt or now_ist())
    if not is_trading_day(dt.date(), holidays=holidays):
        return MarketStatus.HOLIDAY if not is_weekend(dt.date()) else MarketStatus.CLOSED
    t = dt.time()
    if PRE_OPEN_START <= t < MARKET_OPEN:
        return MarketStatus.PRE_OPEN
    if MARKET_OPEN <= t < MARKET_CLOSE:
        return MarketStatus.OPEN
    if MARKET_CLOSE <= t < POST_CLOSE_END:
        return MarketStatus.POST_CLOSE
    return MarketStatus.CLOSED


def previous_trading_day(d: date, *, holidays: set[date] | None = None) -> date:
    cur = d - timedelta(days=1)
    for _ in range(15):
        if is_trading_day(cur, holidays=holidays):
            return cur
        cur -= timedelta(days=1)
    raise ValueError(f"No trading day found within 15 days before {d}")


def next_trading_day(d: date, *, holidays: set[date] | None = None) -> date:
    cur = d + timedelta(days=1)
    for _ in range(15):
        if is_trading_day(cur, holidays=holidays):
            return cur
        cur += timedelta(days=1)
    raise ValueError(f"No trading day found within 15 days after {d}")


def trading_days_between(
    start: date, end: date, *, holidays: set[date] | None = None
) -> list[date]:
    out, cur = [], start
    while cur <= end:
        if is_trading_day(cur, holidays=holidays):
            out.append(cur)
        cur += timedelta(days=1)
    return out


def minutes_since_open(dt: datetime) -> int:
    dt = to_ist(dt)
    open_dt = datetime.combine(dt.date(), MARKET_OPEN, tzinfo=IST)
    return int((dt - open_dt).total_seconds() // 60)
