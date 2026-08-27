from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.api.schemas.matches import (
    MatchBackfillResponse, MatchCreateRequest, MatchListResponse, MatchMapResponse, MatchPatchRequest, MatchReorderRequest,
    MatchResponse, MatchScoreResponse, MatchSplitRequest, MatchTeamResponse,
    TeamMatchStatsResponse, TournamentResponse, MatchVetoUpdateRequest,
)
from cs2eye.db.session import get_db_session
from cs2eye.services.match_service import (
    MatchNotFoundError, MatchService, MatchValidationError, MatchView,
)
from cs2eye.services.veto_service import VetoError, VetoService


router = APIRouter(tags=["matches"])


async def response(view: MatchView, session: AsyncSession) -> MatchResponse:
    item = view.match
    veto = await VetoService(session).actions(item.id)
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
        veto_data_status=item.veto_data_status,
        veto_expected=item.status != "scheduled" and item.resolution_status == "resolved" and item.format in {"bo1", "bo3", "bo5"} and item.team_a_id is not None and item.team_b_id is not None,
        veto=[{"id":a.id,"order_index":a.order_index,"team_id":a.team_id,"team_name":a.team_name,"action":a.action,"map_name":a.map_name,"source":a.source,"source_external_id":a.source_external_id} for a in veto],
        round_number=item.round_number, round_label=item.round_label,
        group_name=item.group_name, bracket_section=item.bracket_section,
        bracket_position=item.bracket_position, next_match_id=item.next_match_id,
        next_match_slot=item.next_match_slot,
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
    veto_filter: str | None = Query(None, pattern="^(expected_missing|has_veto)$"),
    session: AsyncSession = Depends(get_db_session),
) -> MatchListResponse:
    views = await MatchService(session).list(team_id=team_id, resolution_status=resolution_status, veto_filter=veto_filter)
    return MatchListResponse(total=len(views), items=[await response(view, session) for view in views])


@router.get("/matches/{match_id}", response_model=MatchResponse)
async def get_match(match_id: int, session: AsyncSession = Depends(get_db_session)) -> MatchResponse:
    try: return await response(await MatchService(session).get(match_id), session)
    except MatchNotFoundError as error: raise expected_error(error) from error


@router.post("/matches", response_model=MatchResponse)
async def create_match(payload: MatchCreateRequest, session: AsyncSession = Depends(get_db_session)) -> MatchResponse:
    try:
        view = await MatchService(session).create_manual(**payload.model_dump())
        await session.commit(); return await response(view, session)
    except MatchValidationError as error:
        await session.rollback(); raise expected_error(error) from error


@router.patch("/matches/{match_id}", response_model=MatchResponse)
async def patch_match(match_id: int, payload: MatchPatchRequest, session: AsyncSession = Depends(get_db_session)) -> MatchResponse:
    try:
        view = await MatchService(session).update(match_id, **payload.model_dump(exclude_unset=True))
        await session.commit(); return await response(view, session)
    except (MatchNotFoundError, MatchValidationError) as error:
        await session.rollback(); raise expected_error(error) from error


@router.post("/matches/{match_id}/reorder", response_model=MatchResponse)
async def reorder_match(match_id: int, payload: MatchReorderRequest, session: AsyncSession = Depends(get_db_session)) -> MatchResponse:
    try:
        view = await MatchService(session).reorder(match_id, payload.demo_file_ids)
        await session.commit(); return await response(view, session)
    except (MatchNotFoundError, MatchValidationError) as error:
        await session.rollback(); raise expected_error(error) from error


@router.post("/matches/{match_id}/split", response_model=list[MatchResponse])
async def split_match(match_id: int, payload: MatchSplitRequest, session: AsyncSession = Depends(get_db_session)) -> list[MatchResponse]:
    try:
        views = await MatchService(session).split(match_id, payload.demo_file_ids)
        await session.commit(); return [await response(view, session) for view in views]
    except (MatchNotFoundError, MatchValidationError) as error:
        await session.rollback(); raise expected_error(error) from error

@router.put("/matches/{match_id}/veto", response_model=MatchResponse)
async def put_match_veto(match_id: int, payload: MatchVetoUpdateRequest, session: AsyncSession = Depends(get_db_session)) -> MatchResponse:
    try:
        if payload.text is not None:
            await VetoService(session).replace_text(match_id, payload.text, status=payload.status)
        elif payload.actions is not None:
            await VetoService(session).replace(match_id, [a.model_dump() for a in payload.actions], status=payload.status, source="manual", source_external_id=payload.source_external_id)
        else:
            raise VetoError("Передайте text или actions.")
        await session.commit(); return await response(await MatchService(session).get(match_id), session)
    except VetoError as error:
        await session.rollback(); raise HTTPException(status_code=422, detail=str(error)) from error


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
