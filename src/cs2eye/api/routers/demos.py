from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.api.schemas.demos import (
    DemoListResponse, DemoParseFileResult, DemoParseJobResponse, DemoParseRequest, DemoParseResponse,
    DemoPlayerStatResponse, DemoPlayerStatsResponse, DemoUploadResponse,
    DemoTournamentOption,
    DemoRankReclassifyRequest, DemoRankReclassifyResponse,
    DemoMapResultPatch, DemoMapResultResponse, DemoMapTeamResponse,
    DemoMapWinnerResponse,
    DemoRoundsResponse, DemoRoundResponse, DemoSideStatsResponse,
    DemoTeamSideStatResponse, SideSummary, DemoBombStatsResponse, DemoTeamBombStatResponse,
    DemoEconomyStatsResponse, DemoTeamEconomyStatResponse, EconomyMetricResponse,
    DemoCombatStatsResponse, DemoUtilityStatsResponse,
)
from cs2eye.core.config import settings
from cs2eye.db.session import get_db_session
from cs2eye.services.demo_storage_service import DemoStorageService, make_tournament_slug
from cs2eye.services.demo_parse_service import DemoParseService
from cs2eye.services.demo_parse_job_service import demo_parse_job_manager
from cs2eye.models.demo import (
    DemoMapResult, DemoParseRun, DemoPlayerStat, DemoRound, DemoTeamBombStat,
    DemoTeamCombatStat, DemoTeamEconomyStat, DemoTeamSideStat, DemoTeamUtilityStat,
)
from cs2eye.models.team import Team
from cs2eye.models.demo_file import DemoFile
from cs2eye.services.opponent_rank_reclassify_service import (
    OpponentRankReclassifyService,
)
from cs2eye.services.demo_map_result_service import (
    ParsedMapResult, apply_to_model, normalize_parsed_map_result, refresh_validation,
)
from cs2eye.services.demo_round_service import recalculate_demo_team_side_stats
from cs2eye.services.team_map_aggregate_service import (
    recalculate_team_map, recalculate_demo_affected_aggregates,
    recalculate_demo_roster_aggregates,
)
from cs2eye.services.team_roster_service import rebuild_roster_links, resolve_demo_rosters
from cs2eye.services.match_service import MatchService, MatchValidationError


router = APIRouter(prefix="/demos", tags=["demos"])


class RosterRebuildRequest(BaseModel):
    demo_file_id: int | None = None
    team_id: int | None = None
    replace_existing: bool = False


class DemoEventTypeRequest(BaseModel):
    tournament_name: str
    event_type: Literal["online", "lan"]


@router.post("/assign-event-type")
async def assign_demo_event_type(
    payload: DemoEventTypeRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, int | str]:
    name = validate_tournament_name(payload.tournament_name)
    moved = await DemoStorageService(
        session, settings.demo_storage_root, settings.demo_max_file_size_bytes,
        settings.demo_archive_max_depth,
    ).assign_event_type(name, payload.event_type)
    return {"tournament_name": name, "event_type": payload.event_type, "moved": moved}


@router.post("/rebuild-roster-links")
async def rebuild_demo_roster_links(
    payload: RosterRebuildRequest, session: AsyncSession = Depends(get_db_session),
) -> dict:
    results = await rebuild_roster_links(
        session, demo_file_id=payload.demo_file_id, team_id=payload.team_id,
        replace_existing=payload.replace_existing,
    )
    aggregates = []
    for result in results:
        aggregates.extend(await recalculate_demo_roster_aggregates(session, result.demo_file_id))
    await session.commit()
    return {"demos_processed": len(results), "links_created": sum(x.links_created for x in results),
            "links_updated": sum(x.links_updated for x in results),
            "rosters_created": sum(x.rosters_created for x in results),
            "aggregates_recalculated": len(aggregates),
            "warnings": [warning for x in results for warning in x.warnings]}


