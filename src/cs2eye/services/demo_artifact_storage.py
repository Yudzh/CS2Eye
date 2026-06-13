import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

RAW_DEMOS_DIR = Path("storage/demos/raw")

ALLOWED_DEMO_ARTIFACT_EXTENSIONS = [".dem", ".rar", ".zip", ".7z"]


class DemoArtifactStorageError(Exception):
    pass


@dataclass(frozen=True)
class StoredDemoArtifact:
    id: str
    original_filename: str
    stored_filename: str
    file_path: Path
    artifact_type: str


def _get_file_extension(filename: str | None) -> str:
    if not filename:
        raise DemoArtifactStorageError("Uploaded file must have a filename")

    extension = Path(filename).suffix.lower()

    if extension not in ALLOWED_DEMO_ARTIFACT_EXTENSIONS:
        allowed_extensions = ", ".join(sorted(ALLOWED_DEMO_ARTIFACT_EXTENSIONS))
        raise DemoArtifactStorageError(
            f"Only {allowed_extensions} files are allowed"
        )

    return extension


def _detect_artifact_type(extension: str) -> str:
    if extension == ".dem":
        return "demo"

    return "archive"


def _slugify_storage_part(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9а-яё]+", "-", value)
    value = value.strip("-")

    return value or "unknown"


def _build_storage_relative_dir(
        tournament_name: str | None,
        match_date: date | None,
) -> Path:
    if tournament_name is None or match_date is None:
        return Path()

    return Path(match_date.isoformat()) / _slugify_storage_part(tournament_name)


async def save_uploaded_demo_artifact(
        file: UploadFile,
        tournament_name: str | None = None,
        match_date: date | None = None,
) -> StoredDemoArtifact:
    extension = _get_file_extension(file.filename)

    artifact_id = str(uuid4())
    safe_original_filename = Path(file.filename or "demo_artifact").name
    stored_file_name = f"{artifact_id}__{safe_original_filename}"

    relative_dir = _build_storage_relative_dir(
        tournament_name=tournament_name,
        match_date=match_date,
    )

    raw_dir = RAW_DEMOS_DIR / relative_dir
    raw_dir.mkdir(parents=True, exist_ok=True)

    destination = raw_dir / stored_file_name

    try:
        with destination.open("wb") as output_file:
            while chunk := await file.read(1024 * 1024):
                output_file.write(chunk)
    except OSError as error:
        if destination.exists():
            destination.unlink()

        raise DemoArtifactStorageError(
            f"Could not save uploaded demo artifact: {error}"
        ) from error

    stored_filename = (
        stored_file_name
        if relative_dir == Path()
        else (relative_dir / stored_file_name).as_posix()
    )

    return StoredDemoArtifact(
        id=artifact_id,
        original_filename=safe_original_filename,
        stored_filename=stored_filename,
        file_path=destination,
        artifact_type=_detect_artifact_type(extension),
    )