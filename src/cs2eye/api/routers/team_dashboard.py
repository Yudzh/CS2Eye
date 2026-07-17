from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.api.schemas.team_dashboard import (
    TeamComparisonDashboardResponse,
    TeamComparisonSideResponse,
    TeamDashboardMapResponse,
    TeamDashboardResponse,
    TeamHeadToHeadMapResponse,
    TeamMapComparisonResponse,
    TeamMapComparisonSideResponse,
    TeamRoleComparisonResponse,
    TeamRosterStateResponse,
    TeamSummaryListResponse,
    TeamSummaryResponse,
)
from cs2eye.api.schemas.teams import (
    TeamRosterMemberResponse,
    TeamStrengthResponse, TeamStrengthFactorResponse,
)
from cs2eye.db.session import get_db_session
from cs2eye.services.team_dashboard_service import (
    TeamComparisonSideInfo,
    TeamRosterStateInfo,
    calculate_relative_strength_percentages,
    compare_team_dashboards,
    get_team_dashboard,
    list_team_summaries,
)

router = APIRouter(
    prefix="/teams",
    tags=["team-dashboard"],
)


def _build_roster_state_response(
        roster_state: TeamRosterStateInfo,
) -> TeamRosterStateResponse:
    return TeamRosterStateResponse(
        code=roster_state.code,
        note=roster_state.note,
    )


def _build_strength_response(
        strength,
) -> TeamStrengthResponse:
    return TeamStrengthResponse(
        team_id=strength.team_id,
        team_name=strength.team_name,

        active_players_count=(
            strength.active_players_count
        ),

        base_player_score=(
            strength.base_player_score
        ),

        roster_bonus=(
            strength.roster_bonus
        ),

        roster_penalty=(
            strength.roster_penalty
        ),

        total_adjustment=(
            strength.total_adjustment
        ),

        score_before_limits=(
            strength.score_before_limits
        ),

        team_strength_score=(
            strength.team_strength_score
        ),

        calculation=(
            strength.calculation
        ),

        missing_required_roles=(
            strength.missing_required_roles
        ),

        factors=[
            TeamStrengthFactorResponse(
                code=factor.code,
                label=factor.label,
                kind=factor.kind,
                value=factor.value,
                explanation=(
                    factor.explanation
                ),
                players=factor.players,
            )
            for factor in strength.factors
        ],

        notes=strength.notes,
    )


def _build_roster_member_response(
        item,
) -> TeamRosterMemberResponse:
    return TeamRosterMemberResponse(
        roster_member_id=item.roster_member_id,
        player_id=item.player_id,
        nickname=item.nickname,
        real_name=item.real_name,
        country=item.country,
        status=item.status,
        role=item.role,
        joined_at=item.joined_at,
        left_at=item.left_at,
        current_rating=item.current_rating,
        player_strength_score=item.player_strength_score,
        source_name=item.source_name,
        source_url=item.source_url,
        source_confidence=item.source_confidence,
        notes=item.notes,
    )


def _build_comparison_side_response(
        side: TeamComparisonSideInfo,
) -> TeamComparisonSideResponse:
    return TeamComparisonSideResponse(
        team_id=side.strength.team_id,
        team_name=side.strength.team_name,
        active_players_count=side.strength.active_players_count,
        team_strength_score=side.strength.team_strength_score,
        relative_strength_percent=side.relative_strength_percent,
        roster_state=_build_roster_state_response(
            side.roster_state
        ),
    )


def _build_map_comparison_response(
        item,
) -> TeamMapComparisonResponse:
    has_both_samples = (
        item.team_a.total_matches_on_map > 0
        and item.team_b.total_matches_on_map > 0
    )

    if has_both_samples:
        team_a_percent, team_b_percent = (
            calculate_relative_strength_percentages(
                item.team_a.map_strength_score,
                item.team_b.map_strength_score,
            )
        )
    else:
        team_a_percent, team_b_percent = None, None

    return TeamMapComparisonResponse(
        map_name=item.map_name,
        team_a=TeamMapComparisonSideResponse(
            team_name=item.team_a.team_name,
            total_matches=item.team_a.total_matches_on_map,
            win_rate=item.team_a.win_rate_on_map,
            map_strength_score=item.team_a.map_strength_score,
            confidence_score=item.team_a.map_confidence_score,
            confidence_level=item.team_a.map_confidence_level,
            map_tier=item.team_a.map_tier,
        ),
        team_b=TeamMapComparisonSideResponse(
            team_name=item.team_b.team_name,
            total_matches=item.team_b.total_matches_on_map,
            win_rate=item.team_b.win_rate_on_map,
            map_strength_score=item.team_b.map_strength_score,
            confidence_score=item.team_b.map_confidence_score,
            confidence_level=item.team_b.map_confidence_level,
            map_tier=item.team_b.map_tier,
        ),
        team_a_relative_strength_percent=team_a_percent,
        team_b_relative_strength_percent=team_b_percent,
        advantage_team_name=item.advantage_team_name,
        advantage_score=item.advantage_score,
        matchup_confidence_level=item.matchup_confidence_level,
        recommendation=item.recommendation,
    )


