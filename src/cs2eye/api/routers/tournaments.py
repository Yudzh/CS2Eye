from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.api.routers.matches import response as match_response
from cs2eye.api.schemas.matches import MatchResponse, TournamentResponse
from cs2eye.api.schemas.tournaments import (
    BracketLink, TournamentCreateRequest, TournamentListItem, TournamentListResponse, TournamentPatchRequest,
    TournamentParticipant, TournamentScheduledMatchCreate,
    TournamentProblem, TournamentSummary, TournamentViewResponse,
    TournamentRosterOverrideCreate, TournamentRosterOverridePatch, TournamentRosterOverrideResponse,
)
from cs2eye.db.session import get_db_session
from cs2eye.models.match import Tournament, TournamentRosterOverride
from cs2eye.models.team import AnalystFactor
from cs2eye.services.effective_roster_service import EffectiveRosterService
from cs2eye.services.tournament_lineup_monitor import TournamentLineupMonitor
from cs2eye.services.tournament_view_service import TournamentNotFoundError, TournamentViewService
from cs2eye.services.team_import_service import TeamImportService
from cs2eye.services.match_service import MatchService
from cs2eye.services.tournament_prediction_service import TournamentPredictionError, TournamentPredictionService


router = APIRouter(prefix="/tournaments", tags=["tournaments"])

class TeamImportRequest(BaseModel):
    slug_or_url: str

@router.post("/import-team")
async def import_team(payload: TeamImportRequest, session: AsyncSession = Depends(get_db_session)):
    try:
        team = await TeamImportService(session).import_bo3(payload.slug_or_url); await session.commit()
        return {"id":team.id,"name":team.name,"bo3_id":team.bo3_id,"bo3_slug":team.bo3_slug,"is_analytics_active":team.is_analytics_active}
    except (ValueError, RuntimeError) as error:
        await session.rollback(); raise HTTPException(422, str(error)) from error


def tournament_response(item) -> TournamentResponse:
    return TournamentResponse.model_validate(item, from_attributes=True)


async def build_view(service: TournamentViewService, tournament_id: int, session: AsyncSession) -> TournamentViewResponse:
    view = await service.view(tournament_id)
    matches = [await match_response(item, session) for item in view.matches]
    map_count = sum(len(item.maps) for item in matches)
    parsed_maps = sum(map_item.parse_status == "success" for item in matches for map_item in item.maps)
    problem_matches = {problem.match_id for problem in view.problems}
    participants = await service.participants(tournament_id)
    summary = TournamentSummary(
        series_count=len(matches), map_count=map_count, parsed_maps=parsed_maps,
        review_series=len(problem_matches),
        missing_veto_series=sum(item.veto_data_status == "not_available" for item in matches),
        participant_count=len(participants), scheduled_series=sum(item.status == "scheduled" for item in matches),
    )
    return TournamentViewResponse(
        tournament=tournament_response(view.tournament), summary=summary, matches=matches,
        stages=list(dict.fromkeys(item.stage for item in matches)),
        bracket_links=[BracketLink(from_match_id=a, to_match_id=b, source=source) for a, b, source in view.links],
        problems=[TournamentProblem.model_validate(item, from_attributes=True) for item in view.problems],
        participants=[TournamentParticipant(team_id=link.team_id, name=team.name, seed=link.seed) for link, team in participants],
    )

@router.post("", response_model=TournamentResponse, status_code=201)
async def create_tournament(payload: TournamentCreateRequest, session: AsyncSession = Depends(get_db_session)) -> TournamentResponse:
    try:
        data = payload.model_dump(by_alias=False)
        matches = data.pop("matches")
        tournament = await TournamentViewService(session).create(**data, matches=matches)
        await session.commit()
        return tournament_response(tournament)
    except ValueError as error:
        await session.rollback()
        raise HTTPException(422, str(error)) from error

@router.post("/{tournament_id}/matches", response_model=MatchResponse, status_code=201)
async def create_scheduled_match(tournament_id: int, payload: TournamentScheduledMatchCreate,
        session: AsyncSession = Depends(get_db_session)) -> MatchResponse:
    try:
        service = TournamentViewService(session)
        tournament = await service.get(tournament_id)
        participants = {link.team_id for link, _ in await service.participants(tournament_id)}
        item = payload.model_dump()
        a, b, match_date = item["team_a_id"], item["team_b_id"], item["match_date"]
        if a is not None and a == b: raise ValueError("Team A и Team B должны отличаться.")
        if any(team_id is not None and team_id not in participants for team_id in (a, b)):
            raise ValueError("Обе команды матча должны входить в participants турнира.")
        if (tournament.start_date and match_date < tournament.start_date) or (tournament.end_date and match_date > tournament.end_date):
            raise ValueError("Дата матча должна находиться в пределах турнира.")
        view = await MatchService(session).create_scheduled(tournament_id=tournament_id,
            environment=tournament.environment, **item)
        await session.commit()
        return await match_response(view, session)
    except TournamentNotFoundError as error:
        await session.rollback(); raise HTTPException(404, str(error)) from error
    except ValueError as error:
        await session.rollback(); raise HTTPException(422, str(error)) from error


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


