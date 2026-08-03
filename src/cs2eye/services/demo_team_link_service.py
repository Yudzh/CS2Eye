from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.team import Team
from cs2eye.services.demo_parser_service import ParsedDemoPlayerStat
from cs2eye.services.demo_team_resolver import (
    normalize_team_name, resolve_demo_team, team_name_aliases,
)
from cs2eye.services.opponent_rank_resolver import (
    OpponentRankGroup,
    ResolvedOpponentRank,
    UNKNOWN_RANK,
    opponent_rank_group,
    resolve_opponent_rank,
)


@dataclass(frozen=True)
class TeamResolution:
    demo_name: str
    team: Team | None


@dataclass(frozen=True)
class PlayerOpponentSnapshot:
    demo_team_id: int | None
    demo_team_name: str | None
    opponent_team_id: int | None
    opponent_team_name: str | None
    opponent_rank: int | None
    opponent_rank_group: OpponentRankGroup
    opponent_rank_source: str
    opponent_rank_snapshot_id: int | None
    opponent_rank_snapshot_date: date | None


async def resolve_demo_opponents(
    session: AsyncSession,
    stats: list[ParsedDemoPlayerStat],
    match_date: date | None = None,
) -> tuple[dict[str, PlayerOpponentSnapshot], list[str]]:
    names_by_key = {
        normalize_team_name(item.team_name): item.team_name
        for item in stats if item.team_name and normalize_team_name(item.team_name)
    }
    diagnostics: list[str] = []
    if len(names_by_key) != 2:
        diagnostics.append(
            f"Expected exactly two demo teams, found {len(names_by_key)}.",
        )
        return {
            item.identity_key: PlayerOpponentSnapshot(
                None, item.team_name, None, None, None, "unknown",
                "unknown", None, None,
            ) for item in stats
        }, diagnostics

    teams = (await session.execute(select(Team))).scalars().all()
    resolutions: dict[str, TeamResolution] = {}
    for key, demo_name in names_by_key.items():
        demo_aliases = team_name_aliases(demo_name)
        resolved = await resolve_demo_team(session, demo_name, teams)
        matches = [team for team in teams if demo_aliases.intersection(team_name_aliases(team.name))]
        team = next((team for team in teams if team.id == resolved.team_id), None)
        resolutions[key] = TeamResolution(demo_name, team)
        if not matches:
            diagnostics.append(f'Demo team "{demo_name}" was not found in teams.')
        elif len(matches) > 1:
            diagnostics.append(f'Demo team "{demo_name}" is ambiguous ({len(matches)} matches).')

    keys = list(names_by_key)
    resolved_ranks: dict[int, ResolvedOpponentRank] = {}
    for resolution in resolutions.values():
        if resolution.team is not None:
            resolved_ranks[resolution.team.id] = await resolve_opponent_rank(
                session, resolution.team.id, match_date,
            )
    snapshots: dict[str, PlayerOpponentSnapshot] = {}
    for item in stats:
        own_key = normalize_team_name(item.team_name or "")
        if own_key not in resolutions:
            snapshots[item.identity_key] = PlayerOpponentSnapshot(
                None, item.team_name, None, None, None, "unknown",
                "unknown", None, None,
            )
            continue
        opponent_key = keys[1] if keys[0] == own_key else keys[0]
        own = resolutions[own_key]
        opponent = resolutions[opponent_key]
        resolved_rank = (
            resolved_ranks.get(opponent.team.id, UNKNOWN_RANK)
            if opponent.team else UNKNOWN_RANK
        )
        snapshots[item.identity_key] = PlayerOpponentSnapshot(
            demo_team_id=own.team.id if own.team else None,
            demo_team_name=item.team_name,
            opponent_team_id=opponent.team.id if opponent.team else None,
            opponent_team_name=opponent.demo_name,
            opponent_rank=resolved_rank.rank,
            opponent_rank_group=resolved_rank.rank_group,
            opponent_rank_source=resolved_rank.source,
            opponent_rank_snapshot_id=resolved_rank.snapshot_id,
            opponent_rank_snapshot_date=resolved_rank.snapshot_date,
        )
    return snapshots, diagnostics
