from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.api.schemas.matches import (
    MatchBackfillResponse, MatchCreateRequest, MatchListResponse, MatchMapResponse, MatchPatchRequest, MatchReorderRequest,
    MatchResponse, MatchScoreResponse, MatchSplitRequest, MatchTeamResponse,
    TeamMatchStatsResponse, TournamentResponse,
)
from cs2eye.db.session import get_db_session
from cs2eye.services.match_service import (
    MatchNotFoundError, MatchService, MatchValidationError, MatchView,
)


router = APIRouter(tags=["matches"])


def response(view: MatchView) -> MatchResponse:
    item = view.match
    return MatchResponse(
        id=item.id,
        tournament=TournamentResponse.model_validate(view.tournament, from_attributes=True) if view.tournament else None,
        match_date=item.match_date, format=item.format, stage=item.stage, environment=item.environment,
        status=item.status, resolution_status=item.resolution_status, is_playoff=item.is_playoff,
        is_elimination=item.is_elimination,
        team_a=MatchTeamResponse(id=item.team_a_id, name=view.team_a.name if view.team_a else None),
        team_b=MatchTeamResponse(id=item.team_b_id, name=view.team_b.name if view.team_b else None),
        score=MatchScoreResponse(team_a=item.team_a_maps_won, team_b=item.team_b_maps_won),
        winner_team_id=item.winner_team_id,
        maps=[MatchMapResponse.model_validate(map_item, from_attributes=True) for map_item in view.maps],
    )


def expected_error(error: Exception) -> HTTPException:
    return HTTPException(status_code=404 if isinstance(error, MatchNotFoundError) else 422, detail=str(error))


@router.post("/matches/backfill", response_model=MatchBackfillResponse)
async def backfill_matches(session: AsyncSession = Depends(get_db_session)) -> MatchBackfillResponse:
    result = await MatchService(session).backfill()
    await session.commit()
    return MatchBackfillResponse.model_validate(result, from_attributes=True)


@router.get("/matches", response_model=MatchListResponse)
async def list_matches(
    team_id: int | None = Query(None), resolution_status: str | None = Query(None),
    session: AsyncSession = Depends(get_db_session),
) -> MatchListResponse:
    views = await MatchService(session).list(team_id=team_id, resolution_status=resolution_status)
    return MatchListResponse(total=len(views), items=[response(view) for view in views])


@router.get("/matches/{match_id}", response_model=MatchResponse)
async def get_match(match_id: int, session: AsyncSession = Depends(get_db_session)) -> MatchResponse:
    try: return response(await MatchService(session).get(match_id))
    except MatchNotFoundError as error: raise expected_error(error) from error


@router.post("/matches", response_model=MatchResponse)
async def create_match(payload: MatchCreateRequest, session: AsyncSession = Depends(get_db_session)) -> MatchResponse:
    try:
        view = await MatchService(session).create_manual(**payload.model_dump())
        await session.commit(); return response(view)
    except MatchValidationError as error:
        await session.rollback(); raise expected_error(error) from error


@router.patch("/matches/{match_id}", response_model=MatchResponse)
async def patch_match(match_id: int, payload: MatchPatchRequest, session: AsyncSession = Depends(get_db_session)) -> MatchResponse:
    try:
        view = await MatchService(session).update(match_id, **payload.model_dump(exclude_unset=True))
        await session.commit(); return response(view)
    except (MatchNotFoundError, MatchValidationError) as error:
        await session.rollback(); raise expected_error(error) from error


@router.post("/matches/{match_id}/reorder", response_model=MatchResponse)
async def reorder_match(match_id: int, payload: MatchReorderRequest, session: AsyncSession = Depends(get_db_session)) -> MatchResponse:
    try:
        view = await MatchService(session).reorder(match_id, payload.demo_file_ids)
        await session.commit(); return response(view)
    except (MatchNotFoundError, MatchValidationError) as error:
        await session.rollback(); raise expected_error(error) from error


@router.post("/matches/{match_id}/split", response_model=list[MatchResponse])
async def split_match(match_id: int, payload: MatchSplitRequest, session: AsyncSession = Depends(get_db_session)) -> list[MatchResponse]:
    try:
        views = await MatchService(session).split(match_id, payload.demo_file_ids)
        await session.commit(); return [response(view) for view in views]
    except (MatchNotFoundError, MatchValidationError) as error:
        await session.rollback(); raise expected_error(error) from error


@router.get("/analysis/teams/{team_id}/matches", response_model=TeamMatchStatsResponse)
async def team_match_stats(
    team_id: int, aggregation_level: str = Query("organization", pattern="^(organization|current_roster)$"),
    session: AsyncSession = Depends(get_db_session),
) -> TeamMatchStatsResponse:
    try:
        stats = await MatchService(session).team_stats(team_id, aggregation_level=aggregation_level)
    except MatchValidationError as error: raise HTTPException(status_code=404, detail=str(error)) from error
    def line(value): return {**value.__dict__, "match_win_rate": value.match_win_rate}
    return TeamMatchStatsResponse.model_validate({**stats.__dict__, "all": line(stats.all),
        "by_format": {key: line(value) for key, value in stats.by_format.items()},
        "by_context": {key: line(value) for key, value in stats.by_context.items()}})
