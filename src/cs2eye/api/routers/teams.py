from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.api.schemas.teams import (
    TeamListItem,
    TeamComparisonPlayerResponse,
    TeamComparisonResponse,
    TeamComparisonSideResponse,
    TeamRankingComparisonResponse,
    TeamRoleComparisonResponse,
    TeamDetailResponse,
    TeamParticipantResponse,
    TeamParticipantRoleUpdate,
    TeamStrengthResponse,
)
from cs2eye.db.session import get_db_session
from cs2eye.services.top_teams_service import (
    list_ranked_teams,
    list_active_rosters,
    get_team_with_roster,
)
from cs2eye.services.team_strength_service import calculate_team_strength
from cs2eye.services.team_comparison_service import (
    ComparisonSide,
    InactiveTeamError,
    SameTeamComparisonError,
    TeamComparisonService,
    TeamNotFoundError,
)
from cs2eye.models.team import Player, Team, TeamParticipantMembership, TeamRoster, TeamRosterMember


router = APIRouter(
    prefix="/teams",
    tags=["teams"],
)


@router.get("/{team_id}/rosters/current")
async def get_current_roster(team_id: int, session: AsyncSession = Depends(get_db_session)) -> dict:
    team = await session.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Команда не найдена.")
    roster = await session.get(TeamRoster, team.current_roster_id) if team.current_roster_id else None
    if roster is None or roster.resolution_status != "complete":
        return {"team_id": team.id, "team_name": team.name, "status": "current_roster_unavailable", "roster": None}
    rows = (await session.execute(
        select(TeamRosterMember, Player).outerjoin(Player, Player.id == TeamRosterMember.player_id)
        .where(TeamRosterMember.roster_id == roster.id).order_by(TeamRosterMember.id)
    )).all()
    return {"team_id": team.id, "team_name": team.name, "status": "available", "roster": {
        "id": roster.id, "active_from": roster.active_from,
        "active_from_source": roster.active_from_source, "resolution_status": roster.resolution_status,
        "players": [{"id": member.player_id, "name": player.nickname if player else member.player_name_snapshot,
                     "role": member.role_snapshot} for member, player in rows],
    }}


@router.get(
    "",
    response_model=list[TeamListItem],
)
async def get_teams(
    session: AsyncSession = Depends(
        get_db_session,
    ),
) -> list[TeamListItem]:
    teams = await list_ranked_teams(session)
    rosters = await list_active_rosters(session)
    return [
        TeamListItem(
            **TeamListItem.model_validate(team).model_dump(
                exclude={"roster"},
            ),
            roster=[
                TeamParticipantResponse(
                    id=player.id,
                    bo3_id=player.bo3_id,
                    bo3_slug=player.bo3_slug,
                    nickname=player.nickname,
                    image_url=player.image_url,
                    country_code=player.country_code,
                    country_name=player.country_name,
                    participant_type=participant_type,
                    player_strength=player.player_strength,
                    bo3_rating=player.bo3_rating,
                    bo3_avg_rating=player.bo3_rating,
                    internal_rating=player.internal_rating,
                    internal_rating_maps_count=player.internal_rating_maps_count,
                    internal_rating_rounds_count=player.internal_rating_rounds_count,
                    internal_rating_version=player.internal_rating_version,
                    internal_rating_top15=player.internal_rating_top15,
                    internal_rating_top15_maps_count=player.internal_rating_top15_maps_count,
                    internal_rating_top15_rounds_count=player.internal_rating_top15_rounds_count,
                    internal_rating_top16_30=player.internal_rating_top16_30,
                    internal_rating_top16_30_maps_count=player.internal_rating_top16_30_maps_count,
                    internal_rating_top16_30_rounds_count=player.internal_rating_top16_30_rounds_count,
                )
                for player, participant_type
                in rosters.get(team.id, [])
            ],
        )
        for team in teams
    ]


