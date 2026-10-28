from fastapi.testclient import TestClient

from app.core.config import settings


def test_root_endpoint(client: TestClient) -> None:
    """Test the root endpoint returns a greeting with application name."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == f"Welcome to {settings.app_name}"


def test_health_endpoint(client: TestClient) -> None:
    """Test top-level /health endpoint returns healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_api_v1_health_endpoint(client: TestClient) -> None:
    """Test API v1 /api/v1/health endpoint returns healthy status."""
    response = client.get(f"{settings.api_v1_prefix}/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
