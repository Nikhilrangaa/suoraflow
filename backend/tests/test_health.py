"""
test_health.py — Tests for GET /health.

Designed to run via:
  docker compose run --rm backend pytest -q

The backend container has live DB + Redis, so this is an integration test
that exercises real reachability checks.
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200():
    response = client.get("/health")
    assert response.status_code == 200


def test_health_schema():
    response = client.get("/health")
    data = response.json()
    assert "status" in data
    assert "db" in data
    assert "redis" in data


def test_health_status_ok_when_services_up():
    """When DB and Redis are reachable (docker compose context), status must be 'ok'."""
    response = client.get("/health")
    data = response.json()
    assert data["db"] == "ok", f"DB not reachable: {data}"
    assert data["redis"] == "ok", f"Redis not reachable: {data}"
    assert data["status"] == "ok"
