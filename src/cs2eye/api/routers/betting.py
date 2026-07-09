from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from cs2eye.api.schemas.betting import (
    BettingDraftSignalResponse,
    BettingPreMatchDraftResponse,
)
from cs2eye.api.schemas.demos import (
    DemoTeamMapMatchupItem,
    DemoTeamMapMatchupTeamStats,
)
from cs2eye.api.schemas.teams import (
    TeamCompareResponse,
    TeamRoleComparisonResponse,
    TeamStrengthResponse,
)
from cs2eye.db.session import get_db_session
from cs2eye.services.betting_pre_match_draft_service import build_pre_match_draft

router = APIRouter(prefix="/betting", tags=["betting"])


def _build_strength_response(strength) -> TeamStrengthResponse:
    return TeamStrengthResponse(
        team_id=strength.team_id,
        team_name=strength.team_name,
        active_players_count=strength.active_players_count,
        base_player_score=strength.base_player_score,
        roster_bonus=strength.roster_bonus,
        roster_penalty=strength.roster_penalty,
        team_strength_score=strength.team_strength_score,
        missing_required_roles=strength.missing_required_roles,
        notes=strength.notes,
    )


def _build_team_compare_response(comparison) -> TeamCompareResponse:
    return TeamCompareResponse(
        team_a=_build_strength_response(comparison.team_a),
        team_b=_build_strength_response(comparison.team_b),
        strength_advantage_team_name=comparison.strength_advantage_team_name,
        strength_advantage_diff=comparison.strength_advantage_diff,
        role_comparisons=[
            TeamRoleComparisonResponse(
                role=item.role,
                team_a_score=item.team_a_score,
                team_b_score=item.team_b_score,
                team_a_players=item.team_a_players,
                team_b_players=item.team_b_players,
                advantage_team_name=item.advantage_team_name,
                advantage_diff=item.advantage_diff,
                note=item.note,
            )
            for item in comparison.role_comparisons
        ],
        summary_notes=comparison.summary_notes,
    )


def _build_map_team_stats(item) -> DemoTeamMapMatchupTeamStats:
    return DemoTeamMapMatchupTeamStats(
        team_name=item.team_name,
        map_name=item.map_name,
        total_matches_on_map=item.total_matches_on_map,
        win_rate_on_map=item.win_rate_on_map,
        ct_win_rate=item.ct_win_rate,
        t_win_rate=item.t_win_rate,
        avg_bomb_plants_per_map=item.avg_bomb_plants_per_map,
        avg_bomb_explosions_per_map=item.avg_bomb_explosions_per_map,
        avg_bomb_defuses_per_map=item.avg_bomb_defuses_per_map,
        map_strength_score=item.map_strength_score,
        map_confidence_score=item.map_confidence_score,
        map_confidence_level=item.map_confidence_level,
        map_tier=item.map_tier,
    )


def _build_map_matchup_item(item) -> DemoTeamMapMatchupItem:
    return DemoTeamMapMatchupItem(
        map_name=item.map_name,
        team_a=_build_map_team_stats(item.team_a),
        team_b=_build_map_team_stats(item.team_b),
        advantage_team_name=item.advantage_team_name,
        advantage_score=item.advantage_score,
        matchup_confidence_level=item.matchup_confidence_level,
        recommendation=item.recommendation,
    )


@router.get(
    "/pre-match-draft",
    response_model=BettingPreMatchDraftResponse,
)
async def get_pre_match_draft_endpoint(
        team_a_name: str,
        team_b_name: str,
        map_name: str | None = None,
        session: AsyncSession = Depends(get_db_session),
) -> BettingPreMatchDraftResponse:
    try:
        draft = await build_pre_match_draft(
            session=session,
            team_a_name=team_a_name,
            team_b_name=team_b_name,
            map_name=map_name,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    return BettingPreMatchDraftResponse(
        team_a_name=draft.team_a_name,
        team_b_name=draft.team_b_name,
        map_name=draft.map_name,
        roster_comparison=_build_team_compare_response(draft.roster_comparison),
        map_comparisons=[
            _build_map_matchup_item(item)
            for item in draft.map_matchup.items
        ],
        draft_signal=BettingDraftSignalResponse(
            edge_team_name=draft.draft_signal.edge_team_name,
            edge_score=draft.draft_signal.edge_score,
            bet_signal=draft.draft_signal.bet_signal,
            risk_level=draft.draft_signal.risk_level,
            confidence_level=draft.draft_signal.confidence_level,
            explanation=draft.draft_signal.explanation,
        ),
        notes=draft.notes,
        total_maps_compared=len(draft.map_matchup.items),
    )