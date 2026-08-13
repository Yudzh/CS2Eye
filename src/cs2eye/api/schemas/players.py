from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel


class PlayerTeamResponse(BaseModel):
    id: int
    bo3_id: int
    bo3_slug: str
    name: str
    logo_url: str | None
    is_active: bool
    participant_type: str


class PlayerResponse(BaseModel):
    id: int
    bo3_id: int
    bo3_slug: str
    nickname: str
    first_name: str | None
    last_name: str | None
    image_url: str | None
    country_code: str | None
    country_name: str | None
    bo3_rating: Decimal | None
    bo3_avg_rating: Decimal | None
    player_strength: int | None
    player_strength_raw_score: float | None
    player_strength_reliability: float | None
    player_strength_model_version: str | None
    steam_id: str | None
    internal_rating: Decimal | None
    internal_rating_maps_count: int
    internal_rating_rounds_count: int
    internal_rating_updated_at: datetime | None
    internal_rating_version: str | None
    internal_rating_top15: Decimal | None
    internal_rating_top15_maps_count: int
    internal_rating_top15_rounds_count: int
    internal_rating_top16_30: Decimal | None
    internal_rating_top16_30_maps_count: int
    internal_rating_top16_30_rounds_count: int
    strength_breakdown: dict[str, Any] | None
    combat: dict[str, Any]
    utility: dict[str, Any]
    round_swing: dict[str, Any]
    stats_synced_at: datetime | None
    source_updated_at: datetime | None
    teams: list[PlayerTeamResponse]
    igl: dict[str, Any] | None = None
    captain_strength: float | None = None
