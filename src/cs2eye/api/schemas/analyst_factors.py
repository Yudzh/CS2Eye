from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

FactorType = Literal["positive", "negative"]
Environment = Literal["lan", "online", "any"]
Category = Literal["overall", "ct_defense", "t_attack", "tactics", "veto", "form", "communication", "roles", "individual", "teamplay", "mental", "coach", "roster", "other"]


class AnalystPerson(BaseModel):
    id: int
    nickname: str


class AnalystFactorBase(BaseModel):
    team_id: int
    factor_type: FactorType
    text: str = Field(min_length=1, max_length=5000)
    category: Category | None = None
    map_name: str | None = None
    environment: Environment = "any"
    player_ids: list[int] = Field(default_factory=list)
    coach_id: int | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def validate_dates(self):
        if self.valid_from and self.valid_until and self.valid_until <= self.valid_from:
            raise ValueError("valid_until должен быть позже valid_from")
        self.player_ids = list(dict.fromkeys(self.player_ids))
        return self


class AnalystFactorCreate(AnalystFactorBase):
    pass


class AnalystFactorUpdate(BaseModel):
    factor_type: FactorType | None = None
    text: str | None = Field(default=None, min_length=1, max_length=5000)
    category: Category | None = None
    map_name: str | None = None
    environment: Environment | None = None
    player_ids: list[int] | None = None
    coach_id: int | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    is_active: bool | None = None


class AnalystFactorResponse(BaseModel):
    id: int
    team_id: int
    team_name: str
    factor_type: FactorType
    text: str
    category: Category | None
    map_name: str | None
    environment: Environment
    players: list[AnalystPerson]
    coach: AnalystPerson | None
    valid_from: datetime | None
    valid_until: datetime | None
    is_active: bool
    status: Literal["active", "expired", "inactive", "scheduled"]
    created_at: datetime
    updated_at: datetime


class AnalystContextSide(BaseModel):
    relevant: list[AnalystFactorResponse]
    all_active: list[AnalystFactorResponse]


class AnalystContextResponse(BaseModel):
    team: str
    positive: list[dict]
    negative: list[dict]
