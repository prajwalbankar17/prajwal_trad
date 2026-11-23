"""Shared test fixtures.

Unit tests run with no database. Integration tests (marked `integration`) need
a live PostgreSQL and Redis and are skipped automatically when the database is
unreachable, so `pytest` is always runnable.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from app.core.market_calendar import IST, MARKET_OPEN


def build_session(day: datetime, minutes: int = 375, start_price: float = 100.0,
                  seed: int = 0, drift: float = 0.0) -> list[dict]:
    """Deterministic one-minute candles for a single session."""
    rng = np.random.default_rng(seed)
    start = datetime.combine(day.date(), MARKET_OPEN, tzinfo=IST)
    rows = []
    price = start_price
    for i in range(minutes):
        step = rng.normal(drift, 0.1)
        o = price
        c = o + step
        wick = abs(rng.normal(0, 0.05))
        rows.append(
            {
                "ts": start + timedelta(minutes=i),
                "open": round(o, 2),
                "high": round(max(o, c) + wick, 2),
                "low": round(min(o, c) - wick, 2),
                "close": round(c, 2),
                "volume": int(abs(rng.normal(3000, 800)) + 100),
            }
        )
        price = c
    return rows


@pytest.fixture
def one_session() -> pd.DataFrame:
    return pd.DataFrame(build_session(datetime(2024, 6, 3, tzinfo=IST), seed=7))


@pytest.fixture
def three_sessions() -> pd.DataFrame:
    rows = []
    price = 100.0
    for offset, day in enumerate([3, 4, 5]):
        session = build_session(
            datetime(2024, 6, day, tzinfo=IST), start_price=price, seed=offset + 1
        )
        rows.extend(session)
        price = session[-1]["close"]
    return pd.DataFrame(rows)


@pytest.fixture
def trending_session() -> pd.DataFrame:
    """A session with a clear up-trend, so trend strategies have something to
    find and crossovers actually occur."""
    return pd.DataFrame(
        build_session(datetime(2024, 6, 3, tzinfo=IST), seed=3, drift=0.02)
    )


@pytest.fixture(scope="session")
def db_available() -> bool:
    from sqlalchemy import text

    from app.db.session import engine

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.fixture
def db_session(db_available):
    if not db_available:
        pytest.skip("PostgreSQL is not reachable; skipping integration test.")
    from app.db.session import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