def map_result_response(result: DemoMapResult, issues: list[str] | None = None) -> DemoMapResultResponse:
    return DemoMapResultResponse(
        demo_file_id=result.demo_file_id, map_name=result.map_name,
        team_a=DemoMapTeamResponse(id=result.team_a_id, name=result.team_a_name, score=result.team_a_score),
        team_b=DemoMapTeamResponse(id=result.team_b_id, name=result.team_b_name, score=result.team_b_score),
        winner=DemoMapWinnerResponse(id=result.winner_team_id, name=result.winner_team_name) if result.winner_team_name else None,
        rounds_count=result.rounds_count, went_to_overtime=result.went_to_overtime,
        result_source=result.result_source, metadata_status=result.metadata_status,
        issues=issues or [],
        round_data_status=result.round_data_status,
        bomb_data_status=result.bomb_data_status,
        economy_data_status=result.economy_data_status,
        combat_data_status=result.combat_data_status,
        utility_data_status=result.utility_data_status,
        rounds_parsed_count=result.rounds_parsed_count,
        rounds_expected_count=result.rounds_count,
        rounds_consistent=(
            result.round_data_status == "complete"
            and result.rounds_parsed_count == result.rounds_count
        ),
    )


def validate_tournament_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Tournament name must not be empty.")
    if not make_tournament_slug(name):
        raise HTTPException(status_code=422, detail="Tournament name cannot form a valid slug.")
    return value


@router.post("/upload", response_model=DemoUploadResponse)
async def upload_demos(
    tournament_name: str = Form(...),
    event_type: Literal["online", "lan"] = Form(...),
    match_date: date = Form(...),
    parse_after_upload: bool = Form(False),
    delete_after_successful_parse: bool = Form(False),
    files: list[UploadFile] = File(...),
    session: AsyncSession = Depends(get_db_session),
) -> DemoUploadResponse:
    name = validate_tournament_name(tournament_name)
    if not files:
        raise HTTPException(status_code=422, detail="At least one demo file is required.")
    result = await DemoStorageService(
        session, settings.demo_storage_root, settings.demo_max_file_size_bytes,
        settings.demo_archive_max_depth,
    ).upload(name, event_type, match_date, files)
    if parse_after_upload:
        # A failed upload has no id and is deliberately excluded. Unchanged
        # files are valid stored demos and may be parsed if still pending.
        demo_ids = [item.id for item in result.files if item.id is not None and item.status != "failed"]
        if demo_ids:
            job = demo_parse_job_manager.start_for_files(
                demo_ids, replace_existing=False,
                delete_after_successful_parse=delete_after_successful_parse,
            )
            result.parse_job_id, result.parse_job_status = job.job_id, job.status
    return result


@router.get("", response_model=DemoListResponse)
async def list_demos(
    tournament_name: str = Query(...),
    year: int = Query(..., ge=2000, le=2100),
    session: AsyncSession = Depends(get_db_session),
) -> DemoListResponse:
    name = validate_tournament_name(tournament_name)
    return await DemoStorageService(
        session, settings.demo_storage_root, settings.demo_max_file_size_bytes,
        settings.demo_archive_max_depth,
    ).list(name, year)


@router.get("/tournaments", response_model=list[DemoTournamentOption])
async def list_demo_tournaments(
    session: AsyncSession = Depends(get_db_session),
) -> list[DemoTournamentOption]:
    return await DemoStorageService(
        session, settings.demo_storage_root, settings.demo_max_file_size_bytes,
        settings.demo_archive_max_depth,
    ).list_tournaments()


@router.post("/parse", response_model=DemoParseResponse)
async def parse_demos(
    payload: DemoParseRequest,
    session: AsyncSession = Depends(get_db_session),
) -> DemoParseResponse:
    name = validate_tournament_name(payload.tournament_name)
    if not 2000 <= payload.year <= 2100:
        raise HTTPException(status_code=422, detail="Year must be between 2000 and 2100.")
    return await DemoParseService(
        session, settings.demo_storage_root,
        settings.demo_delete_after_successful_parse,
    ).parse_many(
        name, payload.year, payload.replace_existing,
    )


@router.post("/parse-all", response_model=DemoParseResponse)
async def parse_all_demos(
    session: AsyncSession = Depends(get_db_session),
) -> DemoParseResponse:
    try:
        return await DemoParseService(
            session, settings.demo_storage_root,
            settings.demo_delete_after_successful_parse,
        ).parse_all()
    except FileNotFoundError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


