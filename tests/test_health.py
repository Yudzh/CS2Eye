from fastapi.testclient import TestClient

from cs2eye.core.config import settings
from cs2eye.main import create_app


def test_liveness_returns_ok() -> None:
    with TestClient(
        create_app(),
    ) as client:
        response = client.get(
            "/api/v1/health/live",
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": settings.app_name,
    }
