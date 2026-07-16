from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.demo import DemoParseRun, DemoRoundStat
from cs2eye.services.demo_team_map_stats_service import (
    TeamMapMatchupItem,
    TeamMapStatsItem,
    get_team_map_matchup,
    get_team_map_stats,
)
from cs2eye.services.team_service import (
    TeamComparisonInfo,
    TeamDetailInfo,
    TeamStrengthInfo,
    compare_teams,
    get_team_detail,
    list_teams,
)


@dataclass(frozen=True)
class TeamRosterStateInfo:
    code: str
    note: str


@dataclass(frozen=True)
class TeamSummaryInfo:
    id: UUID
    name: str
    country: str | None
    region: str | None

    active_players_count: int
    team_strength_score: float
    roster_state: TeamRosterStateInfo


@dataclass(frozen=True)
class TeamDashboardInfo:
    team: TeamDetailInfo
    roster_state: TeamRosterStateInfo
    maps: list[TeamMapStatsItem]


@dataclass(frozen=True)
class TeamComparisonSideInfo:
    strength: TeamStrengthInfo
    relative_strength_percent: float | None
    roster_state: TeamRosterStateInfo


@dataclass(frozen=True)
class TeamHeadToHeadMapInfo:
    parse_run_id: UUID

    tournament_name: str | None
    match_date: date | None
    map_name: str | None
    map_number: int | None

    team_a_name: str
    team_b_name: str

    team_a_rounds: int
    team_b_rounds: int
    winner_team_name: str | None


@dataclass(frozen=True)
class TeamComparisonDashboardInfo:
    team_a: TeamComparisonSideInfo
    team_b: TeamComparisonSideInfo

    comparison: TeamComparisonInfo
    map_comparisons: list[TeamMapMatchupItem]
    recent_head_to_head_maps: list[TeamHeadToHeadMapInfo]


def _same_team(left: str | None, right: str | None) -> bool:
    if left is None or right is None:
        return False

    return left.strip().casefold() == right.strip().casefold()


def build_roster_state(
        strength: TeamStrengthInfo,
) -> TeamRosterStateInfo:
    if strength.active_players_count < 5:
        return TeamRosterStateInfo(
            code="incomplete",
            note=(
                "Неполный состав: "
                f"{strength.active_players_count}/5 активных игроков."
            ),
        )

    if any("stand-in" in note.casefold() for note in strength.notes):
        return TeamRosterStateInfo(
            code="stand_in",
            note="Команда играет со stand-in игроком.",
        )

    if any("новые игроки" in note.casefold() for note in strength.notes):
        return TeamRosterStateInfo(
            code="new",
            note="В составе есть игроки, пришедшие за последние 14 дней.",
        )

    if any(
        "стабилен минимум 90 дней" in note.casefold()
        for note in strength.notes
    ):
        return TeamRosterStateInfo(
            code="stable",
            note="Состав стабилен минимум 90 дней.",
        )

    return TeamRosterStateInfo(
        code="unknown",
        note="Недостаточно данных, чтобы оценить стабильность состава.",
    )


def calculate_relative_strength_percentages(
        team_a_score: float,
        team_b_score: float,
) -> tuple[float | None, float | None]:
    safe_team_a_score = max(0.0, team_a_score)
    safe_team_b_score = max(0.0, team_b_score)
    total_score = safe_team_a_score + safe_team_b_score

    if total_score <= 0:
        return None, None

    team_a_percent = round(
        safe_team_a_score / total_score * 100,
        2,
    )

    return team_a_percent, round(100.0 - team_a_percent, 2)


def _resolve_round_winner_team_name(
        round_stat: DemoRoundStat,
) -> str | None:
    if round_stat.winner_team_name:
        return round_stat.winner_team_name

    if round_stat.winner_side == "CT":
        return round_stat.ct_team_name

    if round_stat.winner_side == "T":
        return round_stat.t_team_name

    return None


async def list_team_summaries(
        *,
        session: AsyncSession,
) -> list[TeamSummaryInfo]:
    teams = await list_teams(session=session)

    return [
        TeamSummaryInfo(
            id=team.id,
            name=team.name,
            country=team.country,
            region=team.region,
            active_players_count=team.strength.active_players_count,
            team_strength_score=team.strength.team_strength_score,
            roster_state=build_roster_state(team.strength),
        )
        for team in teams
    ]


async def get_team_dashboard(
        *,
        session: AsyncSession,
        team_id: UUID,
) -> TeamDashboardInfo:
    team = await get_team_detail(
        session=session,
        team_id=team_id,
    )

    map_stats = await get_team_map_stats(
        session=session,
        team_name=team.name,
    )

    maps = sorted(
        map_stats.items,
        key=lambda item: (
            -item.total_matches_on_map,
            -item.map_strength_score,
            item.map_name or "",
        ),
    )

    return TeamDashboardInfo(
        team=team,
        roster_state=build_roster_state(team.strength),
        maps=maps,
    )


