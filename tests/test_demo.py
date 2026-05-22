from uuid import UUID

from fastapi.testclient import TestClient

from cs2eye.core.config import settings
from cs2eye.main import create_app

prefix = "/api/v1/demos"

def test_demos_get_list_returns_ok():
    app = create_app()
    client = TestClient(app)

    resource = client.get(prefix)

    assert resource.status_code == 200
    assert resource.json() == {
        "items": [],
        "total": 0
    }

def test_demos_upload_file_returns_ok():
    app = create_app()
    client = TestClient(app)

    resource = client.post(prefix + "/upload", files={
        "file": (
            "test.dem",
            b"fake demo content",
            "application/octet-stream",
        )
    })

    assert resource.status_code == 200

    payload = resource.json()

    UUID(payload["id"])

    assert payload["filename"] == "test.dem"
    assert payload["status"] == "accepted"

def test_demos_upload_file_non_dem_file():
    app = create_app()
    client = TestClient(app)

    resource = client.post(prefix + "/upload", files={
        "file": (
            "test.bin",
            b"not a dem file",
            "text/plain",
        )
    })

    assert resource.status_code == 400

    assert resource.json() == {
        "detail": "Only .dem file is allowed",
    }

