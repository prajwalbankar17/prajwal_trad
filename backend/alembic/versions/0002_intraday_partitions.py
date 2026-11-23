"""Create yearly partitions for intraday_candles.

The parent table is declared PARTITION BY RANGE (ts) in the initial migration.
Postgres rejects an insert whose ts falls outside every partition, so a DEFAULT
partition catches anything unexpected instead of failing a 180 GB import - and
`scripts/manage_partitions.py` reports what landed there.

Revision ID: 0002_intraday_partitions
Revises: d6a740e46dc8
"""
from __future__ import annotations

from alembic import op

revision: str = "0002_intraday_partitions"
down_revision: str | None = "d6a740e46dc8"
branch_labels = None
depends_on = None

START_YEAR = 2018
END_YEAR = 2032  # exclusive upper bound of the last yearly partition


def upgrade() -> None:
    for year in range(START_YEAR, END_YEAR):
        op.execute(
            f"CREATE TABLE IF NOT EXISTS intraday_candles_{year} "
            f"PARTITION OF intraday_candles "
            f"FOR VALUES FROM ('{year}-01-01 00:00:00+05:30') "
            f"TO ('{year + 1}-01-01 00:00:00+05:30')"
        )
    op.execute(
        "CREATE TABLE IF NOT EXISTS intraday_candles_default "
        "PARTITION OF intraday_candles DEFAULT"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS intraday_candles_default")
    for year in range(START_YEAR, END_YEAR):
        op.execute(f"DROP TABLE IF EXISTS intraday_candles_{year}")
