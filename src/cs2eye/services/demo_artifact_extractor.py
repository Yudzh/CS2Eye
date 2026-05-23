from dataclasses import dataclass
from pathlib import Path
from uuid import UUID
import shutil
import zipfile

import py7zr
import rarfile


RAW_DEMOS_DIR = Path("storage/demos/raw")
PREPARED_DEMOS_DIR = Path("storage/demos/prepared")

ARCHIVE_EXTENSIONS = {".rar", ".zip", ".7z"}


class DemoArtifactExtractionError(Exception):
    pass


@dataclass(frozen=True)
class PreparedDemoArtifact:
    artifact_id: str
    stored_filename: str
    artifact_type: str
    prepared_dir: Path
    demo_files: list[Path]


def _get_artifact_id_from_stored_filename(stored_filename: str) -> str:
    artifact_id = stored_filename.split("__", 1)[0]

    try:
        UUID(artifact_id)
    except ValueError as error:
        raise DemoArtifactExtractionError(
            "Stored filename must start with artifact UUID"
        ) from error

    return artifact_id


def _resolve_raw_artifact_path(stored_filename: str) -> Path:
    if Path(stored_filename).name != stored_filename:
        raise DemoArtifactExtractionError("Stored filename must not contain path parts")

    artifact_path = RAW_DEMOS_DIR / stored_filename

    if not artifact_path.exists():
        raise DemoArtifactExtractionError("Uploaded demo artifact was not found")

    if not artifact_path.is_file():
        raise DemoArtifactExtractionError("Uploaded demo artifact is not a file")

    return artifact_path


def _safe_output_path(output_dir: Path, archive_member_name: str) -> Path:
    normalized_name = archive_member_name.replace("\\", "/")
    member_path = Path(normalized_name)

    if member_path.is_absolute() or ".." in member_path.parts:
        raise DemoArtifactExtractionError(
            f"Unsafe archive member path: {archive_member_name}"
        )

    target_path = (output_dir / member_path).resolve()
    output_root = output_dir.resolve()

    try:
        target_path.relative_to(output_root)
    except ValueError as error:
        raise DemoArtifactExtractionError(
            f"Unsafe archive member path: {archive_member_name}"
        ) from error

    return target_path


def _copy_demo_file(artifact_path: Path, prepared_dir: Path) -> None:
    destination = prepared_dir / artifact_path.name
    shutil.copy2(artifact_path, destination)


def _extract_zip_archive(archive_path: Path, prepared_dir: Path) -> None:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue

                target_path = _safe_output_path(prepared_dir, member.filename)
                target_path.parent.mkdir(parents=True, exist_ok=True)

                with archive.open(member) as source_file:
                    with target_path.open("wb") as output_file:
                        shutil.copyfileobj(source_file, output_file)
    except zipfile.BadZipFile as error:
        raise DemoArtifactExtractionError("Invalid .zip archive") from error


def _extract_rar_archive(archive_path: Path, prepared_dir: Path) -> None:
    try:
        with rarfile.RarFile(archive_path) as archive:
            for member in archive.infolist():
                if member.isdir():
                    continue

                target_path = _safe_output_path(prepared_dir, member.filename)
                target_path.parent.mkdir(parents=True, exist_ok=True)

                with archive.open(member) as source_file:
                    with target_path.open("wb") as output_file:
                        shutil.copyfileobj(source_file, output_file)
    except rarfile.RarCannotExec as error:
        raise DemoArtifactExtractionError(
            "Cannot extract .rar archive: install 7-Zip, unrar, unar, or bsdtar"
        ) from error
    except rarfile.BadRarFile as error:
        raise DemoArtifactExtractionError("Invalid .rar archive") from error


def _extract_7z_archive(archive_path: Path, prepared_dir: Path) -> None:
    try:
        with py7zr.SevenZipFile(archive_path, mode="r") as archive:
            for member_name in archive.getnames():
                _safe_output_path(prepared_dir, member_name)

            archive.extractall(path=prepared_dir)
    except py7zr.Bad7zFile as error:
        raise DemoArtifactExtractionError("Invalid .7z archive") from error


def _extract_archive(archive_path: Path, prepared_dir: Path) -> None:
    extension = archive_path.suffix.lower()

    if extension == ".zip":
        _extract_zip_archive(archive_path, prepared_dir)
        return

    if extension == ".rar":
        _extract_rar_archive(archive_path, prepared_dir)
        return

    if extension == ".7z":
        _extract_7z_archive(archive_path, prepared_dir)
        return

    raise DemoArtifactExtractionError(f"Unsupported archive extension: {extension}")


def _find_demo_files(prepared_dir: Path) -> list[Path]:
    return sorted(
        path for path in prepared_dir.rglob("*.dem")
        if path.is_file()
    )


def prepare_demo_artifact(stored_filename: str) -> PreparedDemoArtifact:
    artifact_path = _resolve_raw_artifact_path(stored_filename)
    artifact_id = _get_artifact_id_from_stored_filename(stored_filename)

    extension = artifact_path.suffix.lower()
    prepared_dir = PREPARED_DEMOS_DIR / artifact_id

    if prepared_dir.exists():
        shutil.rmtree(prepared_dir)

    prepared_dir.mkdir(parents=True, exist_ok=True)

    if extension == ".dem":
        artifact_type = "demo"
        _copy_demo_file(artifact_path, prepared_dir)
    elif extension in ARCHIVE_EXTENSIONS:
        artifact_type = "archive"
        _extract_archive(artifact_path, prepared_dir)
    else:
        raise DemoArtifactExtractionError(
            f"Unsupported demo artifact extension: {extension}"
        )

    demo_files = _find_demo_files(prepared_dir)

    if not demo_files:
        raise DemoArtifactExtractionError("No .dem files found in prepared artifact")

    return PreparedDemoArtifact(
        artifact_id=artifact_id,
        stored_filename=stored_filename,
        artifact_type=artifact_type,
        prepared_dir=prepared_dir,
        demo_files=demo_files,
    )