def _parse_job_payload(job) -> DemoParseJobResponse:
    return DemoParseJobResponse(
        job_id=job.job_id, status=job.status,
        processed_files=job.processed_files, total_files=job.total_files,
        parsed_count=job.parsed_count, skipped_count=job.skipped_count,
        failed_count=job.failed_count, current_filename=job.current_filename,
        error=job.error, result=job.result,
    )


@router.post("/parse-all/jobs", response_model=DemoParseJobResponse)
async def start_parse_all_job() -> DemoParseJobResponse:
    return _parse_job_payload(demo_parse_job_manager.start())


@router.get("/parse-all/jobs/{job_id}", response_model=DemoParseJobResponse)
async def get_parse_all_job(job_id: str) -> DemoParseJobResponse:
    job = demo_parse_job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Задача парсинга не найдена.")
    return _parse_job_payload(job)


@router.post("/parse/jobs", response_model=DemoParseJobResponse)
async def start_filtered_parse_job(
    payload: DemoParseRequest,
) -> DemoParseJobResponse:
    name = validate_tournament_name(payload.tournament_name)
    if not 2000 <= payload.year <= 2100:
        raise HTTPException(status_code=422, detail="Year must be between 2000 and 2100.")
    return _parse_job_payload(demo_parse_job_manager.start(
        tournament_name=name, year=payload.year,
        replace_existing=payload.replace_existing,
    ))


@router.post(
    "/reclassify-opponent-ranks",
    response_model=DemoRankReclassifyResponse,
)
async def reclassify_opponent_ranks(
    payload: DemoRankReclassifyRequest,
    session: AsyncSession = Depends(get_db_session),
) -> DemoRankReclassifyResponse:
    name = validate_tournament_name(payload.tournament_name)
    if not 2000 <= payload.year <= 2100:
        raise HTTPException(status_code=422, detail="Year must be between 2000 and 2100.")
    return await OpponentRankReclassifyService(session).reclassify_many(
        name,
        payload.year,
        only_unknown_or_fallback=payload.only_unknown_or_fallback,
    )


@router.post(
    "/{demo_file_id}/reclassify-opponent-ranks",
    response_model=DemoRankReclassifyResponse,
)
async def reclassify_demo_opponent_ranks(
    demo_file_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> DemoRankReclassifyResponse:
    result = await OpponentRankReclassifyService(session).reclassify_one(
        demo_file_id,
    )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Successfully parsed demo file not found.",
        )
    return result


