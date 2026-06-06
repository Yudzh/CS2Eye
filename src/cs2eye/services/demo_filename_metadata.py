import re
from dataclasses import dataclass
from pathlib import Path


PREPARED_DEMOS_DIR = Path("storage/demos/prepared")

DEMO_FILENAME_PATTERN = re.compile(
    r"^(?P<team_a>.+)-vs-(?P<team_b>.+)-m(?P<map_number>\d+)-(?P<map_name>[a-zA-Z0-9_]+)$"
)


@dataclass(frozen=True)
class PreparedDemoFileMetadata:
    demo_file_path: Path
    file_name: str
    artifact_id: str | None
    detected_team_a_name: str | None
    detected_team_b_name: str | None
    detected_map_name: str | None
    metadata_detected_from_filename: bool


def _humanize_team_slug(value: str) -> str:
    return (
        value
        .replace("_", "-")
        .replace("-", " ")
        .strip()
        .title()
    )


def _normalize_map_name(value: str) -> str:
    normalized_value = value.strip().lower()

    if normalized_value.startswith("de_"):
        return normalized_value

    return f"de_{normalized_value}"


def _extract_artifact_id(demo_file_path: Path) -> str | None:
    try:
        relative_path = demo_file_path.relative_to(PREPARED_DEMOS_DIR)
    except ValueError:
        return None

    if not relative_path.parts:
        return None

    return relative_path.parts[0]


def build_prepared_demo_file_metadata(
        demo_file_path: Path,
) -> PreparedDemoFileMetadata:
    file_name = demo_file_path.name
    stem = demo_file_path.stem

    match = DEMO_FILENAME_PATTERN.match(stem)

    if match is None:
        return PreparedDemoFileMetadata(
            demo_file_path=demo_file_path,
            file_name=file_name,
            artifact_id=_extract_artifact_id(demo_file_path),
            detected_team_a_name=None,
            detected_team_b_name=None,
            detected_map_name=None,
            metadata_detected_from_filename=False,
        )

    return PreparedDemoFileMetadata(
        demo_file_path=demo_file_path,
        file_name=file_name,
        artifact_id=_extract_artifact_id(demo_file_path),
        detected_team_a_name=_humanize_team_slug(match.group("team_a")),
        detected_team_b_name=_humanize_team_slug(match.group("team_b")),
        detected_map_name=_normalize_map_name(match.group("map_name")),
        metadata_detected_from_filename=True,
    )