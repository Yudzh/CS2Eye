from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


TeamRoleCode = Literal[
    "igl",
    "awper",
    "rifler",
    "entry_frag",
    "lurk",
    "anchor_support",
    "coach",
]


class TeamRoleOptionResponse(BaseModel):
    value: TeamRoleCode
    label: str

    allowed_statuses: list[
        Literal["active", "coach"]
    ]

class TeamRosterMemberResponse(BaseModel):
    roster_member_id: UUID

    player_id: UUID
    nickname: str
    real_name: str | None
    country: str | None

    status: str
    role: str | None

    joined_at: date | None
    left_at: date | None

    current_rating: float | None
    player_strength_score: float

    source_name: str | None
    source_url: str | None
    source_confidence: float

    notes: str | None


class TeamStrengthResponse(BaseModel):
    team_id: UUID
    team_name: str

    active_players_count: int
    base_player_score: float

    roster_bonus: float
    roster_penalty: float

    team_strength_score: float

    missing_required_roles: list[str]
    notes: list[str]


class TeamDetailResponse(BaseModel):
    id: UUID
    name: str
    country: str | None
    region: str | None
    liquipedia_url: str | None
    hltv_id: int | None

    roster: list[TeamRosterMemberResponse]
    strength: TeamStrengthResponse


class TeamListResponse(BaseModel):
    items: list[TeamDetailResponse]
    total: int


class ManualRosterPlayerUpdate(BaseModel):
    nickname: str

    # 0 = добавить/обновить игрока в составе
    # 1 = удалить игрока из состава команды
    delete: int = Field(default=0, ge=0, le=1)

    # Допустимые роли:
    # igl, awper, entry_frag, lurk, anchor_support, coach
    # Также сервис принимает алиасы: IGL, AWPer, Entry Frag, Lurk, Anchor/Support, Тренер
    role: str | None = None

    real_name: str | None = None
    country: str | None = None

    joined_at: date | None = None
    left_at: date | None = None

    liquipedia_url: str | None = None
    hltv_id: int | None = None

    current_rating: float | None = None
    player_strength_score: float | None = Field(default=None, ge=0, le=100)

    notes: str | None = None


class ManualRosterUpdateRequest(BaseModel):
    players: list[ManualRosterPlayerUpdate]


class LiquipediaRoleAssignment(BaseModel):
    nickname: str = Field(min_length=1)
    role: TeamRoleCode


class LiquipediaTeamRequest(BaseModel):
    team_page: str = Field(min_length=1)
    team_name: str | None = None

    # false — только предпросмотр
    # true — сохранить/обновить команду
    override_roster: bool = False

    # При preview список пустой.
    # При сохранении UI передаёт выбранные роли.
    role_assignments: list[
        LiquipediaRoleAssignment
    ] = Field(default_factory=list)


class LiquipediaRosterPlayerPreview(BaseModel):
    nickname: str
    real_name: str | None
    country: str | None
    status: str
    role: str | None

    joined_at: date | None = None
    left_at: date | None = None

    liquipedia_url: str | None
    source_url: str
    source_confidence: float
    notes: str | None


class LiquipediaTeamPreviewResponse(BaseModel):
    team_name: str
    liquipedia_url: str

    players: list[
        LiquipediaRosterPlayerPreview
    ]

    warnings: list[str]

    role_options: list[
        TeamRoleOptionResponse
    ]

    total_players: int
    active_players_count: int


class LiquipediaTeamResponse(BaseModel):
    saved: bool
    override_roster: bool
    preview: LiquipediaTeamPreviewResponse
    team: TeamDetailResponse | None = None


class TeamDeleteResponse(BaseModel):
    deleted: bool
    team_name: str