@router.get("/compare", response_model=TeamComparisonResponse)
async def compare_teams(
    team_a_id: int,
    team_b_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> TeamComparisonResponse:
    try:
        comparison = await TeamComparisonService(session).compare(
            team_a_id,
            team_b_id,
        )
    except SameTeamComparisonError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (TeamNotFoundError, InactiveTeamError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    def side_response(side: ComparisonSide) -> TeamComparisonSideResponse:
        team = side.team
        return TeamComparisonSideResponse(
            id=team.id,
            bo3_id=team.bo3_id,
            bo3_slug=team.bo3_slug,
            name=team.name,
            logo_url=team.logo_url,
            country_code=team.country_code,
            country_name=team.country_name,
            region=team.region,
            current_rank=team.current_rank,
            current_points=team.current_points,
            rank_change=team.rank_change,
            ranking_date=team.ranking_date,
            roster_synced_at=team.roster_synced_at,
            active_players_count=side.strength.active_players_count,
            roster=[
                TeamComparisonPlayerResponse.model_validate(
                    player, from_attributes=True,
                )
                for player in side.roster
            ],
            coaches=[
                TeamComparisonPlayerResponse.model_validate(
                    player, from_attributes=True,
                )
                for player in side.coaches
            ],
            strength=TeamStrengthResponse.model_validate(
                side.strength, from_attributes=True,
            ),
            relative_strength_percent=side.relative_strength_percent,
        )

    return TeamComparisonResponse(
        team_a=side_response(comparison.team_a),
        team_b=side_response(comparison.team_b),
        strength_advantage_team_id=comparison.strength_advantage_team_id,
        strength_advantage_team_name=comparison.strength_advantage_team_name,
        strength_advantage_diff=comparison.strength_advantage_diff,
        ranking=TeamRankingComparisonResponse.model_validate(
            comparison.ranking, from_attributes=True,
        ),
        role_comparisons=[
            TeamRoleComparisonResponse.model_validate(
                role, from_attributes=True,
            )
            for role in comparison.role_comparisons
        ],
        summary_notes=comparison.summary_notes,
    )


@router.get("/{team_id}", response_model=TeamDetailResponse)
async def get_team(
    team_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> TeamDetailResponse:
    team, roster = await get_team_with_roster(session, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Команда не найдена.")
    participants = [
        TeamParticipantResponse(
            id=player.id,
            bo3_id=player.bo3_id,
            bo3_slug=player.bo3_slug,
            nickname=player.nickname,
            image_url=player.image_url,
            country_code=player.country_code,
            country_name=player.country_name,
            participant_type=membership.participant_type,
            role=membership.role,
            is_active=membership.is_active,
            joined_at=membership.joined_at,
            left_at=membership.left_at,
            player_strength=player.player_strength,
            bo3_rating=player.bo3_rating,
            bo3_avg_rating=player.bo3_rating,
            internal_rating=player.internal_rating,
            internal_rating_maps_count=player.internal_rating_maps_count,
            internal_rating_rounds_count=player.internal_rating_rounds_count,
            internal_rating_version=player.internal_rating_version,
            internal_rating_top15=player.internal_rating_top15,
            internal_rating_top15_maps_count=player.internal_rating_top15_maps_count,
            internal_rating_top15_rounds_count=player.internal_rating_top15_rounds_count,
            internal_rating_top16_30=player.internal_rating_top16_30,
            internal_rating_top16_30_maps_count=player.internal_rating_top16_30_maps_count,
            internal_rating_top16_30_rounds_count=player.internal_rating_top16_30_rounds_count,
        )
        for player, membership in roster
    ]
    strength = calculate_team_strength(roster)
    return TeamDetailResponse(
        **TeamListItem.model_validate(team).model_dump(exclude={"roster"}),
        roster=participants,
        strength=TeamStrengthResponse.model_validate(
            strength,
            from_attributes=True,
        ),
    )


@router.patch(
    "/{team_id}/players/{player_id}/role",
    response_model=TeamDetailResponse,
)
async def update_player_role(
    team_id: int,
    player_id: int,
    payload: TeamParticipantRoleUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> TeamDetailResponse:
    membership = (
        await session.execute(
            select(TeamParticipantMembership).where(
                TeamParticipantMembership.team_id == team_id,
                TeamParticipantMembership.player_id == player_id,
                TeamParticipantMembership.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(
            status_code=404,
            detail="Активный игрок этой команды не найден.",
        )
    if membership.participant_type != "player":
        raise HTTPException(
            status_code=409,
            detail="Роль можно назначить только игроку основного состава.",
        )

    membership.role = payload.role
    await session.commit()
    return await get_team(team_id, session)
