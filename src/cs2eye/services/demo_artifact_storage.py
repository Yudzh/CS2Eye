from dataclasses import dataclass
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


async def save_uploaded_demo_artifact(file: UploadFile) -> StoredDemoArtifact:
    extension = _get_file_extension(file.filename)

    artifact_id = str(uuid4())
    safe_original_filename = Path(file.filename or "demo_artifact").name
    stored_filename = f"{artifact_id}__{safe_original_filename}"

    RAW_DEMOS_DIR.mkdir(parents=True, exist_ok=True)

    destination = RAW_DEMOS_DIR / stored_filename

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

    return StoredDemoArtifact(
        id=artifact_id,
        original_filename=safe_original_filename,
        stored_filename=stored_filename,
        file_path=destination,
        artifact_type=_detect_artifact_type(extension),
    )