async def get_recent_head_to_head_maps(
        *,
        session: AsyncSession,
        team_a_name: str,
        team_b_name: str,
        limit: int = 10,
) -> list[TeamHeadToHeadMapInfo]:
    normalized_team_a_name = team_a_name.strip()
    normalized_team_b_name = team_b_name.strip()

    if not normalized_team_a_name:
        raise ValueError("team_a_name is required")

    if not normalized_team_b_name:
        raise ValueError("team_b_name is required")

    if _same_team(normalized_team_a_name, normalized_team_b_name):
        raise ValueError("Teams must be different")

    team_a_key = normalized_team_a_name.casefold()
    team_b_key = normalized_team_b_name.casefold()

    parse_runs_result = await session.execute(
        select(DemoParseRun)
        .where(
            DemoParseRun.status == "success",
            or_(
                and_(
                    func.lower(DemoParseRun.team_a_name) == team_a_key,
                    func.lower(DemoParseRun.team_b_name) == team_b_key,
                ),
                and_(
                    func.lower(DemoParseRun.team_a_name) == team_b_key,
                    func.lower(DemoParseRun.team_b_name) == team_a_key,
                ),
            ),
        )
        .order_by(
            DemoParseRun.match_date.desc().nullslast(),
            DemoParseRun.started_at.desc(),
        )
        .limit(limit)
    )

    parse_runs = list(parse_runs_result.scalars().all())

    if not parse_runs:
        return []

    parse_run_ids = [parse_run.id for parse_run in parse_runs]

    round_stats_result = await session.execute(
        select(DemoRoundStat)
        .where(DemoRoundStat.parse_run_id.in_(parse_run_ids))
        .order_by(
            DemoRoundStat.parse_run_id,
            DemoRoundStat.round_number,
        )
    )

    round_stats_by_parse_run_id: dict[
        UUID,
        list[DemoRoundStat],
    ] = defaultdict(list)

    for round_stat in round_stats_result.scalars().all():
        round_stats_by_parse_run_id[
            round_stat.parse_run_id
        ].append(round_stat)

    meetings: list[TeamHeadToHeadMapInfo] = []

    for parse_run in parse_runs:
        team_a_rounds = 0
        team_b_rounds = 0

        for round_stat in round_stats_by_parse_run_id[parse_run.id]:
            winner_team_name = _resolve_round_winner_team_name(
                round_stat
            )

            if _same_team(
                winner_team_name,
                normalized_team_a_name,
            ):
                team_a_rounds += 1
            elif _same_team(
                winner_team_name,
                normalized_team_b_name,
            ):
                team_b_rounds += 1

        if team_a_rounds > team_b_rounds:
            winner_team_name = normalized_team_a_name
        elif team_b_rounds > team_a_rounds:
            winner_team_name = normalized_team_b_name
        else:
            winner_team_name = None

        meetings.append(
            TeamHeadToHeadMapInfo(
                parse_run_id=parse_run.id,
                tournament_name=parse_run.tournament_name,
                match_date=parse_run.match_date,
                map_name=parse_run.map_name,
                map_number=parse_run.map_number,
                team_a_name=normalized_team_a_name,
                team_b_name=normalized_team_b_name,
                team_a_rounds=team_a_rounds,
                team_b_rounds=team_b_rounds,
                winner_team_name=winner_team_name,
            )
        )

    return meetings


async def compare_team_dashboards(
        *,
        session: AsyncSession,
        team_a_id: UUID,
        team_b_id: UUID,
) -> TeamComparisonDashboardInfo:
    if team_a_id == team_b_id:
        raise ValueError("Teams must be different")

    comparison = await compare_teams(
        session=session,
        team_a_id=team_a_id,
        team_b_id=team_b_id,
    )

    map_matchup = await get_team_map_matchup(
        session=session,
        team_a_name=comparison.team_a.team_name,
        team_b_name=comparison.team_b.team_name,
    )

    recent_head_to_head_maps = await get_recent_head_to_head_maps(
        session=session,
        team_a_name=comparison.team_a.team_name,
        team_b_name=comparison.team_b.team_name,
        limit=10,
    )

    team_a_percent, team_b_percent = (
        calculate_relative_strength_percentages(
            comparison.team_a.team_strength_score,
            comparison.team_b.team_strength_score,
        )
    )

    return TeamComparisonDashboardInfo(
        team_a=TeamComparisonSideInfo(
            strength=comparison.team_a,
            relative_strength_percent=team_a_percent,
            roster_state=build_roster_state(comparison.team_a),
        ),
        team_b=TeamComparisonSideInfo(
            strength=comparison.team_b,
            relative_strength_percent=team_b_percent,
            roster_state=build_roster_state(comparison.team_b),
        ),
        comparison=comparison,
        map_comparisons=map_matchup.items,
        recent_head_to_head_maps=recent_head_to_head_maps,
    )