"""API tests against the real application and database.

Marked `integration`: skipped automatically when PostgreSQL is unreachable, so
`pytest` always runs.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture
def ensure_db(db_available):
    if not db_available:
        pytest.skip("PostgreSQL is not reachable.")


# --- Public routes --------------------------------------------------------


def test_root_reports_paper_mode(client):
    body = client.get("/").json()
    assert body["execution_mode"] == "paper"
    assert body["live_order_placement_possible"] is False


def test_safety_endpoint_is_unambiguous(client):
    body = client.get("/api/v1/safety").json()
    assert body["paper_only_build"] is True
    assert body["live_order_placement_possible"] is False
    assert "disabled" in body["note"].lower()


def test_health_reports_dependencies(client, ensure_db):
    body = client.get("/api/v1/health").json()
    assert body["status"] in {"ok", "degraded"}
    assert "postgres" in body["dependencies"]
    assert body["safety"]["live_order_placement_possible"] is False


def test_openapi_schema_is_served(client):
    schema = client.get("/api/v1/openapi.json").json()
    assert schema["info"]["title"]
    assert "/api/v1/auth/login" in schema["paths"]


# --- Authentication -------------------------------------------------------


def test_protected_route_requires_a_token(client):
    response = client.get("/api/v1/dashboard")
    assert response.status_code == 401
    assert response.json()["code"] == "authentication_failed"


def test_invalid_token_is_rejected(client):
    response = client.get(
        "/api/v1/dashboard", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401


def test_login_with_wrong_password_does_not_enumerate_users(client, ensure_db):
    missing = client.post(
        "/api/v1/auth/login", json={"username": "no-such-user", "password": "x"}
    )
    assert missing.status_code == 401
    assert missing.json()["message"] == "Incorrect username or password."


def test_error_responses_have_a_stable_shape(client):
    body = client.get("/api/v1/dashboard").json()
    assert set(body) == {"code", "message", "details"}


# --- Route surface --------------------------------------------------------


def test_no_live_order_route_exists(client):
    """A route that places a real order must not exist anywhere in the API."""
    paths = client.get("/api/v1/openapi.json").json()["paths"]
    forbidden = [
        path
        for path in paths
        if "order" in path and "place" in path or path.endswith("/orders")
    ]
    assert forbidden == [], f"Unexpected order-placement routes: {forbidden}"


def test_broker_router_has_no_execution_endpoint(client):
    paths = client.get("/api/v1/openapi.json").json()["paths"]
    broker_paths = [p for p in paths if p.startswith("/api/v1/broker")]
    assert all("order" not in p for p in broker_paths)
