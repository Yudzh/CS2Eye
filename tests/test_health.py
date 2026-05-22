from fastapi.testclient import TestClient


from cs2eye.core.config import settings
from cs2eye.main import create_app


def test_health_returns_ok():
    app = create_app()
    client = TestClient(app)

    resource = client.get("/health")

    assert resource.status_code == 200
    assert resource.json() == {
        "status": "ok",
        "service": settings.app_name}