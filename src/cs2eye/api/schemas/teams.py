from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class TeamParticipantResponse(BaseModel):
    id: int
    bo3_id: int
    bo3_slug: str
    nickname: str
    image_url: str | None
    country_code: str | None
    country_name: str | None
    participant_type: str


class TeamListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bo3_id: int
    bo3_slug: str
    name: str
    logo_url: str | None
    country_code: str | None
    country_name: str | None
    region: str | None
    current_rank: int | None
    current_points: Decimal | None
    rank_change: int | None
    ranking_date: date | None
    is_analytics_active: bool
    roster_synced_at: datetime | None
    roster: list[TeamParticipantResponse] = Field(
        default_factory=list,
    )


class RankingRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    source: str
    source_url: str
    started_at: datetime
    finished_at: datetime | None
    ranking_date: date | None
    teams_received: int
    teams_activated: int
    teams_deactivated: int
    player_profiles_updated: int
    player_profiles_failed: int
    player_profile_failures: list[dict] = Field(default_factory=list)
    error_message: str | None


class ProbeTeamResponse(BaseModel):
    rank: int
    name: str
    bo3_id: int
    bo3_slug: str
    points: Decimal
    rank_change: int | None
    region: str | None
    roster_size: int


class TopTeamsProbeResponse(BaseModel):
    ranking_date: date
    teams_received: int
    teams: list[ProbeTeamResponse]
