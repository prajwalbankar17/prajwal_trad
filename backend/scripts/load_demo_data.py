"""Load clearly-labelled SYNTHETIC candles so the platform can be exercised
locally before the real historical database is available.

READ THIS BEFORE USING THE OUTPUT FOR ANYTHING:

    Every row written here has source='MOCK' and every instrument is flagged
    `meta.is_demo = true`. This is a random walk. It is NOT market data. Any
    backtest run against it measures the engine, not a strategy edge, and the
    UI labels these instruments as demo data throughout.

Remove it at any time with:  python -m scripts.load_demo_data --purge
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from sqlalchemy import select, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.market_calendar import IST, MARKET_OPEN, is_trading_day  # noqa: E402
from app.db.session import session_scope  # noqa: E402
from app.models.instrument import Instrument, Sector  # noqa: E402
from app.models.market_data import DataAvailability, DataSource  # noqa: E402

DEMO_SYMBOLS = [
    ("DEMOBANK", "Demo Bank Ltd", "Banking", 1450.0, 0.012),
    ("DEMOTECH", "Demo Technologies Ltd", "Information Technology", 3200.0, 0.014),
    ("DEMOAUTO", "Demo Motors Ltd", "Automobile", 820.0, 0.016),
    ("DEMOPHARMA", "Demo Pharma Ltd", "Pharmaceuticals", 1150.0, 0.011),
    ("DEMOENERGY", "Demo Energy Ltd", "Oil & Gas", 2400.0, 0.013),
]

SESSION_MINUTES = 375


def generate_session(
    rng: np.random.Generator, day, open_price: float, daily_vol: float
) -> list[dict]:
    """One session of 1-minute candles from a random walk with intraday
    seasonality (wider ranges at the open and close)."""
    start = datetime.combine(day, MARKET_OPEN, tzinfo=IST)
    minute_vol = daily_vol / np.sqrt(SESSION_MINUTES)

    shape = 1.0 + 1.2 * np.exp(-np.arange(SESSION_MINUTES) / 40) + 1.0 * np.exp(
        -(SESSION_MINUTES - 1 - np.arange(SESSION_MINUTES)) / 40
    )
    steps = rng.normal(0, minute_vol, SESSION_MINUTES) * shape
    # A gentle intraday drift so trends exist for trend strategies to find.
    steps += rng.normal(0, minute_vol * 0.3) * np.ones(SESSION_MINUTES) / SESSION_MINUTES

    rows: list[dict] = []
    price = open_price
    for i in range(SESSION_MINUTES):
        o = price
        c = o * (1 + steps[i])
        wick = abs(rng.normal(0, minute_vol * 0.6)) * o * shape[i]
        h = max(o, c) + wick
        low = min(o, c) - wick
        volume = int(max(rng.normal(4000, 1500) * shape[i], 100))
        rows.append(
            {
                "ts": start + timedelta(minutes=i),
                "open": round(o, 2),
                "high": round(h, 2),
                "low": round(low, 2),
                "close": round(c, 2),
                "volume": volume,
            }
        )
        price = c
    return rows


def load(days: int, seed: int) -> None:
    rng = np.random.default_rng(seed)

    with session_scope() as db:
        source = db.scalar(select(DataSource).where(DataSource.name == "demo:synthetic"))
        if source is None:
            source = DataSource(
                name="demo:synthetic",
                kind="MOCK",
                description=(
                    "Synthetic random-walk candles for local development. "
                    "NOT market data. Never use for research conclusions."
                ),
                is_trusted=False,
                meta={"generator": "scripts/load_demo_data.py", "seed": seed},
            )
            db.add(source)
            db.flush()

        end = datetime.now(IST).date()
        sessions = []
        cursor = end
        while len(sessions) < days:
            if is_trading_day(cursor):
                sessions.append(cursor)
            cursor -= timedelta(days=1)
        sessions.reverse()

        total_rows = 0
        for symbol, name, sector_name, base_price, vol in DEMO_SYMBOLS:
            sector = db.scalar(select(Sector).where(Sector.name == sector_name))
            instrument = db.scalar(
                select(Instrument).where(Instrument.tradingsymbol == symbol)
            )
            if instrument is None:
                instrument = Instrument(
                    tradingsymbol=symbol,
                    name=name,
                    exchange="NSE",
                    segment="EQUITY",
                    sector_id=sector.id if sector else None,
                    lot_size=1,
                    tick_size=0.05,
                    is_active=True,
                    last_price=base_price,
                    meta={
                        "is_demo": True,
                        "warning": "Synthetic instrument - prices are not real.",
                    },
                )
                db.add(instrument)
                db.flush()

            price = base_price
            rows: list[dict] = []
            for day in sessions:
                gap = rng.normal(0, vol * 0.4)
                price = price * (1 + gap)
                session_rows = generate_session(rng, day, price, vol)
                price = session_rows[-1]["close"]
                rows.extend(session_rows)

            db.execute(
                text(
                    """
                    INSERT INTO intraday_candles
                        (ts, instrument_id, timeframe, open, high, low, close,
                         volume, source, source_id)
                    VALUES
                        (:ts, :instrument_id, '1m', :open, :high, :low, :close,
                         :volume, 'MOCK', :source_id)
                    ON CONFLICT (ts, instrument_id, timeframe) DO NOTHING
                    """
                ),
                [
                    {**row, "instrument_id": instrument.id, "source_id": source.id}
                    for row in rows
                ],
            )

            availability = db.scalar(
                select(DataAvailability).where(
                    DataAvailability.instrument_id == instrument.id,
                    DataAvailability.timeframe == "1m",
                )
            )
            if availability is None:
                availability = DataAvailability(
                    instrument_id=instrument.id, timeframe="1m"
                )
                db.add(availability)
            availability.first_ts = rows[0]["ts"]
            availability.last_ts = rows[-1]["ts"]
            availability.record_count = len(rows)
            availability.completeness_pct = 100
            availability.is_usable = True

            total_rows += len(rows)
            print(f"  {symbol}: {len(rows):,} one-minute candles over {len(sessions)} sessions")

        print(f"\nLoaded {total_rows:,} SYNTHETIC candles (source='MOCK').")
        print("These are NOT real prices. Do not draw research conclusions from them.")


def purge() -> None:
    with session_scope() as db:
        deleted = db.execute(
            text("DELETE FROM intraday_candles WHERE source = 'MOCK'")
        ).rowcount
        ids = db.scalars(
            select(Instrument.id).where(Instrument.tradingsymbol.in_(
                [s[0] for s in DEMO_SYMBOLS]
            ))
        ).all()
        if ids:
            db.execute(
                text("DELETE FROM data_availability WHERE instrument_id = ANY(:ids)"),
                {"ids": list(ids)},
            )
        print(f"Removed {deleted:,} synthetic candle rows.")
        print("Demo instruments were left in place; delete them from the UI if unwanted.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=60, help="Trading sessions to generate")
    parser.add_argument("--seed", type=int, default=20240101)
    parser.add_argument("--purge", action="store_true", help="Delete all synthetic candles")
    args = parser.parse_args()

    if args.purge:
        purge()
        return

    print("=" * 72)
    print("GENERATING SYNTHETIC DEMO DATA - THIS IS NOT MARKET DATA")
    print("=" * 72)
    load(args.days, args.seed)


if __name__ == "__main__":
    main()
