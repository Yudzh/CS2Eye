from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from cs2eye.api.schemas.teams import (
    TeamCreateRequest,
    TeamDetailResponse,
    TeamListItem,
    TeamListResponse,
    TeamRosterMemberResponse,
    TeamStrengthResponse, TeamCompareResponse, TeamRoleComparisonResponse,
)
from cs2eye.db.session import get_db_session
from cs2eye.services.team_service import (
    create_or_update_team_with_roster,
    get_team_detail,
    list_teams, compare_teams, compare_teams_by_names,
)

router = APIRouter(prefix="/teams", tags=["teams"])


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


def _build_team_detail_response(team) -> TeamDetailResponse:
    return TeamDetailResponse(
        id=team.id,
        name=team.name,
        country=team.country,
        region=team.region,
        liquipedia_url=team.liquipedia_url,
        hltv_id=team.hltv_id,
        roster=[
            TeamRosterMemberResponse(
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
            for item in team.roster
        ],
        strength=_build_strength_response(team.strength),
    )


@router.post(
    "",
    response_model=TeamDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_or_update_team_endpoint(
        request: TeamCreateRequest,
        session: AsyncSession = Depends(get_db_session),
) -> TeamDetailResponse:
    try:
        team = await create_or_update_team_with_roster(
            session=session,
            name=request.name,
            country=request.country,
            region=request.region,
            liquipedia_url=request.liquipedia_url,
            hltv_id=request.hltv_id,
            players=[
                player.model_dump()
                for player in request.players
            ],
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    return _build_team_detail_response(team)


@router.get(
    "",
    response_model=TeamListResponse,
)
async def list_teams_endpoint(
        session: AsyncSession = Depends(get_db_session),
) -> TeamListResponse:
    teams = await list_teams(session=session)

    return TeamListResponse(
        items=[
            TeamListItem(
                id=team.id,
                name=team.name,
                country=team.country,
                region=team.region,
                active_players_count=team.strength.active_players_count,
                team_strength_score=team.strength.team_strength_score,
            )
            for team in teams
        ],
        total=len(teams),
    )


@router.get(
    "/compare",
    response_model=TeamCompareResponse,
)
async def compare_teams_endpoint(
        team_a_id: UUID,
        team_b_id: UUID,
        session: AsyncSession = Depends(get_db_session),
) -> TeamCompareResponse:
    try:
        comparison = await compare_teams(
            session=session,
            team_a_id=team_a_id,
            team_b_id=team_b_id,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

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


@router.get(
    "/compare-by-names",
    response_model=TeamCompareResponse,
)
async def compare_teams_by_names_endpoint(
        team_a_name: str,
        team_b_name: str,
        session: AsyncSession = Depends(get_db_session),
) -> TeamCompareResponse:
    try:
        comparison = await compare_teams_by_names(
            session=session,
            team_a_name=team_a_name,
            team_b_name=team_b_name,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

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


@router.get(
    "/{team_id}",
    response_model=TeamDetailResponse,
)
async def get_team_detail_endpoint(
        team_id: UUID,
        session: AsyncSession = Depends(get_db_session),
) -> TeamDetailResponse:
    try:
        team = await get_team_detail(
            session=session,
            team_id=team_id,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    return _build_team_detail_response(team)


@router.get(
    "/{team_id}/strength",
    response_model=TeamStrengthResponse,
)
async def get_team_strength_endpoint(
        team_id: UUID,
        session: AsyncSession = Depends(get_db_session),
) -> TeamStrengthResponse:
    try:
        team = await get_team_detail(
            session=session,
            team_id=team_id,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    return _build_strength_response(team.strength)