@router.post("/{demo_file_id}/parse", response_model=DemoParseFileResult)
async def parse_demo(
    demo_file_id: int,
    replace_existing: bool = Query(False),
    session: AsyncSession = Depends(get_db_session),
) -> DemoParseFileResult:
    result = await DemoParseService(
        session, settings.demo_storage_root,
        settings.demo_delete_after_successful_parse,
    ).parse_by_id(
        demo_file_id, replace_existing,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Demo file not found.")
    if result[0].error == "source_demo_deleted_reupload_required":
        raise HTTPException(
            status_code=409, detail="source_demo_deleted_reupload_required",
        )
    return result[0]


@router.get("/{demo_file_id}/player-stats", response_model=DemoPlayerStatsResponse)
async def demo_player_stats(
    demo_file_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> DemoPlayerStatsResponse:
    demo = await session.get(DemoFile, demo_file_id)
    if demo is None:
        raise HTTPException(status_code=404, detail="Demo file not found.")
    run = (
        await session.execute(select(DemoParseRun).where(
            DemoParseRun.demo_file_id == demo_file_id,
        ))
    ).scalar_one_or_none()
    stats = (
        await session.execute(select(DemoPlayerStat).where(
            DemoPlayerStat.demo_file_id == demo_file_id,
        ).order_by(DemoPlayerStat.nickname))
    ).scalars().all()
    return DemoPlayerStatsResponse(
        demo_file_id=demo.id, filename=demo.original_filename,
        parse_status=run.status if run else "pending",
        players=[DemoPlayerStatResponse(
            player_id=item.player_id, steam_id=item.steam_id,
            nickname=item.nickname, team_name=item.team_name,
            rounds_played=item.rounds_played, kills=item.kills,
            deaths=item.deaths, assists=item.assists,
            total_damage=item.total_damage, adr=item.adr,
            kast_rounds=item.kast_rounds, kast_percent=item.kast_percent,
            internal_rating=item.internal_rating,
            internal_rating_version=item.internal_rating_version,
            demo_team_id=item.demo_team_id,
            demo_team_name=item.demo_team_name,
            opponent_team_id=item.opponent_team_id,
            opponent_team_name=item.opponent_team_name,
            opponent_rank=item.opponent_rank,
            opponent_rank_group=item.opponent_rank_group,
            opponent_rank_source=item.opponent_rank_source,
            opponent_rank_snapshot_date=item.opponent_rank_snapshot_date,
            combat=item.combat_data,
            utility=item.utility_data,
        ) for item in stats],
    )


@router.get("/{demo_file_id}/combat-stats", response_model=DemoCombatStatsResponse)
async def get_demo_combat_stats(
    demo_file_id: int, session: AsyncSession = Depends(get_db_session),
) -> DemoCombatStatsResponse:
    result = (await session.execute(select(DemoMapResult).where(
        DemoMapResult.demo_file_id == demo_file_id))).scalar_one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail="Demo map result not found.")
    teams = list((await session.execute(select(DemoTeamCombatStat).where(
        DemoTeamCombatStat.demo_file_id == demo_file_id).order_by(DemoTeamCombatStat.team_name))).scalars())
    players = list((await session.execute(select(DemoPlayerStat).where(
        DemoPlayerStat.demo_file_id == demo_file_id).order_by(DemoPlayerStat.nickname))).scalars())
    return DemoCombatStatsResponse(
        demo_file_id=demo_file_id, map_name=result.map_name,
        combat_data_status=result.combat_data_status,
        teams=[{"team_id": item.team_id, "team_name": item.team_name, **item.combat_data} for item in teams],
        players=[{"player_id": item.player_id, "nickname": item.nickname,
                  "team_id": item.demo_team_id, "team_name": item.demo_team_name,
                  **(item.combat_data or {})} for item in players],
    )


@router.get("/{demo_file_id}/utility-stats", response_model=DemoUtilityStatsResponse)
async def get_demo_utility_stats(demo_file_id: int, session: AsyncSession = Depends(get_db_session)) -> DemoUtilityStatsResponse:
    result = (await session.execute(select(DemoMapResult).where(DemoMapResult.demo_file_id == demo_file_id))).scalar_one_or_none()
    if result is None: raise HTTPException(status_code=404, detail="Demo map result not found.")
    teams = list((await session.execute(select(DemoTeamUtilityStat).where(
        DemoTeamUtilityStat.demo_file_id == demo_file_id).order_by(DemoTeamUtilityStat.team_name))).scalars())
    players = list((await session.execute(select(DemoPlayerStat).where(
        DemoPlayerStat.demo_file_id == demo_file_id).order_by(DemoPlayerStat.nickname))).scalars())
    return DemoUtilityStatsResponse(
        demo_file_id=demo_file_id, map_name=result.map_name, utility_data_status=result.utility_data_status,
        teams=[{"team_id": row.team_id, "team_name": row.team_name, **row.utility_data} for row in teams],
        players=[{"player_id": row.player_id, "nickname": row.nickname, "team_id": row.demo_team_id,
                  "team_name": row.demo_team_name, **(row.utility_data or {})} for row in players])


@router.get("/{demo_file_id}/map-result", response_model=DemoMapResultResponse)
async def get_demo_map_result(
    demo_file_id: int, session: AsyncSession = Depends(get_db_session),
) -> DemoMapResultResponse:
    result = (await session.execute(select(DemoMapResult).where(DemoMapResult.demo_file_id == demo_file_id))).scalar_one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail="Demo map result not found.")
    return map_result_response(result)


