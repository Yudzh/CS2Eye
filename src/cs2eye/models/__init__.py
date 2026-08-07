"""Import SQLAlchemy models here for Alembic autogeneration."""

from cs2eye.models.demo_file import DemoFile
from cs2eye.models.match import Match, Tournament
from cs2eye.models.demo import (
    DemoMapResult,
    DemoParseRun,
    DemoPlayerStat,
    DemoRound,
    DemoTeamOpponentContext,
    DemoTeamSideStat,
    DemoTeamRoster,
    TeamMapAggregate,
)
from cs2eye.models.team import (
    Player,
    RankingImportRun,
    Team,
    TeamParticipantMembership,
    TeamRoster,
    TeamRosterMember,
    TeamRankingSnapshot,
)


__all__ = [
    "DemoFile",
    "Match",
    "Tournament",
    "DemoParseRun",
    "DemoMapResult",
    "DemoPlayerStat",
    "DemoRound",
    "DemoTeamOpponentContext",
    "DemoTeamSideStat",
    "DemoTeamRoster",
    "TeamMapAggregate",
    "Player",
    "RankingImportRun",
    "Team",
    "TeamParticipantMembership",
    "TeamRoster",
    "TeamRosterMember",
    "TeamRankingSnapshot",
]
