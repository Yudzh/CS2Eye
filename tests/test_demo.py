import io
import zipfile
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
    assert payload["status"] == "uploaded"
    assert payload["artifact_type"] == "demo"
    assert payload["stored_filename"].endswith("_test.dem")
    assert payload["file_path"].endswith(payload['stored_filename'])

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
        "detail": "Only .7z, .dem, .rar, .zip files are allowed",
    }

def test_demos_upload_archive_returns_ok():
    app = create_app()
    client = TestClient(app)

    resource = client.post(prefix + "/upload", files={
        "file": (
            "match_demo.rar",
            b"fake archive content",
            "application/octet-stream",
        )
    })

    assert resource.status_code == 200

    payload = resource.json()

    UUID(payload["id"])

    assert payload["filename"] == "match_demo.rar"
    assert payload["status"] == "uploaded"
    assert payload["artifact_type"] == "archive"
    assert payload["stored_filename"].endswith("__match_demo.rar")
    assert payload["file_path"].endswith(payload["stored_filename"])


def test_demos_prepare_uploaded_dem_file_returns_ok():
    app = create_app()
    client = TestClient(app)

    upload_response = client.post(prefix + "/upload", files={
        "file": (
            "test.dem",
            b"fake demo content",
            "application/octet-stream",
        )
    })

    stored_filename = upload_response.json()["stored_filename"]

    resource = client.post(prefix + "/prepare", json={
        "stored_filename": stored_filename,
    })

    assert resource.status_code == 200

    payload = resource.json()

    UUID(payload["artifact_id"])

    assert payload["stored_filename"] == stored_filename
    assert payload["artifact_type"] == "demo"
    assert payload["status"] == "prepared"
    assert len(payload["demo_files"]) == 1
    assert payload["demo_files"][0].endswith(".dem")


def test_demos_prepare_uploaded_zip_archive_returns_ok():
    app = create_app()
    client = TestClient(app)

    archive_buffer = io.BytesIO()

    with zipfile.ZipFile(archive_buffer, mode="w") as archive:
        archive.writestr("map_1.dem", b"fake demo content")
        archive.writestr("readme.txt", b"not a demo")

    upload_response = client.post(prefix + "/upload", files={
        "file": (
            "match_archive.zip",
            archive_buffer.getvalue(),
            "application/zip",
        )
    })

    stored_filename = upload_response.json()["stored_filename"]

    resource = client.post(prefix + "/prepare", json={
        "stored_filename": stored_filename,
    })

    assert resource.status_code == 200

    payload = resource.json()

    UUID(payload["artifact_id"])

    assert payload["stored_filename"] == stored_filename
    assert payload["artifact_type"] == "archive"
    assert payload["status"] == "prepared"
    assert len(payload["demo_files"]) == 1
    assert payload["demo_files"][0].endswith("map_1.dem")


def test_demos_prepare_archive_without_dem_files_returns_bad_request():
    app = create_app()
    client = TestClient(app)

    archive_buffer = io.BytesIO()

    with zipfile.ZipFile(archive_buffer, mode="w") as archive:
        archive.writestr("readme.txt", b"not a demo")

    upload_response = client.post(prefix + "/upload", files={
        "file": (
            "empty_archive.zip",
            archive_buffer.getvalue(),
            "application/zip",
        )
    })

    stored_filename = upload_response.json()["stored_filename"]

    resource = client.post(prefix + "/prepare", json={
        "stored_filename": stored_filename,
    })

    assert resource.status_code == 400

    assert resource.json() == {
        "detail": "No .dem files found in prepared artifact",
    }

