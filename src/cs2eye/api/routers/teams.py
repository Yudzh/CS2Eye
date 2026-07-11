import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.api.schemas.teams import (
    LiquipediaRosterPlayerPreview,
    LiquipediaTeamPreviewResponse,
    LiquipediaTeamRequest,
    LiquipediaTeamResponse,
    ManualRosterUpdateRequest,
    TeamDeleteResponse,
    TeamDetailResponse,
    TeamListResponse,
    TeamRosterMemberResponse,
    TeamStrengthResponse,
)
from cs2eye.db.session import get_db_session
from cs2eye.services.liquipedia_team_import_service import (
    fetch_liquipedia_team_roster,
    liquipedia_draft_to_team_payload,
)
from cs2eye.services.team_service import (
    create_or_update_team_with_roster,
    delete_team_by_name,
    get_team_detail_by_name,
    list_teams,
    update_team_roster_manually,
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


def _build_liquipedia_preview_response(draft) -> LiquipediaTeamPreviewResponse:
    return LiquipediaTeamPreviewResponse(
        team_name=draft.team_name,
        liquipedia_url=draft.liquipedia_url,
        players=[
            LiquipediaRosterPlayerPreview(
                nickname=item.nickname,
                real_name=item.real_name,
                country=item.country,
                status=item.status,
                role=item.role,
                joined_at=item.joined_at,
                left_at=item.left_at,
                liquipedia_url=item.liquipedia_url,
                source_url=item.source_url,
                source_confidence=item.source_confidence,
                notes=item.notes,
            )
            for item in draft.players
        ],
        warnings=draft.warnings,
        total_players=len(draft.players),
        active_players_count=sum(
            1
            for item in draft.players
            if item.status == "active"
        ),
    )


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
            _build_team_detail_response(team)
            for team in teams
        ],
        total=len(teams),
    )


@router.get(
    "/by-name",
    response_model=TeamDetailResponse,
)
async def get_team_by_name_endpoint(
        team_name: str,
        session: AsyncSession = Depends(get_db_session),
) -> TeamDetailResponse:
    try:
        team = await get_team_detail_by_name(
            session=session,
            team_name=team_name,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    return _build_team_detail_response(team)


@router.patch(
    "/by-name/roster",
    response_model=TeamDetailResponse,
)
async def update_team_roster_manually_endpoint(
        team_name: str,
        request: ManualRosterUpdateRequest,
        session: AsyncSession = Depends(get_db_session),
) -> TeamDetailResponse:
    try:
        team = await update_team_roster_manually(
            session=session,
            team_name=team_name,
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


@router.post(
    "/liquipedia",
    response_model=LiquipediaTeamResponse,
)
async def liquipedia_team_endpoint(
        request: LiquipediaTeamRequest,
        session: AsyncSession = Depends(get_db_session),
) -> LiquipediaTeamResponse:
    try:
        draft = await fetch_liquipedia_team_roster(
            team_page=request.team_page,
            team_name=request.team_name,
        )

        preview = _build_liquipedia_preview_response(draft)

        if not request.override_roster:
            return LiquipediaTeamResponse(
                saved=False,
                override_roster=False,
                preview=preview,
                team=None,
            )

        if preview.active_players_count < 5:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": "Liquipedia update aborted: найдено меньше 5 active-игроков. БД не обновлена.",
                    "team_name": preview.team_name,
                    "active_players_count": preview.active_players_count,
                    "total_players": preview.total_players,
                    "warnings": preview.warnings,
                },
            )

        payload = liquipedia_draft_to_team_payload(draft)

        team = await create_or_update_team_with_roster(
            session=session,
            name=payload["name"],
            country=payload["country"],
            region=payload["region"],
            liquipedia_url=payload["liquipedia_url"],
            hltv_id=payload["hltv_id"],
            players=payload["players"],
            delete_missing_current=True,
        )
    except httpx.TimeoutException as error:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={
                "message": "Liquipedia request timeout",
                "error_type": type(error).__name__,
                "error_repr": repr(error),
            },
        ) from error
    except httpx.HTTPStatusError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": "Liquipedia returned bad status",
                "status_code": error.response.status_code,
                "body_start": error.response.text[:500],
            },
        ) from error
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": "Liquipedia request failed",
                "error_type": type(error).__name__,
                "error_repr": repr(error),
            },
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    return LiquipediaTeamResponse(
        saved=True,
        override_roster=True,
        preview=preview,
        team=_build_team_detail_response(team),
    )


@router.delete(
    "/by-name",
    response_model=TeamDeleteResponse,
)
async def delete_team_by_name_endpoint(
        team_name: str,
        session: AsyncSession = Depends(get_db_session),
) -> TeamDeleteResponse:
    try:
        deleted_team_name = await delete_team_by_name(
            session=session,
            team_name=team_name,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    return TeamDeleteResponse(
        deleted=True,
        team_name=deleted_team_name,
    )