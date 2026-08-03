from dataclasses import dataclass
from datetime import date
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.core.config import settings
from cs2eye.models.team import Team, TeamRankingSnapshot


OpponentRankGroup = Literal[
    "top_15", "top_16_30", "outside_top_30", "unknown",
]
OpponentRankSource = Literal[
    "historical_snapshot", "current_fallback", "unknown",
]


def opponent_rank_group(rank: int | None) -> OpponentRankGroup:
    if rank is None:
        return "unknown"
    if 1 <= rank <= 15:
        return "top_15"
    if 16 <= rank <= 30:
        return "top_16_30"
    return "outside_top_30"


@dataclass(frozen=True)
class ResolvedOpponentRank:
    rank: int | None
    rank_group: OpponentRankGroup
    source: OpponentRankSource
    snapshot_id: int | None
    snapshot_date: date | None


UNKNOWN_RANK = ResolvedOpponentRank(None, "unknown", "unknown", None, None)


async def resolve_opponent_rank(
    session: AsyncSession,
    opponent_team_id: int | None,
    match_date: date | None,
) -> ResolvedOpponentRank:
    if opponent_team_id is None:
        return UNKNOWN_RANK

    if match_date is not None:
        snapshot = (
            await session.execute(
                select(TeamRankingSnapshot)
                .where(
                    TeamRankingSnapshot.team_id == opponent_team_id,
                    TeamRankingSnapshot.ranking_date <= match_date,
                )
                .order_by(
                    TeamRankingSnapshot.ranking_date.desc(),
                    TeamRankingSnapshot.id.desc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if (
            snapshot is not None
            and (match_date - snapshot.ranking_date).days
            <= settings.max_ranking_snapshot_age_days
        ):
            return ResolvedOpponentRank(
                snapshot.rank,
                opponent_rank_group(snapshot.rank),
                "historical_snapshot",
                snapshot.id,
                snapshot.ranking_date,
            )

    team = await session.get(Team, opponent_team_id)
    if team is not None and team.current_rank is not None:
        return ResolvedOpponentRank(
            team.current_rank,
            opponent_rank_group(team.current_rank),
            "current_fallback",
            None,
            None,
        )
    return UNKNOWN_RANK