@router.get(
    "/summaries",
    response_model=TeamSummaryListResponse,
)
async def list_team_summaries_endpoint(
        session: AsyncSession = Depends(get_db_session),
) -> TeamSummaryListResponse:
    teams = await list_team_summaries(session=session)

    return TeamSummaryListResponse(
        items=[
            TeamSummaryResponse(
                id=team.id,
                name=team.name,
                country=team.country,
                region=team.region,
                active_players_count=team.active_players_count,
                team_strength_score=team.team_strength_score,
                roster_state=_build_roster_state_response(
                    team.roster_state
                ),
            )
            for team in teams
        ],
        total=len(teams),
    )


@router.get(
    "/compare",
    response_model=TeamComparisonDashboardResponse,
)
async def compare_team_dashboards_endpoint(
        team_a_id: UUID,
        team_b_id: UUID,
        session: AsyncSession = Depends(get_db_session),
) -> TeamComparisonDashboardResponse:
    try:
        result = await compare_team_dashboards(
            session=session,
            team_a_id=team_a_id,
            team_b_id=team_b_id,
        )
    except ValueError as error:
        error_text = str(error)

        response_status = (
            status.HTTP_404_NOT_FOUND
            if "not found" in error_text.casefold()
            else status.HTTP_400_BAD_REQUEST
        )

        raise HTTPException(
            status_code=response_status,
            detail=error_text,
        ) from error

    comparison = result.comparison

    return TeamComparisonDashboardResponse(
        team_a=_build_comparison_side_response(
            result.team_a
        ),
        team_b=_build_comparison_side_response(
            result.team_b
        ),
        strength_advantage_team_name=(
            comparison.strength_advantage_team_name
        ),
        strength_advantage_diff=(
            comparison.strength_advantage_diff
        ),
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
        map_comparisons=[
            _build_map_comparison_response(item)
            for item in result.map_comparisons
        ],
        recent_head_to_head_maps=[
            TeamHeadToHeadMapResponse(
                parse_run_id=item.parse_run_id,
                tournament_name=item.tournament_name,
                match_date=item.match_date,
                map_name=item.map_name,
                map_number=item.map_number,
                team_a_name=item.team_a_name,
                team_b_name=item.team_b_name,
                team_a_rounds=item.team_a_rounds,
                team_b_rounds=item.team_b_rounds,
                winner_team_name=item.winner_team_name,
            )
            for item in result.recent_head_to_head_maps
        ],
        summary_notes=comparison.summary_notes,
    )


@router.get(
    "/{team_id}/dashboard",
    response_model=TeamDashboardResponse,
)
async def get_team_dashboard_endpoint(
        team_id: UUID,
        session: AsyncSession = Depends(get_db_session),
) -> TeamDashboardResponse:
    try:
        dashboard = await get_team_dashboard(
            session=session,
            team_id=team_id,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    team = dashboard.team

    return TeamDashboardResponse(
        id=team.id,
        name=team.name,
        country=team.country,
        region=team.region,
        liquipedia_url=team.liquipedia_url,
        hltv_id=team.hltv_id,
        roster_state=_build_roster_state_response(
            dashboard.roster_state
        ),
        roster=[
            _build_roster_member_response(item)
            for item in team.roster
        ],
        strength=_build_strength_response(
            team.strength
        ),
        maps=[
            TeamDashboardMapResponse(
                map_name=item.map_name,
                total_matches=item.total_matches_on_map,
                wins=item.wins_on_map,
                losses=item.losses_on_map,
                win_rate=item.win_rate_on_map,
                ct_win_rate=item.ct_win_rate,
                t_win_rate=item.t_win_rate,
                map_strength_score=item.map_strength_score,
                recent_form_score=item.recent_form_score,
                confidence_score=item.map_confidence_score,
                confidence_level=item.map_confidence_level,
                map_tier=item.map_tier,
                last_played_date=item.last_played_date_on_map,
                days_since_last_played=(
                    item.days_since_last_played_map
                ),
                is_strong_map=item.is_strong_map,
                is_weak_map=item.is_weak_map,
                is_permaban_map=item.is_permaban_map,
            )
            for item in dashboard.maps
        ],
    )