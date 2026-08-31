"""Import SQLAlchemy models here for Alembic autogeneration."""

from cs2eye.models.demo_file import DemoFile
from cs2eye.models.match import MapPoolEntry, Match, MatchVetoAction, Tournament, TournamentTeam
from cs2eye.models.demo import (
    DemoMapResult,
    DemoParseRun,
    DemoPlayerStat,
    DemoRound,
    DemoTeamOpponentContext,
    DemoTeamSideStat,
    DemoTeamBombStat,
    DemoTeamEconomyStat,
    DemoKill,
    DemoTeamCombatStat,
    DemoTeamUtilityStat,
    DemoUtilityEvent,
    DemoDamageEvent,
    DemoBombEvent,
    DemoRoundSwingEvent,
    RoundWinModelArtifact,
    DemoTeamRoster,
    TeamMapAggregate,
)
from cs2eye.models.team import (
    AnalystFactor,
    AnalystFactorPlayer,
    Player,
    RankingImportRun,
    Team,
    TeamParticipantMembership,
    TeamRoster,
    TeamRosterMember,
    TeamRankingSnapshot,
)
from cs2eye.models.prediction import MatchPrediction,PredictionHistorySnapshot,TournamentMatchPrediction,TournamentPredictionRun,WinProbabilityModelArtifact
from cs2eye.models.match_llm_analysis_run import MatchLLMAnalysisRun
from cs2eye.models.llm_quality import LLMQualityReview, LLMQualityRun


__all__ = [
    "DemoFile",
    "Match",
    "MatchVetoAction",
    "MapPoolEntry",
    "Tournament",
    "TournamentTeam",
    "DemoParseRun",
    "DemoMapResult",
    "DemoPlayerStat",
    "DemoRound",
    "DemoTeamOpponentContext",
    "DemoTeamSideStat",
    "DemoTeamBombStat",
    "DemoTeamEconomyStat",
    "DemoKill",
    "DemoTeamCombatStat",
    "DemoTeamUtilityStat",
    "DemoUtilityEvent",
    "DemoDamageEvent",
    "DemoBombEvent",
    "DemoRoundSwingEvent",
    "RoundWinModelArtifact",
    "DemoTeamRoster",
    "TeamMapAggregate",
    "Player",
    "AnalystFactor",
    "AnalystFactorPlayer",
    "RankingImportRun",
    "Team",
    "TeamParticipantMembership",
    "TeamRoster",
    "TeamRosterMember",
    "TeamRankingSnapshot",
    "MatchPrediction","PredictionHistorySnapshot","TournamentMatchPrediction","TournamentPredictionRun","WinProbabilityModelArtifact",
    "MatchLLMAnalysisRun",
    "LLMQualityRun",
    "LLMQualityReview",
]
