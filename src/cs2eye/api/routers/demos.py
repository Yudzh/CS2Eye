from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.api.schemas.demos import (
    DemoListResponse, DemoParseFileResult, DemoParseRequest, DemoParseResponse,
    DemoPlayerStatResponse, DemoPlayerStatsResponse, DemoUploadResponse,
    DemoTournamentOption,
)
from cs2eye.core.config import settings
from cs2eye.db.session import get_db_session
from cs2eye.services.demo_storage_service import DemoStorageService, make_tournament_slug
from cs2eye.services.demo_parse_service import DemoParseService
from cs2eye.models.demo import DemoParseRun, DemoPlayerStat
from cs2eye.models.demo_file import DemoFile


router = APIRouter(prefix="/demos", tags=["demos"])


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
    match_date: date = Form(...),
    files: list[UploadFile] = File(...),
    session: AsyncSession = Depends(get_db_session),
) -> DemoUploadResponse:
    name = validate_tournament_name(tournament_name)
    if not files:
        raise HTTPException(status_code=422, detail="At least one demo file is required.")
    return await DemoStorageService(
        session, settings.demo_storage_root, settings.demo_max_file_size_bytes,
        settings.demo_archive_max_depth,
    ).upload(name, match_date, files)


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
    return await DemoParseService(session, settings.demo_storage_root).parse_many(
        name, payload.year, payload.replace_existing,
    )


@router.post("/{demo_file_id}/parse", response_model=DemoParseFileResult)
async def parse_demo(
    demo_file_id: int,
    replace_existing: bool = Query(False),
    session: AsyncSession = Depends(get_db_session),
) -> DemoParseFileResult:
    result = await DemoParseService(session, settings.demo_storage_root).parse_by_id(
        demo_file_id, replace_existing,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Demo file not found.")
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
        ) for item in stats],
    )
