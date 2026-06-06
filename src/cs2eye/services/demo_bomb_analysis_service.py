from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.demo import DemoBombRoundStat, DemoParseRun


@dataclass(frozen=True)
class BombAnalysisMeeting:
    parse_run_id: UUID
    demo_file_path: str
    map_name: str | None
    team_a_name: str | None
    team_b_name: str | None
    rounds_count: int | None
    exploded_bombs: int
    defused_bombs: int


@dataclass(frozen=True)
class BombAnalysisResult:
    map_name: str
    team_a_name: str | None
    team_b_name: str | None
    matches_count: int
    average_exploded_bombs_per_map: float
    average_defused_bombs_per_map: float
    meetings: list[BombAnalysisMeeting]


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None

    normalized_value = value.strip()

    if not normalized_value:
        return None

    return normalized_value


async def get_bomb_analysis(
        session: AsyncSession,
        map_name: str,
        team_a_name: str | None = None,
        team_b_name: str | None = None,
) -> BombAnalysisResult:
    normalized_map_name = _normalize_text(map_name)
    normalized_team_a_name = _normalize_text(team_a_name)
    normalized_team_b_name = _normalize_text(team_b_name)

    filters = [
        DemoParseRun.status == "success",
        DemoParseRun.map_name == normalized_map_name,
    ]

    should_show_meetings = (
        normalized_team_a_name is not None
        and normalized_team_b_name is not None
    )

    if should_show_meetings:
        filters.append(
            or_(
                and_(
                    DemoParseRun.team_a_name == normalized_team_a_name,
                    DemoParseRun.team_b_name == normalized_team_b_name,
                ),
                and_(
                    DemoParseRun.team_a_name == normalized_team_b_name,
                    DemoParseRun.team_b_name == normalized_team_a_name,
                ),
            )
        )

    exploded_bombs_expression = func.coalesce(
        func.sum(
            case(
                (DemoBombRoundStat.outcome == "exploded", 1),
                else_=0,
            )
        ),
        0,
    )

    defused_bombs_expression = func.coalesce(
        func.sum(
            case(
                (DemoBombRoundStat.outcome == "defused", 1),
                else_=0,
            )
        ),
        0,
    )

    result = await session.execute(
        select(
            DemoParseRun.id.label("parse_run_id"),
            DemoParseRun.demo_file_path,
            DemoParseRun.map_name,
            DemoParseRun.team_a_name,
            DemoParseRun.team_b_name,
            DemoParseRun.rounds_count,
            exploded_bombs_expression.label("exploded_bombs"),
            defused_bombs_expression.label("defused_bombs"),
        )
        .join(
            DemoBombRoundStat,
            DemoBombRoundStat.parse_run_id == DemoParseRun.id,
            isouter=True,
        )
        .where(*filters)
        .group_by(
            DemoParseRun.id,
            DemoParseRun.demo_file_path,
            DemoParseRun.map_name,
            DemoParseRun.team_a_name,
            DemoParseRun.team_b_name,
            DemoParseRun.rounds_count,
            DemoParseRun.started_at,
        )
        .order_by(DemoParseRun.started_at.desc())
    )

    all_meetings = [
        BombAnalysisMeeting(
            parse_run_id=row["parse_run_id"],
            demo_file_path=row["demo_file_path"],
            map_name=row["map_name"],
            team_a_name=row["team_a_name"],
            team_b_name=row["team_b_name"],
            rounds_count=row["rounds_count"],
            exploded_bombs=int(row["exploded_bombs"]),
            defused_bombs=int(row["defused_bombs"]),
        )
        for row in result.mappings().all()
    ]

    matches_count = len(all_meetings)

    exploded_bombs_sum = sum(
        meeting.exploded_bombs
        for meeting in all_meetings
    )

    defused_bombs_sum = sum(
        meeting.defused_bombs
        for meeting in all_meetings
    )

    return BombAnalysisResult(
        map_name=normalized_map_name or map_name,
        team_a_name=normalized_team_a_name,
        team_b_name=normalized_team_b_name,
        matches_count=matches_count,
        average_exploded_bombs_per_map=(
            round(exploded_bombs_sum / matches_count, 2)
            if matches_count > 0
            else 0.0
        ),
        average_defused_bombs_per_map=(
            round(defused_bombs_sum / matches_count, 2)
            if matches_count > 0
            else 0.0
        ),
        meetings=all_meetings if should_show_meetings else [],
    )