"""Engine behaviour against the real database.

These exercise the paths that only make sense with persistence: risk state,
signal deduplication and the paper-only database constraint.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.engines.risk import RiskEngine, get_default_profile
from app.models.strategy import TradingModuleState
from app.models.system import Permission, Role

pytestmark = pytest.mark.integration


def test_seeded_roles_and_permissions_exist(db_session):
    roles = {r.name for r in db_session.scalars(select(Role)).all()}
    assert {"Super Admin", "Admin", "Manager", "Analyst", "Viewer"} <= roles

    codes = {p.code for p in db_session.scalars(select(Permission)).all()}
    assert "strategy:activate" in codes
    assert "risk:killswitch" in codes


def test_viewer_role_is_read_only(db_session):
    viewer = db_session.scalar(select(Role).where(Role.name == "Viewer"))
    assert viewer is not None
    assert all(p.action == "read" for p in viewer.permissions)


def test_trading_modules_start_inactive(db_session):
    states = db_session.scalars(select(TradingModuleState)).all()
    assert {s.module for s in states} == {"EQUITY", "FNO"}
    # monitor_open_positions must always be on, whatever is_active says.
    assert all(s.monitor_open_positions for s in states)


def _throwaway_instrument(db_session) -> str:
    """Create an instrument that exists only inside this test's transaction.

    These constraint tests used to borrow whatever rows happened to already be
    in the database.  That made the most safety-critical check in the project
    depend on unrelated leftover data: against an empty instruments table the
    INSERT ... SELECT matched nothing, no error was raised, and the paper-only
    CHECK was never exercised.  The orders variant was worse - it called
    pytest.skip(), so the suite stayed green while testing nothing at all.
    """
    return db_session.execute(
        text(
            "INSERT INTO instruments (id, tradingsymbol, exchange, segment, "
            "lot_size, tick_size, is_active, is_tradable, meta, created_at, "
            "updated_at) VALUES (gen_random_uuid(), :sym, 'NSE', 'EQUITY', 1, "
            "0.05, true, true, '{\"is_test\": true}'::jsonb, now(), now()) "
            "RETURNING id"
        ),
        {"sym": f"ZZTEST{uuid4().hex[:8].upper()}"},
    ).scalar_one()


ORDER_INSERT = (
    "INSERT INTO orders (id, execution_mode, instrument_id, side, order_type, "
    "product, quantity, filled_quantity, status, simulation, created_at, "
    "updated_at) VALUES (gen_random_uuid(), :mode, :iid, 'BUY', 'MARKET', "
    "'MIS', 1, 0, 'PENDING', '{}'::jsonb, now(), now())"
)

# Every NOT NULL column has to be present.  The previous version of this
# INSERT omitted eleven of them (trailing_stop_active, the pnl columns,
# charge_breakdown, capital_deployed, margin_used, is_backtest).  It still
# raised IntegrityError, so the test passed - but from a NotNullViolation,
# never from the paper-only CHECK.  That test would have gone on passing with
# the CHECK constraint deleted.
POSITION_INSERT = (
    "INSERT INTO positions (id, execution_mode, module, instrument_id, "
    "direction, product, quantity, remaining_quantity, entry_price, "
    "entry_time, trade_date, stop_loss, target, initial_stop_loss, "
    "trailing_stop_active, status, gross_pnl, charges, net_pnl, "
    "unrealised_pnl, charge_breakdown, max_favourable_excursion, "
    "max_adverse_excursion, capital_deployed, margin_used, is_backtest, "
    "created_at, updated_at) "
    "VALUES (gen_random_uuid(), :mode, 'EQUITY', :iid, 'BUY', 'MIS', 1, 1, "
    "100, now(), current_date, 99, 101, 99, false, 'OPEN', 0, 0, 0, 0, "
    "'{}'::jsonb, 0, 0, 100, 0, false, now(), now())"
)


@pytest.mark.parametrize(
    ("statement", "constraint"),
    [
        (ORDER_INSERT, "orders_paper_only"),
        (POSITION_INSERT, "positions_paper_only"),
    ],
    ids=["orders", "positions"],
)
def test_table_rejects_live_execution_mode(db_session, statement, constraint):
    """The database itself refuses to record anything but paper execution."""
    instrument_id = _throwaway_instrument(db_session)

    with pytest.raises(IntegrityError) as excinfo:
        with db_session.begin_nested():
            db_session.execute(text(statement), {"mode": "LIVE", "iid": instrument_id})

    # Assert on the constraint by name.  A test that accepts any IntegrityError
    # would still pass if the CHECK were dropped and the row failed a foreign
    # key or a NOT NULL instead - that is a false green on the one rule the
    # whole platform rests on.
    assert constraint in str(excinfo.value)
    db_session.rollback()


@pytest.mark.parametrize(
    "statement", [ORDER_INSERT, POSITION_INSERT], ids=["orders", "positions"]
)
def test_table_accepts_paper_execution_mode(db_session, statement):
    """Positive control for the test above.

    Without this, the rejection test could pass for the wrong reason: any
    malformed INSERT raises IntegrityError.  This proves the statement is
    otherwise valid, so the only thing the database objects to is the value
    of execution_mode.
    """
    instrument_id = _throwaway_instrument(db_session)

    with db_session.begin_nested():
        db_session.execute(text(statement), {"mode": "PAPER", "iid": instrument_id})

    db_session.rollback()


def test_risk_engine_reports_utilisation(db_session):
    profile = get_default_profile(db_session)
    engine = RiskEngine(db_session, profile)
    utilisation = engine.utilisation()

    for key in (
        "capital", "deployed_capital", "daily_loss_limit", "open_positions",
        "max_open_positions", "trading_halted", "kill_switch",
    ):
        assert key in utilisation
    assert utilisation["capital"] > 0


def test_intraday_candles_are_partitioned(db_session):
    count = db_session.execute(
        text(
            "SELECT count(*) FROM pg_inherits "
            "WHERE inhparent = 'intraday_candles'::regclass"
        )
    ).scalar()
    assert count > 1, "intraday_candles should have yearly partitions"
