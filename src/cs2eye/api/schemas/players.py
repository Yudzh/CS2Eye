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
    player_strength: int | None
    strength_breakdown: dict[str, Any] | None
    stats_synced_at: datetime | None
    source_updated_at: datetime | None
    teams: list[PlayerTeamResponse]
