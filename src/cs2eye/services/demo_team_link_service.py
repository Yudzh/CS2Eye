import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.team import Team
from cs2eye.services.demo_parser_service import ParsedDemoPlayerStat


OpponentRankGroup = Literal["top_15", "top_16_30", "outside_top_30", "unknown"]


def normalize_team_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().casefold())
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", ascii_value).strip()


def team_name_aliases(value: str) -> set[str]:
    """Return exact normalized aliases without fuzzy matching."""
    normalized = normalize_team_name(value)
    aliases = {normalized} if normalized else set()
    words = normalized.split()
    while words and words[-1] in {"clan", "esports", "cs2"}:
        words.pop()
        if words:
            aliases.add(" ".join(words))
    return aliases


def opponent_rank_group(rank: int | None) -> OpponentRankGroup:
    if rank is None:
        return "unknown"
    if 1 <= rank <= 15:
        return "top_15"
    if 16 <= rank <= 30:
        return "top_16_30"
    return "outside_top_30"


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


async def resolve_demo_opponents(
    session: AsyncSession, stats: list[ParsedDemoPlayerStat],
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
            ) for item in stats
        }, diagnostics

    teams = (await session.execute(select(Team))).scalars().all()
    resolutions: dict[str, TeamResolution] = {}
    for key, demo_name in names_by_key.items():
        demo_aliases = team_name_aliases(demo_name)
        matches = [
            team for team in teams
            if demo_aliases.intersection(team_name_aliases(team.name))
        ]
        team = matches[0] if len(matches) == 1 else None
        resolutions[key] = TeamResolution(demo_name, team)
        if not matches:
            diagnostics.append(f'Demo team "{demo_name}" was not found in teams.')
        elif len(matches) > 1:
            diagnostics.append(f'Demo team "{demo_name}" is ambiguous ({len(matches)} matches).')

    keys = list(names_by_key)
    snapshots: dict[str, PlayerOpponentSnapshot] = {}
    for item in stats:
        own_key = normalize_team_name(item.team_name or "")
        if own_key not in resolutions:
            snapshots[item.identity_key] = PlayerOpponentSnapshot(
                None, item.team_name, None, None, None, "unknown",
            )
            continue
        opponent_key = keys[1] if keys[0] == own_key else keys[0]
        own = resolutions[own_key]
        opponent = resolutions[opponent_key]
        rank = opponent.team.current_rank if opponent.team else None
        snapshots[item.identity_key] = PlayerOpponentSnapshot(
            demo_team_id=own.team.id if own.team else None,
            demo_team_name=item.team_name,
            opponent_team_id=opponent.team.id if opponent.team else None,
            opponent_team_name=opponent.demo_name,
            opponent_rank=rank,
            opponent_rank_group=(
                opponent_rank_group(rank) if opponent.team else "unknown"
            ),
        )
    return snapshots, diagnostics
