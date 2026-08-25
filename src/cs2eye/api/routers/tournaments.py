from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.api.routers.matches import response as match_response
from cs2eye.api.schemas.matches import MatchResponse, TournamentResponse
from cs2eye.api.schemas.tournaments import (
    BracketLink, TournamentListItem, TournamentListResponse, TournamentPatchRequest,
    TournamentProblem, TournamentSummary, TournamentViewResponse,
)
from cs2eye.db.session import get_db_session
from cs2eye.services.tournament_view_service import TournamentNotFoundError, TournamentViewService


router = APIRouter(prefix="/tournaments", tags=["tournaments"])


def tournament_response(item) -> TournamentResponse:
    return TournamentResponse.model_validate(item, from_attributes=True)


async def build_view(service: TournamentViewService, tournament_id: int, session: AsyncSession) -> TournamentViewResponse:
    view = await service.view(tournament_id)
    matches = [await match_response(item, session) for item in view.matches]
    map_count = sum(len(item.maps) for item in matches)
    parsed_maps = sum(map_item.parse_status == "success" for item in matches for map_item in item.maps)
    problem_matches = {problem.match_id for problem in view.problems}
    summary = TournamentSummary(
        series_count=len(matches), map_count=map_count, parsed_maps=parsed_maps,
        review_series=len(problem_matches),
        missing_veto_series=sum(item.veto_data_status == "not_available" for item in matches),
    )
    return TournamentViewResponse(
        tournament=tournament_response(view.tournament), summary=summary, matches=matches,
        stages=list(dict.fromkeys(item.stage for item in matches)),
        bracket_links=[BracketLink(from_match_id=a, to_match_id=b, source=source) for a, b, source in view.links],
        problems=[TournamentProblem.model_validate(item, from_attributes=True) for item in view.problems],
    )


@router.get("", response_model=TournamentListResponse)
async def list_tournaments(session: AsyncSession = Depends(get_db_session)) -> TournamentListResponse:
    service = TournamentViewService(session)
    items = []
    for tournament in await service.list_tournaments():
        view = await build_view(service, tournament.id, session)
        items.append(TournamentListItem(**view.tournament.model_dump(), summary=view.summary))
    return TournamentListResponse(total=len(items), items=items)


@router.get("/{tournament_id}", response_model=TournamentResponse)
async def get_tournament(tournament_id: int, session: AsyncSession = Depends(get_db_session)) -> TournamentResponse:
    try: return tournament_response(await TournamentViewService(session).get(tournament_id))
    except TournamentNotFoundError as error: raise HTTPException(404, str(error)) from error


@router.get("/{tournament_id}/matches", response_model=list[MatchResponse])
async def get_tournament_matches(tournament_id: int, session: AsyncSession = Depends(get_db_session)) -> list[MatchResponse]:
    try: return (await build_view(TournamentViewService(session), tournament_id, session)).matches
    except TournamentNotFoundError as error: raise HTTPException(404, str(error)) from error


@router.get("/{tournament_id}/view", response_model=TournamentViewResponse)
async def get_tournament_view(tournament_id: int, session: AsyncSession = Depends(get_db_session)) -> TournamentViewResponse:
    try: return await build_view(TournamentViewService(session), tournament_id, session)
    except TournamentNotFoundError as error: raise HTTPException(404, str(error)) from error


@router.patch("/{tournament_id}", response_model=TournamentResponse)
async def patch_tournament(tournament_id: int, payload: TournamentPatchRequest, session: AsyncSession = Depends(get_db_session)) -> TournamentResponse:
    try:
        tournament = await TournamentViewService(session).update(tournament_id, **payload.model_dump(exclude_unset=True))
        await session.commit()
        return tournament_response(tournament)
    except TournamentNotFoundError as error:
        await session.rollback(); raise HTTPException(404, str(error)) from error
    except ValueError as error:
        await session.rollback(); raise HTTPException(422, str(error)) from error
