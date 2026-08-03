import re
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.demo import DemoMapResult
from cs2eye.services.demo_team_resolver import ResolvedDemoTeam, normalize_team_name, resolve_demo_teams

STANDARD_MAPS = (
    "mirage", "inferno", "nuke", "ancient", "anubis", "dust2", "train",
    "overpass", "vertigo", "cache",
)
MAP_ALIASES = {f"de_{name}": name for name in STANDARD_MAPS}


def normalize_map_name(raw_map_name: str | None) -> str | None:
    if not raw_map_name or not raw_map_name.strip():
        return None
    value = raw_map_name.strip().casefold()
    value = MAP_ALIASES.get(value, value.removeprefix("workshop/"))
    value = re.sub(r"[^a-z0-9_-]+", "_", value).strip("_-")
    return value[:160] or None


def detect_overtime(a: int | None, b: int | None, parser_overtime_periods: int | None = None) -> bool | None:
    if parser_overtime_periods is not None:
        return parser_overtime_periods > 0
    if a is None or b is None or a < 0 or b < 0 or a == b:
        return None
    if max(a, b) == 13:
        return False if min(a, b) <= 11 else None
    return min(a, b) >= 12 and max(a, b) > 13


@dataclass
class ParsedMapResult:
    raw_map_name: str | None = None
    team_a_name: str | None = None
    team_a_score: int | None = None
    team_b_name: str | None = None
    team_b_score: int | None = None
    parser_rounds_count: int | None = None
    parser_overtime_periods: int | None = None


@dataclass
class MetadataIssue:
    code: str
    severity: str
    message: str


@dataclass
class NormalizedMapResult:
    map_name: str | None
    team_a: ResolvedDemoTeam
    team_a_score: int | None
    team_b: ResolvedDemoTeam
    team_b_score: int | None
    winner_team_id: int | None
    winner_team_name: str | None
    rounds_count: int | None
    went_to_overtime: bool | None
    metadata_status: str
    issues: list[MetadataIssue] = field(default_factory=list)


def validate_demo_map_result(result: NormalizedMapResult) -> list[MetadataIssue]:
    issues: list[MetadataIssue] = []
    if not result.map_name:
        issues.append(MetadataIssue("missing_map", "partial", "Map name is missing."))
    elif result.map_name not in STANDARD_MAPS:
        issues.append(MetadataIssue("unknown_map", "review", "Map name is not in the standard map set."))
    if not result.team_a.raw_name or not result.team_b.raw_name:
        issues.append(MetadataIssue("missing_team", "partial", "Both team names are required."))
    a_key, b_key = normalize_team_name(result.team_a.raw_name), normalize_team_name(result.team_b.raw_name)
    if a_key and a_key == b_key:
        issues.append(MetadataIssue("same_team", "invalid", "Both sides refer to the same team."))
    if result.team_a.team_id is not None and result.team_a.team_id == result.team_b.team_id:
        issues.append(MetadataIssue("same_team_id", "invalid", "Both sides resolve to the same team."))
    if result.team_a.resolution_status in {"not_found", "ambiguous"} or result.team_b.resolution_status in {"not_found", "ambiguous"}:
        issues.append(MetadataIssue("team_not_resolved", "review", "At least one team could not be uniquely linked."))
    if result.team_a_score is None or result.team_b_score is None:
        issues.append(MetadataIssue("missing_score", "partial", "Both scores are required."))
    elif result.team_a_score < 0 or result.team_b_score < 0:
        issues.append(MetadataIssue("negative_score", "invalid", "Scores cannot be negative."))
    elif result.team_a_score == result.team_b_score:
        issues.append(MetadataIssue("invalid_final_score", "invalid", "A completed map cannot have a tied score."))
    else:
        expected_name = result.team_a.raw_name if result.team_a_score > result.team_b_score else result.team_b.raw_name
        if result.winner_team_name != expected_name:
            issues.append(MetadataIssue("winner_mismatch", "invalid", "Winner contradicts the score."))
    if result.team_a_score is not None and result.team_b_score is not None and result.rounds_count != result.team_a_score + result.team_b_score:
        issues.append(MetadataIssue("score_round_mismatch", "review", "Round count differs from the score sum."))
    if result.winner_team_id is not None and result.winner_team_id not in {result.team_a.team_id, result.team_b.team_id}:
        issues.append(MetadataIssue("winner_not_participant", "invalid", "Winner is not one of the participants."))
    return issues


def _status(issues: list[MetadataIssue]) -> str:
    if any(i.severity == "invalid" for i in issues): return "invalid"
    if any(i.severity == "review" for i in issues): return "needs_review"
    if any(i.severity == "partial" for i in issues): return "partial"
    return "complete"


def refresh_validation(result: NormalizedMapResult) -> None:
    result.issues = validate_demo_map_result(result)
    result.metadata_status = _status(result.issues)


async def normalize_parsed_map_result(session: AsyncSession, parsed: ParsedMapResult) -> NormalizedMapResult:
    team_a, team_b = await resolve_demo_teams(session, [parsed.team_a_name, parsed.team_b_name])
    winner = None
    if parsed.team_a_score is not None and parsed.team_b_score is not None and parsed.team_a_score != parsed.team_b_score:
        winner = team_a if parsed.team_a_score > parsed.team_b_score else team_b
    rounds = parsed.team_a_score + parsed.team_b_score if parsed.team_a_score is not None and parsed.team_b_score is not None else None
    result = NormalizedMapResult(normalize_map_name(parsed.raw_map_name), team_a, parsed.team_a_score, team_b, parsed.team_b_score, winner.team_id if winner else None, winner.raw_name if winner else None, rounds, detect_overtime(parsed.team_a_score, parsed.team_b_score, parsed.parser_overtime_periods), "partial")
    result.issues = validate_demo_map_result(result)
    if parsed.parser_rounds_count is not None and rounds is not None and parsed.parser_rounds_count != rounds:
        result.issues.append(MetadataIssue("score_round_mismatch", "review", f"Parser reported {parsed.parser_rounds_count} rounds, score implies {rounds}."))
    result.metadata_status = _status(result.issues)
    return result


def apply_to_model(model: DemoMapResult, result: NormalizedMapResult, source: str) -> DemoMapResult:
    model.map_name = result.map_name
    model.team_a_id, model.team_a_name, model.team_a_score = result.team_a.team_id, result.team_a.raw_name, result.team_a_score
    model.team_b_id, model.team_b_name, model.team_b_score = result.team_b.team_id, result.team_b.raw_name, result.team_b_score
    model.winner_team_id, model.winner_team_name = result.winner_team_id, result.winner_team_name
    model.rounds_count, model.went_to_overtime = result.rounds_count, result.went_to_overtime
    model.result_source, model.metadata_status = source, result.metadata_status
    return model
