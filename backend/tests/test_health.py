"""Basic endpoint tests for application and database health checks."""

from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.dependencies import get_db

client = TestClient(app)


def test_health_check_returns_200_and_ok():
    """Verify that GET /health returns HTTP 200 with status 'ok'."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_db_health_check_success():
    """Verify that GET /health/db returns HTTP 200 when database executes successfully."""
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        response = client.get("/health/db")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database": "connected"}
    finally:
        app.dependency_overrides.clear()
