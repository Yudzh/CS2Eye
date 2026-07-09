from pydantic import BaseModel

from cs2eye.api.schemas.demos import DemoTeamMapMatchupItem
from cs2eye.api.schemas.teams import TeamCompareResponse


class BettingDraftSignalResponse(BaseModel):
    edge_team_name: str | None
    edge_score: float

    bet_signal: str
    risk_level: str
    confidence_level: str

    explanation: str


class BettingPreMatchDraftResponse(BaseModel):
    team_a_name: str
    team_b_name: str
    map_name: str | None = None

    roster_comparison: TeamCompareResponse
    map_comparisons: list[DemoTeamMapMatchupItem]

    draft_signal: BettingDraftSignalResponse
    notes: list[str]

    total_maps_compared: int