@router.patch("/{demo_file_id}/map-result", response_model=DemoMapResultResponse)
async def patch_demo_map_result(
    demo_file_id: int, payload: DemoMapResultPatch,
    session: AsyncSession = Depends(get_db_session),
) -> DemoMapResultResponse:
    demo = await session.get(DemoFile, demo_file_id)
    if demo is None:
        raise HTTPException(status_code=404, detail="Demo file not found.")
    current = (await session.execute(select(DemoMapResult).where(DemoMapResult.demo_file_id == demo_file_id))).scalar_one_or_none()
    old_pairs = ({(team_id, current.map_name) for team_id in (current.team_a_id, current.team_b_id)
                  if team_id is not None and current.map_name} if current else set())
    supplied = payload.model_fields_set
    def chosen(field: str):
        value = getattr(payload, field)
        return value if field in supplied else getattr(current, field, None)
    normalized = await normalize_parsed_map_result(session, ParsedMapResult(
        raw_map_name=chosen("map_name"), team_a_name=chosen("team_a_name"),
        team_a_score=chosen("team_a_score"), team_b_name=chosen("team_b_name"),
        team_b_score=chosen("team_b_score"),
    ))
    for side in ("a", "b"):
        id_field = f"team_{side}_id"
        requested_id = chosen(id_field)
        if requested_id is not None:
            team = await session.get(Team, requested_id)
            if team is None:
                raise HTTPException(status_code=422, detail=f"Team {requested_id} not found.")
            resolved = normalized.team_a if side == "a" else normalized.team_b
            object.__setattr__(resolved, "team_id", requested_id)
            object.__setattr__(resolved, "resolution_status", "matched")
    # IDs may change the winner link, while names remain authoritative for side/order.
    if normalized.winner_team_name == normalized.team_a.raw_name:
        normalized.winner_team_id = normalized.team_a.team_id
    elif normalized.winner_team_name == normalized.team_b.raw_name:
        normalized.winner_team_id = normalized.team_b.team_id
    refresh_validation(normalized)
    source = "manual_override" if not current or supplied.issuperset({"map_name", "team_a_name", "team_a_score", "team_b_name", "team_b_score"}) else "mixed"
    if current is None:
        current = DemoMapResult(demo_file_id=demo_file_id, result_source=source, metadata_status="partial")
        session.add(current)
    apply_to_model(current, normalized, source)
    round_sensitive_fields = {
        "team_a_id", "team_a_name", "team_a_score",
        "team_b_id", "team_b_name", "team_b_score",
    }
    if supplied.intersection(round_sensitive_fields):
        current.round_data_status = "needs_review"
        current.bomb_data_status = "needs_review"
        current.economy_data_status = "needs_review"
    stat_names = set((await session.execute(select(DemoPlayerStat.demo_team_name).where(DemoPlayerStat.demo_file_id == demo_file_id))).scalars().all())
    result_names = {current.team_a_name, current.team_b_name}
    issues = [issue.code for issue in normalized.issues]
    if {name for name in stat_names if name} and {name for name in stat_names if name} != {name for name in result_names if name}:
        issues.append("player_team_result_mismatch")
        if current.metadata_status == "complete": current.metadata_status = "needs_review"
    await session.flush()
    await resolve_demo_rosters(session, demo_file_id, replace_existing=True)
    new_pairs = {(team_id, current.map_name) for team_id in (current.team_a_id, current.team_b_id)
                 if team_id is not None and current.map_name}
    for team_id, map_name in old_pairs | new_pairs:
        await recalculate_team_map(session, team_id, map_name)
    await recalculate_demo_roster_aggregates(session, demo_file_id)
    try:
        await MatchService(session).auto_group_demo(demo_file_id)
    except MatchValidationError:
        pass
    await session.commit()
    await session.refresh(current)
    return map_result_response(current, issues)


