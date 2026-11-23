"""Engine behaviour against the real database.

These exercise the paths that only make sense with persistence: risk state,
signal deduplication and the paper-only database constraint.
"""

from __future__ import annotations

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


def test_orders_table_rejects_live_execution_mode(db_session):
    """The database itself refuses to record a live order."""
    existing = db_session.execute(text("SELECT id FROM orders LIMIT 1")).first()
    if existing is None:
        pytest.skip("No orders to test the constraint against.")

    with pytest.raises(IntegrityError):
        db_session.execute(
            text("UPDATE orders SET execution_mode = 'LIVE' WHERE id = :id"),
            {"id": existing[0]},
        )
        db_session.flush()
    db_session.rollback()


def test_positions_table_rejects_live_execution_mode(db_session):
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO positions (id, execution_mode, module, instrument_id, "
                "direction, product, quantity, remaining_quantity, entry_price, "
                "entry_time, trade_date, stop_loss, initial_stop_loss, target, status, "
                "created_at, updated_at) "
                "SELECT gen_random_uuid(), 'LIVE', 'EQUITY', id, 'BUY', 'MIS', 1, 1, "
                "100, now(), current_date, 99, 99, 101, 'OPEN', now(), now() "
                "FROM instruments LIMIT 1"
            )
        )
        db_session.flush()
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