@router.post("/{tournament_id}/predictions/generate")
async def generate_tournament_predictions(tournament_id: int, session: AsyncSession = Depends(get_db_session)):
    try:
        service = TournamentPredictionService(session)
        await service.generate(tournament_id)
        await session.commit()
        return await service.latest(tournament_id)
    except TournamentPredictionError as error:
        await session.rollback()
        raise HTTPException(422, str(error)) from error


@router.get("/{tournament_id}/predictions")
async def get_tournament_predictions(tournament_id: int, session: AsyncSession = Depends(get_db_session)):
    if await session.get(Tournament, tournament_id) is None:
        raise HTTPException(404, "Турнир не найден.")
    return await TournamentPredictionService(session).latest(tournament_id)


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


@router.get("/{tournament_id}/roster-overrides", response_model=list[TournamentRosterOverrideResponse])
async def list_roster_overrides(tournament_id: int, team_id: int | None = None,
        session: AsyncSession = Depends(get_db_session)):
    query = select(TournamentRosterOverride).where(TournamentRosterOverride.tournament_id == tournament_id)
    if team_id is not None: query = query.where(TournamentRosterOverride.team_id == team_id)
    return list((await session.scalars(query.order_by(TournamentRosterOverride.team_id, TournamentRosterOverride.id))).all())


@router.post("/{tournament_id}/roster-overrides", response_model=TournamentRosterOverrideResponse, status_code=201)
async def create_roster_override(tournament_id: int, payload: TournamentRosterOverrideCreate,
        session: AsyncSession = Depends(get_db_session)):
    try:
        row = await EffectiveRosterService(session).create_manual(tournament_id, **payload.model_dump())
        await session.commit(); await session.refresh(row); return row
    except ValueError as error:
        await session.rollback(); raise HTTPException(422, str(error)) from error


@router.patch("/{tournament_id}/roster-overrides/{override_id}", response_model=TournamentRosterOverrideResponse)
async def patch_roster_override(tournament_id: int, override_id: int, payload: TournamentRosterOverridePatch,
        session: AsyncSession = Depends(get_db_session)):
    row = await session.get(TournamentRosterOverride, override_id)
    if row is None or row.tournament_id != tournament_id: raise HTTPException(404, "Override not found")
    changes = payload.model_dump(exclude_unset=True)
    if row.source_type == "AUTO" and changes.get("status") == "MANUAL":
        raise HTTPException(422, "Create a separate manual override instead")
    for key, value in changes.items(): setattr(row, key, value)
    if row.player_in_id == row.player_out_id:
        await session.rollback(); raise HTTPException(422, "player_in and player_out must differ")
    await session.commit(); await session.refresh(row); return row


@router.delete("/{tournament_id}/roster-overrides/{override_id}", status_code=204)
async def disable_roster_override(tournament_id: int, override_id: int,
        session: AsyncSession = Depends(get_db_session)):
    row = await session.get(TournamentRosterOverride, override_id)
    if row is None or row.tournament_id != tournament_id: raise HTTPException(404, "Override not found")
    row.is_active = False
    if row.analyst_factor_id:
        factor = await session.get(AnalystFactor, row.analyst_factor_id)
        if factor is not None: factor.is_active = False
    await session.commit()


@router.get("/{tournament_id}/teams/{team_id}/effective-roster")
async def get_effective_roster(tournament_id: int, team_id: int, match_id: int | None = None,
        as_of: date | None = None, session: AsyncSession = Depends(get_db_session)):
    try: return await EffectiveRosterService(session).get_effective_roster(team_id, tournament_id, match_id, as_of)
    except ValueError as error: raise HTTPException(422, str(error)) from error


@router.post("/{tournament_id}/teams/{team_id}/roster-overrides/check")
async def check_roster(tournament_id: int, team_id: int,
        session: AsyncSession = Depends(get_db_session)):
    try:
        result = await TournamentLineupMonitor(session).check(tournament_id, team_id)
        await session.commit(); return result
    except ValueError as error:
        await session.rollback(); raise HTTPException(422, str(error)) from error