@router.get("/{demo_file_id}/rounds", response_model=DemoRoundsResponse)
async def get_demo_rounds(
    demo_file_id: int, phase: str | None = Query(None), half: str | None = Query(None),
    winner_side: str | None = Query(None), page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_db_session),
) -> DemoRoundsResponse:
    result = (await session.execute(select(DemoMapResult).where(DemoMapResult.demo_file_id == demo_file_id))).scalar_one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail="Demo map result not found.")
    conditions = [DemoRound.demo_file_id == demo_file_id]
    if phase: conditions.append(DemoRound.phase == phase)
    if half: conditions.append(DemoRound.half == half)
    if winner_side: conditions.append(DemoRound.winner_side == winner_side.upper())
    total = (await session.execute(select(func.count(DemoRound.id)).where(*conditions))).scalar_one()
    rounds = list((await session.execute(select(DemoRound).where(*conditions).order_by(DemoRound.round_number).offset((page - 1) * page_size).limit(page_size))).scalars().all())
    return DemoRoundsResponse(
        demo_file_id=demo_file_id, round_data_status=result.round_data_status,
        total=total, page=page, page_size=page_size,
        items=[DemoRoundResponse.model_validate(item, from_attributes=True) for item in rounds],
    )


def side_stat_response(item: DemoTeamSideStat) -> DemoTeamSideStatResponse:
    return DemoTeamSideStatResponse(
        team_id=item.team_id, team_name=item.team_name,
        ct=SideSummary(rounds_played=item.ct_rounds_played, rounds_won=item.ct_rounds_won, rounds_lost=item.ct_rounds_lost, win_rate=item.ct_win_rate),
        t=SideSummary(rounds_played=item.t_rounds_played, rounds_won=item.t_rounds_won, rounds_lost=item.t_rounds_lost, win_rate=item.t_win_rate),
        first_half=SideSummary(rounds_played=item.first_half_rounds_played, rounds_won=item.first_half_rounds_won),
        second_half=SideSummary(rounds_played=item.second_half_rounds_played, rounds_won=item.second_half_rounds_won),
        overtime=SideSummary(rounds_played=item.overtime_rounds_played, rounds_won=item.overtime_rounds_won),
        total=SideSummary(rounds_played=item.total_rounds_played, rounds_won=item.total_rounds_won, rounds_lost=item.total_rounds_lost),
    )


@router.get("/{demo_file_id}/side-stats", response_model=DemoSideStatsResponse)
async def get_demo_side_stats(
    demo_file_id: int, session: AsyncSession = Depends(get_db_session),
) -> DemoSideStatsResponse:
    result = (await session.execute(select(DemoMapResult).where(DemoMapResult.demo_file_id == demo_file_id))).scalar_one_or_none()
    if result is None: raise HTTPException(status_code=404, detail="Demo map result not found.")
    stats = list((await session.execute(select(DemoTeamSideStat).where(DemoTeamSideStat.demo_file_id == demo_file_id).order_by(DemoTeamSideStat.id))).scalars().all())
    return DemoSideStatsResponse(demo_file_id=demo_file_id, map_name=result.map_name, round_data_status=result.round_data_status, teams=[side_stat_response(item) for item in stats])


def bomb_stat_response(item: DemoTeamBombStat) -> DemoTeamBombStatResponse:
    return DemoTeamBombStatResponse(
        team_id=item.team_id, team_name=item.team_name,
        t_rounds_played=item.t_rounds_played, plants=item.bomb_plants, plant_rate=item.plant_rate,
        postplant_rounds=item.postplant_rounds, postplant_wins=item.postplant_wins,
        postplant_losses=item.postplant_losses, postplant_win_rate=item.postplant_win_rate,
        retake_opportunities=item.retake_opportunities, retake_wins=item.retake_wins,
        retake_losses=item.retake_losses, retake_win_rate=item.retake_win_rate,
        explosions=item.bomb_explosions, defuses=item.bomb_defuses,
    )


@router.get("/{demo_file_id}/bomb-stats", response_model=DemoBombStatsResponse)
async def get_demo_bomb_stats(
    demo_file_id: int, session: AsyncSession = Depends(get_db_session),
) -> DemoBombStatsResponse:
    result = (await session.execute(select(DemoMapResult).where(DemoMapResult.demo_file_id == demo_file_id))).scalar_one_or_none()
    if result is None: raise HTTPException(status_code=404, detail="Demo map result not found.")
    stats = list((await session.execute(select(DemoTeamBombStat).where(
        DemoTeamBombStat.demo_file_id == demo_file_id,
    ).order_by(DemoTeamBombStat.id))).scalars().all())
    return DemoBombStatsResponse(
        demo_file_id=demo_file_id, map_name=result.map_name,
        bomb_data_status=result.bomb_data_status,
        teams=[bomb_stat_response(item) for item in stats],
    )


