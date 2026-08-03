from collections.abc import AsyncIterator
from datetime import date
from io import BytesIO
from pathlib import Path
import tempfile
from typing import cast
import zipfile
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cs2eye.core.config import settings
from cs2eye.db.base import Base
from cs2eye.db.session import get_db_session
from cs2eye.main import create_app
from cs2eye.api.schemas.demos import DemoUploadFileResult
from cs2eye.models.demo_file import DemoFile  # noqa: F401
from cs2eye.services.demo_storage_service import DemoStorageService, make_tournament_slug


@pytest.fixture
async def demo_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[httpx.AsyncClient]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    monkeypatch.setattr(settings, "demo_storage_root", str(tmp_path))
    monkeypatch.setattr(settings, "demo_max_file_size_bytes", 20)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        yield client
    await engine.dispose()


@pytest.mark.parametrize(("name", "slug"), [
    ("IEM Cologne", "iem-cologne"),
    ("BLAST Premier: Fall Final", "blast-premier-fall-final"),
    ("--  IEM---Cologne --", "iem-cologne"),
    ("Café Open", "cafe-open"),
])
def test_tournament_slug(name: str, slug: str) -> None:
    assert make_tournament_slug(name) == slug


async def upload(
    client: httpx.AsyncClient,
    files: list[tuple[str, bytes]],
    *, tournament: str = "IEM Cologne", day: str = "2026-07-28",
) -> httpx.Response:
    return await client.post(
        "/api/v1/demos/upload",
        data={"tournament_name": tournament, "event_type": "online", "match_date": day},
        files=[("files", (name, content, "application/octet-stream")) for name, content in files],
    )


