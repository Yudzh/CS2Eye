from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.demo import DemoBombRoundStat, DemoParseRun


@dataclass(frozen=True)
class BombAnalysisMap:
    map_name: str | None
    matches_count: int
    exploded_bombs: int
    defused_bombs: int
    average_exploded_bombs_per_map: float
    average_defused_bombs_per_map: float


@dataclass(frozen=True)
class BombAnalysisMeeting:
    parse_run_id: UUID
    demo_file_path: str

    tournament_name: str | None
    match_date: date | None

    map_name: str | None
    map_number: int | None

    team_a_name: str | None
    team_b_name: str | None

    rounds_count: int | None

    exploded_bombs: int
    defused_bombs: int


@dataclass(frozen=True)
class BombAnalysisResult:
    map_name: str | None
    team_a_name: str | None
    team_b_name: str | None
    maps: list[BombAnalysisMap]
    recent_meetings: list[BombAnalysisMeeting]


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None

    value = value.strip()

    return value or None


async def get_bomb_analysis(
        session: AsyncSession,
        map_name: str | None = None,
        team_a_name: str | None = None,
        team_b_name: str | None = None,
) -> BombAnalysisResult:
    normalized_map_name = _normalize_text(map_name)
    normalized_team_a_name = _normalize_text(team_a_name)
    normalized_team_b_name = _normalize_text(team_b_name)

    filters = [
        DemoParseRun.status == "success",
    ]

    if normalized_map_name is not None:
        filters.append(DemoParseRun.map_name == normalized_map_name)

    if normalized_team_a_name is not None and normalized_team_b_name is not None:
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
            DemoParseRun.tournament_name,
            DemoParseRun.match_date,
            DemoParseRun.map_name,
            DemoParseRun.map_number,
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
            DemoParseRun.tournament_name,
            DemoParseRun.match_date,
            DemoParseRun.map_name,
            DemoParseRun.map_number,
            DemoParseRun.team_a_name,
            DemoParseRun.team_b_name,
            DemoParseRun.rounds_count,
            DemoParseRun.started_at,
        )
        .order_by(
            DemoParseRun.match_date.desc().nullslast(),
            DemoParseRun.started_at.desc(),
        )
    )

    meetings = [
        BombAnalysisMeeting(
            parse_run_id=row["parse_run_id"],
            demo_file_path=row["demo_file_path"],
            tournament_name=row["tournament_name"],
            match_date=row["match_date"],
            map_name=row["map_name"],
            map_number=row["map_number"],
            team_a_name=row["team_a_name"],
            team_b_name=row["team_b_name"],
            rounds_count=row["rounds_count"],
            exploded_bombs=int(row["exploded_bombs"]),
            defused_bombs=int(row["defused_bombs"]),
        )
        for row in result.mappings().all()
    ]

    grouped_by_map: dict[str | None, list[BombAnalysisMeeting]] = {}

    for meeting in meetings:
        grouped_by_map.setdefault(meeting.map_name, []).append(meeting)

    maps = []

    for current_map_name, map_meetings in grouped_by_map.items():
        matches_count = len(map_meetings)

        exploded_bombs = sum(
            meeting.exploded_bombs
            for meeting in map_meetings
        )

        defused_bombs = sum(
            meeting.defused_bombs
            for meeting in map_meetings
        )

        maps.append(
            BombAnalysisMap(
                map_name=current_map_name,
                matches_count=matches_count,
                exploded_bombs=exploded_bombs,
                defused_bombs=defused_bombs,
                average_exploded_bombs_per_map=round(exploded_bombs / matches_count, 2)
                if matches_count > 0
                else 0.0,
                average_defused_bombs_per_map=round(defused_bombs / matches_count, 2)
                if matches_count > 0
                else 0.0,
            )
        )

    maps.sort(
        key=lambda item: (
            item.matches_count,
            item.exploded_bombs + item.defused_bombs,
        ),
        reverse=True,
    )

    return BombAnalysisResult(
        map_name=normalized_map_name,
        team_a_name=normalized_team_a_name,
        team_b_name=normalized_team_b_name,
        maps=maps,
        recent_meetings=meetings[:10],
    )