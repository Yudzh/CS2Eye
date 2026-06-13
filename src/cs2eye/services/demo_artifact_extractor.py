import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import py7zr

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
    artifact_id = Path(stored_filename).name.split("__", 1)[0]

    try:
        UUID(artifact_id)
    except ValueError as error:
        raise DemoArtifactExtractionError(
            "Stored filename must start with artifact UUID"
        ) from error

    return artifact_id


def _safe_relative_stored_path(stored_filename: str) -> Path:
    relative_path = Path(stored_filename)

    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise DemoArtifactExtractionError("Stored filename contains unsafe path parts")

    return relative_path


def _resolve_raw_artifact_path(stored_filename: str) -> Path:
    relative_path = _safe_relative_stored_path(stored_filename)

    artifact_path = (RAW_DEMOS_DIR / relative_path).resolve()
    raw_root = RAW_DEMOS_DIR.resolve()

    try:
        artifact_path.relative_to(raw_root)
    except ValueError as error:
        raise DemoArtifactExtractionError("Stored filename points outside raw storage") from error

    if not artifact_path.exists():
        raise DemoArtifactExtractionError("Uploaded demo artifact was not found")

    if not artifact_path.is_file():
        raise DemoArtifactExtractionError("Uploaded demo artifact is not a file")

    return artifact_path


def _extract_nested_archives(prepared_dir: Path) -> None:
    processed_archives: set[Path] = set()

    while True:
        archive_files = sorted(
            path for path in prepared_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in ARCHIVE_EXTENSIONS
        )

        new_archives = [
            archive_path
            for archive_path in archive_files
            if archive_path.resolve() not in processed_archives
        ]

        if not new_archives:
            return

        for archive_path in new_archives:
            processed_archives.add(archive_path.resolve())

            nested_output_dir = archive_path.parent / archive_path.stem
            nested_output_dir.mkdir(parents=True, exist_ok=True)

            _extract_archive(
                archive_path=archive_path,
                prepared_dir=nested_output_dir,
            )


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
        list_result = subprocess.run(
            ["bsdtar", "-tf", str(archive_path)],
            capture_output=True,
            text=True,
            check=True,
        )

        for member_name in list_result.stdout.splitlines():
            if not member_name.strip():
                continue

            _safe_output_path(prepared_dir, member_name)

        subprocess.run(
            [
                "bsdtar",
                "-xf",
                str(archive_path),
                "-C",
                str(prepared_dir),
            ],
            capture_output=True,
            text=True,
            check=True,
        )

    except FileNotFoundError as error:
        raise DemoArtifactExtractionError(
            "Cannot extract .rar archive: bsdtar is not installed in api container"
        ) from error

    except subprocess.CalledProcessError as error:
        raise DemoArtifactExtractionError(
            f"Invalid .rar archive or extraction failed: {error.stderr.strip()}"
        ) from error


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

    stored_relative_path = _safe_relative_stored_path(stored_filename)
    prepared_parent_dir = stored_relative_path.parent

    prepared_dir = PREPARED_DEMOS_DIR / prepared_parent_dir / artifact_id

    if prepared_dir.exists():
        shutil.rmtree(prepared_dir)

    prepared_dir.mkdir(parents=True, exist_ok=True)

    if extension == ".dem":
        artifact_type = "demo"
        _copy_demo_file(artifact_path, prepared_dir)
    elif extension in ARCHIVE_EXTENSIONS:
        artifact_type = "archive"
        _extract_archive(artifact_path, prepared_dir)
        _extract_nested_archives(prepared_dir)
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