def _economy_metric(wins: int, rounds: int) -> EconomyMetricResponse:
    from decimal import Decimal
    rate = Decimal(wins) * 100 / Decimal(rounds) if rounds else None
    return EconomyMetricResponse(
        rounds=rounds, wins=wins, losses=rounds - wins,
        win_rate=rate.quantize(Decimal("0.0001")) if rate is not None else None,
    )


def economy_stat_response(item: DemoTeamEconomyStat) -> DemoTeamEconomyStatResponse:
    pairs = {
        "pistol": (item.pistol_rounds_won, item.pistol_rounds_played),
        "first_pistol": (item.first_pistol_wins, item.first_pistol_opportunities),
        "second_pistol": (item.second_pistol_wins, item.second_pistol_opportunities),
        "both_pistols": (item.both_pistols_wins, item.both_pistols_opportunities),
        "conversion": (item.pistol_conversions, item.pistol_conversion_opportunities),
        "post_pistol_vs_force": (item.post_pistol_vs_force_wins, item.post_pistol_vs_force_rounds),
        "second_round_comeback": (item.second_round_comeback_wins, item.second_round_comeback_opportunities),
        "eco": (item.eco_wins, item.eco_rounds),
        "force_buy": (item.force_buy_wins, item.force_buy_rounds),
        "full_buy": (item.full_buy_wins, item.full_buy_rounds),
        "anti_eco": (item.anti_eco_wins, item.anti_eco_rounds),
        "full_buy_vs_full_buy": (item.full_buy_vs_full_buy_wins, item.full_buy_vs_full_buy_rounds),
        "force_vs_full_buy": (item.force_vs_full_buy_wins, item.force_vs_full_buy_rounds),
    }
    return DemoTeamEconomyStatResponse(
        team_id=item.team_id, team_name=item.team_name,
        **{key: _economy_metric(*value) for key, value in pairs.items()},
        save_rounds=item.save_rounds, players_saved=item.players_saved,
        save_data_status=item.save_data_status,
    )


@router.get("/{demo_file_id}/economy-stats", response_model=DemoEconomyStatsResponse)
async def get_demo_economy_stats(
    demo_file_id: int, session: AsyncSession = Depends(get_db_session),
) -> DemoEconomyStatsResponse:
    result = (await session.execute(select(DemoMapResult).where(
        DemoMapResult.demo_file_id == demo_file_id,
    ))).scalar_one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail="Результат карты demo не найден.")
    stats = list((await session.execute(select(DemoTeamEconomyStat).where(
        DemoTeamEconomyStat.demo_file_id == demo_file_id,
    ).order_by(DemoTeamEconomyStat.id))).scalars())
    return DemoEconomyStatsResponse(
        demo_file_id=demo_file_id, map_name=result.map_name,
        economy_data_status=result.economy_data_status,
        teams=[economy_stat_response(item) for item in stats],
    )


@router.post("/{demo_file_id}/recalculate-side-stats", response_model=DemoSideStatsResponse)
async def recalculate_side_stats(
    demo_file_id: int, session: AsyncSession = Depends(get_db_session),
) -> DemoSideStatsResponse:
    result = (await session.execute(select(DemoMapResult).where(DemoMapResult.demo_file_id == demo_file_id))).scalar_one_or_none()
    if result is None: raise HTTPException(status_code=404, detail="Demo map result not found.")
    stats = await recalculate_demo_team_side_stats(session, result)
    await session.flush()
    await recalculate_demo_affected_aggregates(session, demo_file_id)
    await session.commit()
    return DemoSideStatsResponse(demo_file_id=demo_file_id, map_name=result.map_name, round_data_status=result.round_data_status, teams=[side_stat_response(item) for item in stats])