def zip_bytes(entries: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename, content in entries.items():
            archive.writestr(filename, content)
    return output.getvalue()


async def test_rar_archive_member_is_processed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    class FakeRarInfo:
        filename = "match/m80-vs-nip-map1.dem"
        file_size = 4

        def is_dir(self) -> bool:
            return False

        def needs_password(self) -> bool:
            return False

    class FakeRarFile:
        def __init__(self, _: object) -> None:
            pass

        def __enter__(self) -> "FakeRarFile":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def infolist(self) -> list[FakeRarInfo]:
            return [FakeRarInfo()]

        def open(self, _: FakeRarInfo) -> BytesIO:
            return BytesIO(b"demo")

    monkeypatch.setattr(
        "cs2eye.services.demo_storage_service.rarfile.RarFile", FakeRarFile,
    )
    service = DemoStorageService(
        cast(AsyncSession, MagicMock()), tmp_path, 100, archive_max_depth=5,
    )
    service._upload_one = AsyncMock(return_value=DemoUploadFileResult(
        id=1, filename="m80-vs-nip-map1.dem", status="created",
        storage_path="stored.dem", file_size_bytes=4, sha256="0" * 64,
    ))
    rar_upload = tempfile.SpooledTemporaryFile()
    rar_upload.write(b"rar")
    rar_upload.seek(0)
    results = await service._upload_archive(
        "BLAST Bounty", "blast-bounty", "online", date(2026, 7, 21),
        UploadFile(rar_upload, filename="m80-vs-nip.rar"), 1,
    )
    assert [result.filename for result in results] == ["m80-vs-nip-map1.dem"]


async def test_one_demo_is_created(demo_client: httpx.AsyncClient, tmp_path: Path) -> None:
    response = await upload(demo_client, [("map.dem", b"demo")])
    assert response.status_code == 200
    body = response.json()
    assert body["created_count"] == 1
    assert body["files"][0]["status"] == "created"
    assert body["files"][0]["storage_path"] == (
        "demos/tournaments/iem-cologne/online/2026/2026-07-28/map.dem"
    )
    stored = tmp_path / body["files"][0]["storage_path"]
    assert stored.read_bytes() == b"demo"


async def test_multiple_demos_are_created(demo_client: httpx.AsyncClient) -> None:
    body = (await upload(demo_client, [("a.dem", b"a"), ("b.DEM", b"b")])).json()
    assert body["total_files"] == body["created_count"] == 2


async def test_zip_archive_finds_demos_recursively(
    demo_client: httpx.AsyncClient, tmp_path: Path,
) -> None:
    nested = zip_bytes({"deep/map-two.dem": b"two", "ignore.json": b"{}"})
    archive = zip_bytes({
        "folder/map-one.dem": b"one",
        "folder/nested.zip": nested,
        "readme.txt": b"ignored",
    })
    body = (await upload(demo_client, [("match.zip", archive)])).json()
    assert body["created_count"] == 2
    assert sorted(item["filename"] for item in body["files"]) == [
        "map-one.dem", "map-two.dem",
    ]
    for item in body["files"]:
        assert (tmp_path / item["storage_path"]).is_file()


async def test_archive_without_demos_is_failed(demo_client: httpx.AsyncClient) -> None:
    body = (await upload(demo_client, [
        ("documents.zip", zip_bytes({"readme.txt": b"ignored"})),
    ])).json()
    assert body["failed_count"] == 1
    assert "no supported .dem" in body["files"][0]["error"]


async def test_same_content_is_unchanged(demo_client: httpx.AsyncClient) -> None:
    await upload(demo_client, [("map.dem", b"same")])
    body = (await upload(demo_client, [("map.dem", b"same")])).json()
    assert body["unchanged_count"] == 1


async def test_changed_content_replaces_file(
    demo_client: httpx.AsyncClient, tmp_path: Path,
) -> None:
    await upload(demo_client, [("map.dem", b"old")])
    body = (await upload(demo_client, [("map.dem", b"new")])).json()
    assert body["replaced_count"] == 1
    assert (tmp_path / body["files"][0]["storage_path"]).read_bytes() == b"new"


@pytest.mark.parametrize(("filename", "content", "error"), [
    ("bad.zip", b"data", "Only .dem"),
    ("empty.dem", b"", "must not be empty"),
    ("../escape.dem", b"data", "Invalid demo filename"),
    ("too-big.dem", b"123456789012345678901", "size limit"),
])
async def test_invalid_file_is_failed(
    demo_client: httpx.AsyncClient, filename: str, content: bytes, error: str,
) -> None:
    response = await upload(demo_client, [(filename, content)])
    assert response.status_code == 200
    result = response.json()["files"][0]
    assert result["status"] == "failed"
    assert error in result["error"]


async def test_bad_file_does_not_block_good_file(demo_client: httpx.AsyncClient) -> None:
    body = (await upload(demo_client, [("bad.zip", b"bad"), ("good.dem", b"good")])).json()
    assert body["failed_count"] == 1
    assert body["created_count"] == 1


async def test_list_filters_tournament_and_year(demo_client: httpx.AsyncClient) -> None:
    await upload(demo_client, [("a.dem", b"a")], day="2026-07-28")
    await upload(demo_client, [("b.dem", b"b")], day="2025-07-28")
    await upload(demo_client, [("c.dem", b"c")], tournament="Other Cup")
    response = await demo_client.get(
        "/api/v1/demos", params={"tournament_name": "IEM-Cologne", "year": 2026},
    )
    body = response.json()
    assert response.status_code == 200
    assert body["total_files"] == 1
    assert body["dates"][0]["files"][0]["filename"] == "a.dem"


async def test_tournament_options_are_unique_and_sorted(
    demo_client: httpx.AsyncClient,
) -> None:
    await upload(demo_client, [("a.dem", b"a")], tournament="IEM Cologne")
    await upload(demo_client, [("b.dem", b"b")], tournament="Other Cup")
    await upload(
        demo_client, [("c.dem", b"c")], tournament="iem-cologne", day="2026-07-27",
    )

    response = await demo_client.get("/api/v1/demos/tournaments")

    assert response.status_code == 200
    assert response.json() == [
        {"name": "IEM Cologne", "slug": "iem-cologne"},
        {"name": "Other Cup", "slug": "other-cup"},
    ]


async def test_list_groups_and_sorts(demo_client: httpx.AsyncClient) -> None:
    await upload(demo_client, [("z.dem", b"z"), ("a.dem", b"a")], day="2026-07-27")
    await upload(demo_client, [("b.dem", b"b")], day="2026-07-28")
    body = (await demo_client.get(
        "/api/v1/demos", params={"tournament_name": "iem cologne", "year": 2026},
    )).json()
    assert [group["match_date"] for group in body["dates"]] == ["2026-07-28", "2026-07-27"]
    assert [item["filename"] for item in body["dates"][1]["files"]] == ["a.dem", "z.dem"]


async def test_empty_list_is_200(demo_client: httpx.AsyncClient) -> None:
    response = await demo_client.get(
        "/api/v1/demos", params={"tournament_name": "Missing", "year": 2026},
    )
    assert response.status_code == 200
    assert response.json()["dates"] == []


async def test_year_is_validated(demo_client: httpx.AsyncClient) -> None:
    response = await demo_client.get(
        "/api/v1/demos", params={"tournament_name": "IEM", "year": 1999},
    )
    assert response.status_code == 422
