from datetime import date
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Form
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status
from starlette.concurrency import run_in_threadpool

from cs2eye.api.schemas.demos import DemoListResponse, DemoUploadResponse, DemoArtifactPrepareResponse, \
    DemoArtifactPrepareRequest, DemoBasicStatsAnalyzeResponse, DemoBasicStatsAnalyzeRequest, \
    DemoBombRoundStats, DemoBombRoundStatsResponse, DemoBombAnalysisResponse, DemoBombAnalysisMeeting, PreparedDemoFile, \
    DemoPreparedPathAnalyzeRequest, DemoUploadAnalyzeItem, DemoUploadAnalyzeResponse, DemoParseDataClearResponse, \
    DemoLocalPathImportResponse, DemoLocalPathImportRequest, DemoLocalPathImportItem, DemoBombAnalysisMap
from cs2eye.db.session import get_db_session
from cs2eye.services.demo_artifact_extractor import prepare_demo_artifact, DemoArtifactExtractionError
from cs2eye.services.demo_artifact_storage import save_uploaded_demo_artifact, DemoArtifactStorageError
from cs2eye.services.demo_basic_stats_analyzer import analyze_demo_basic_stats, DemoBasicStatsAnalyzeError
from cs2eye.services.demo_bomb_analysis_service import get_bomb_analysis
from cs2eye.services.demo_filename_metadata import build_prepared_demo_file_metadata
from cs2eye.services.demo_parse_run_service import create_demo_parse_run, mark_demo_parse_run_failed, \
    mark_demo_parse_run_success, get_demo_bomb_round_stats, clear_demo_parse_data, delete_existing_demo_parse_runs

router = APIRouter(prefix="/demos", tags=["demos"])

PROJECT_ROOT = Path(".").resolve()

def _resolve_project_local_path(raw_path: str) -> Path:
    path = Path(raw_path)

    if not path.is_absolute():
        path = PROJECT_ROOT / path

    resolved_path = path.resolve()

    try:
        resolved_path.relative_to(PROJECT_ROOT)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path must be inside project directory",
        ) from error

    if not resolved_path.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Path does not exist: {raw_path}",
        )

    return resolved_path


def _collect_demo_files_from_local_path(path: Path) -> list[Path]:
    if path.is_file():
        if path.suffix.lower() != ".dem":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must have .dem extension",
            )

        return [path]

    if path.is_dir():
        return sorted(
            demo_file
            for demo_file in path.rglob("*.dem")
            if demo_file.is_file()
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Path must be a .dem file or a directory",
    )

async def _analyze_prepared_demo_file(
        *,
        session: AsyncSession,
        demo_file_path: str,
        artifact_id: str | None,
        demo_file_name: str | None,
        tournament_name: str | None,
        match_date: date | None,
        map_name: str | None,
        map_number: int | None,
        team_a_name: str | None,
        team_b_name: str | None,
) -> DemoBasicStatsAnalyzeResponse:
    parse_run = await create_demo_parse_run(
        session=session,
        demo_file_path=demo_file_path,
        artifact_id=artifact_id,
        demo_file_name=demo_file_name,
        tournament_name=tournament_name,
        match_date=match_date,
        map_name=map_name,
        map_number=map_number,
        team_a_name=team_a_name,
        team_b_name=team_b_name,
    )

    try:
        stats = await run_in_threadpool(
            analyze_demo_basic_stats,
            demo_file_path,
        )
    except DemoBasicStatsAnalyzeError as error:
        await mark_demo_parse_run_failed(
            session=session,
            parse_run=parse_run,
            error_message=str(error),
        )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    parse_run = await mark_demo_parse_run_success(
        session=session,
        parse_run=parse_run,
        demo_file_path=str(stats.demo_file_path),
        rounds_count=stats.rounds,
        bomb_rounds=stats.bomb_rounds,
    )

    return DemoBasicStatsAnalyzeResponse(
        parse_run_id=parse_run.id,
        demo_file_path=str(stats.demo_file_path),
        map_name=parse_run.map_name,
        map_number=parse_run.map_number,
        team_a_name=parse_run.team_a_name,
        team_b_name=parse_run.team_b_name,
        rounds=stats.rounds,
        bomb_rounds=[
            DemoBombRoundStats(
                round_number=bomb_round.round_number,
                planter_name=bomb_round.planter_name,
                planter_team_name=bomb_round.planter_team_name,
                defuser_name=bomb_round.defuser_name,
                defuser_team_name=bomb_round.defuser_team_name,
                outcome=bomb_round.outcome,
                plant_tick=bomb_round.plant_tick,
                defuse_tick=bomb_round.defuse_tick,
                explosion_tick=bomb_round.explosion_tick,
            )
            for bomb_round in stats.bomb_rounds
        ],
        status="analyzed",
    )


async def _analyze_demo_file_and_save_bomb_stats(
        *,
        session: AsyncSession,
        demo_file_path: str,
        tournament_name: str | None = None,
        match_date: date | None = None,
        map_name: str | None = None,
        map_number: int | None = None,
        team_a_name: str | None = None,
        team_b_name: str | None = None,
        artifact_id: str | None = None,
        demo_file_name: str | None = None,
) -> DemoBasicStatsAnalyzeResponse:
    parse_run = await create_demo_parse_run(
        session=session,
        demo_file_path=demo_file_path,
        artifact_id=artifact_id,
        demo_file_name=demo_file_name,
        tournament_name=tournament_name,
        match_date=match_date,
        map_name=map_name,
        map_number=map_number,
        team_a_name=team_a_name,
        team_b_name=team_b_name,
    )

    try:
        stats = await run_in_threadpool(
            analyze_demo_basic_stats,
            demo_file_path,
        )
    except DemoBasicStatsAnalyzeError as error:
        await mark_demo_parse_run_failed(
            session=session,
            parse_run=parse_run,
            error_message=str(error),
        )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    parse_run = await mark_demo_parse_run_success(
        session=session,
        parse_run=parse_run,
        demo_file_path=str(stats.demo_file_path),
        rounds_count=stats.rounds,
        bomb_rounds=stats.bomb_rounds,
    )

    return DemoBasicStatsAnalyzeResponse(
        parse_run_id=parse_run.id,
        demo_file_path=str(stats.demo_file_path),
        map_name=parse_run.map_name,
        map_number=parse_run.map_number,
        team_a_name=parse_run.team_a_name,
        team_b_name=parse_run.team_b_name,
        rounds=stats.rounds,
        bomb_rounds=[
            DemoBombRoundStats(
                round_number=bomb_round.round_number,
                planter_name=bomb_round.planter_name,
                planter_team_name=bomb_round.planter_team_name,
                defuser_name=bomb_round.defuser_name,
                defuser_team_name=bomb_round.defuser_team_name,
                outcome=bomb_round.outcome,
                plant_tick=bomb_round.plant_tick,
                defuse_tick=bomb_round.defuse_tick,
                explosion_tick=bomb_round.explosion_tick,
            )
            for bomb_round in stats.bomb_rounds
        ],
        status="analyzed",
    )


@router.get("", response_model=DemoListResponse)
async def list_demos() -> DemoListResponse:
    return DemoListResponse()


@router.get(
    "/parse-runs/{parse_run_id}/bomb-rounds",
    response_model=DemoBombRoundStatsResponse,
)
async def get_demo_bomb_rounds(
        parse_run_id: UUID,
        session: AsyncSession = Depends(get_db_session),
) -> DemoBombRoundStatsResponse:
    bomb_rounds = await get_demo_bomb_round_stats(
        session=session,
        parse_run_id=parse_run_id,
    )

    return DemoBombRoundStatsResponse(
        parse_run_id=parse_run_id,
        items=[
            DemoBombRoundStats(
                round_number=bomb_round.round_number,
                planter_name=bomb_round.planter_name,
                planter_team_name=bomb_round.planter_team_name,
                defuser_name=bomb_round.defuser_name,
                defuser_team_name=bomb_round.defuser_team_name,
                outcome=bomb_round.outcome,
                plant_tick=bomb_round.plant_tick,
                defuse_tick=bomb_round.defuse_tick,
                explosion_tick=bomb_round.explosion_tick,
            )
            for bomb_round in bomb_rounds
        ],
        total=len(bomb_rounds),
    )


@router.get(
    "/analysis/bombs",
    response_model=DemoBombAnalysisResponse,
)
async def get_demo_bomb_analysis_endpoint(
        map_name: str | None = None,
        team_a_name: str | None = None,
        team_b_name: str | None = None,
        session: AsyncSession = Depends(get_db_session),
) -> DemoBombAnalysisResponse:
    if (team_a_name is None) != (team_b_name is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="team_a_name and team_b_name must be provided together",
        )

    if map_name is None and team_a_name is None and team_b_name is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at least map_name or both team_a_name and team_b_name",
        )

    analysis = await get_bomb_analysis(
        session=session,
        map_name=map_name,
        team_a_name=team_a_name,
        team_b_name=team_b_name,
    )

    return DemoBombAnalysisResponse(
        map_name=analysis.map_name,
        team_a_name=analysis.team_a_name,
        team_b_name=analysis.team_b_name,
        maps=[
            DemoBombAnalysisMap(
                map_name=item.map_name,
                matches_count=item.matches_count,
                exploded_bombs=item.exploded_bombs,
                defused_bombs=item.defused_bombs,
                average_exploded_bombs_per_map=item.average_exploded_bombs_per_map,
                average_defused_bombs_per_map=item.average_defused_bombs_per_map,
            )
            for item in analysis.maps
        ],
        recent_meetings=[
            DemoBombAnalysisMeeting(
                parse_run_id=meeting.parse_run_id,
                demo_file_path=meeting.demo_file_path,
                tournament_name=meeting.tournament_name,
                match_date=meeting.match_date,
                map_name=meeting.map_name,
                map_number=meeting.map_number,
                team_a_name=meeting.team_a_name,
                team_b_name=meeting.team_b_name,
                rounds_count=meeting.rounds_count,
                exploded_bombs=meeting.exploded_bombs,
                defused_bombs=meeting.defused_bombs,
            )
            for meeting in analysis.recent_meetings
        ],
    )


@router.post("/upload/analyze", response_model=DemoUploadAnalyzeResponse)
async def upload_prepare_and_analyze_demo_artifact(
        file: UploadFile = File(...),
        tournament_name: str = Form(...),
        match_date: date = Form(...),
        session: AsyncSession = Depends(get_db_session),
) -> DemoUploadAnalyzeResponse:
    try:
        saved_artifact = await save_uploaded_demo_artifact(
            file=file,
            tournament_name=tournament_name,
            match_date=match_date,
        )
    except DemoArtifactStorageError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    try:
        prepared_artifact = prepare_demo_artifact(saved_artifact.stored_filename)
    except DemoArtifactExtractionError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    items: list[DemoUploadAnalyzeItem] = []

    for demo_file in prepared_artifact.demo_files:
        metadata = build_prepared_demo_file_metadata(demo_file)

        if not metadata.metadata_detected_from_filename:
            items.append(
                DemoUploadAnalyzeItem(
                    demo_file_path=str(metadata.demo_file_path),
                    file_name=metadata.file_name,
                    status="failed",
                    error_message=(
                        "Could not detect metadata from demo filename. "
                        "Expected format: team-a-vs-team-b-m1-map.dem"
                    ),
                )
            )
            continue

        try:
            analyzed = await _analyze_prepared_demo_file(
                session=session,
                demo_file_path=str(metadata.demo_file_path),
                artifact_id=metadata.artifact_id,
                demo_file_name=metadata.file_name,
                tournament_name=tournament_name,
                match_date=match_date,
                map_name=metadata.detected_map_name,
                map_number=metadata.detected_map_number,
                team_a_name=metadata.detected_team_a_name,
                team_b_name=metadata.detected_team_b_name,
            )
        except HTTPException as error:
            items.append(
                DemoUploadAnalyzeItem(
                    demo_file_path=str(metadata.demo_file_path),
                    file_name=metadata.file_name,
                    detected_team_a_name=metadata.detected_team_a_name,
                    detected_team_b_name=metadata.detected_team_b_name,
                    detected_map_number=metadata.detected_map_number,
                    detected_map_name=metadata.detected_map_name,
                    status="failed",
                    error_message=str(error.detail),
                )
            )
            continue

        items.append(
            DemoUploadAnalyzeItem(
                parse_run_id=analyzed.parse_run_id,
                demo_file_path=analyzed.demo_file_path,
                file_name=metadata.file_name,
                detected_team_a_name=metadata.detected_team_a_name,
                detected_team_b_name=metadata.detected_team_b_name,
                detected_map_number=metadata.detected_map_number,
                detected_map_name=metadata.detected_map_name,
                rounds=analyzed.rounds,
                status="analyzed",
            )
        )

    analyzed_count = sum(1 for item in items if item.status == "analyzed")
    failed_count = sum(1 for item in items if item.status == "failed")

    return DemoUploadAnalyzeResponse(
        artifact_id=saved_artifact.id,
        stored_filename=saved_artifact.stored_filename,
        artifact_type=saved_artifact.artifact_type,
        raw_file_path=str(saved_artifact.file_path),
        prepared_dir=str(prepared_artifact.prepared_dir),
        tournament_name=tournament_name,
        match_date=match_date,
        total_demo_files=len(items),
        analyzed_count=analyzed_count,
        failed_count=failed_count,
        items=items,
    )


@router.delete(
    "/dev/parse-data",
    response_model=DemoParseDataClearResponse,
)
async def clear_demo_parse_data_endpoint(
        session: AsyncSession = Depends(get_db_session),
) -> DemoParseDataClearResponse:
    await clear_demo_parse_data(session=session)

    return DemoParseDataClearResponse(
        status="cleared",
        message="demo_parse_runs and related demo_bomb_round_stats were cleared",
    )


@router.post("/upload", response_model=DemoUploadResponse)
async def upload_demo_manual(file: UploadFile = File(...)) -> DemoUploadResponse:
    try:
        saved_artifact = await save_uploaded_demo_artifact(file)
    except DemoArtifactStorageError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    return DemoUploadResponse(
        id=saved_artifact.id,
        filename=saved_artifact.original_filename,
        stored_filename=saved_artifact.stored_filename,
        file_path=str(saved_artifact.file_path),
        artifact_type=saved_artifact.artifact_type,
        status="uploaded",
    )


@router.post("/prepare", response_model=DemoArtifactPrepareResponse)
async def prepare_uploaded_demo_artifact(
        payload: DemoArtifactPrepareRequest,
) -> DemoArtifactPrepareResponse:
    try:
        prepared_artifact = prepare_demo_artifact(payload.stored_filename)
    except DemoArtifactExtractionError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    return DemoArtifactPrepareResponse(
        artifact_id=prepared_artifact.artifact_id,
        stored_filename=prepared_artifact.stored_filename,
        artifact_type=prepared_artifact.artifact_type,
        prepared_dir=str(prepared_artifact.prepared_dir),
        demo_files=[
            PreparedDemoFile(
                demo_file_path=str(metadata.demo_file_path),
                file_name=metadata.file_name,
                artifact_id=metadata.artifact_id,
                detected_team_a_name=metadata.detected_team_a_name,
                detected_team_b_name=metadata.detected_team_b_name,
                detected_map_name=metadata.detected_map_name,
                metadata_detected_from_filename=metadata.metadata_detected_from_filename,
                detected_map_number=metadata.detected_map_number,
            )
            for metadata in [
                build_prepared_demo_file_metadata(demo_file)
                for demo_file in prepared_artifact.demo_files
            ]
        ],
        status="prepared",
    )


@router.post("/analyze/prepared-path", response_model=DemoBasicStatsAnalyzeResponse)
async def analyze_prepared_demo_path_endpoint(
        payload: DemoPreparedPathAnalyzeRequest,
        session: AsyncSession = Depends(get_db_session),
) -> DemoBasicStatsAnalyzeResponse:
    metadata = build_prepared_demo_file_metadata(
        Path(payload.demo_file_path)
    )

    if not metadata.metadata_detected_from_filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Could not detect teams and map from demo file name. "
                "Expected file name format: team-a-vs-team-b-map.dem "
                "or team-a-vs-team-b-m1-map.dem"
            ),
        )

    return await _analyze_demo_file_and_save_bomb_stats(
        session=session,
        demo_file_path=payload.demo_file_path,
        artifact_id=metadata.artifact_id,
        demo_file_name=metadata.file_name,
        tournament_name=payload.tournament_name,
        match_date=payload.match_date,
        map_name=metadata.detected_map_name,
        team_a_name=metadata.detected_team_a_name,
        team_b_name=metadata.detected_team_b_name,
    )


@router.post("/analyze/basic", response_model=DemoBasicStatsAnalyzeResponse)
async def analyze_demo_basic_stats_endpoint(
        payload: DemoBasicStatsAnalyzeRequest,
        session: AsyncSession = Depends(get_db_session),
) -> DemoBasicStatsAnalyzeResponse:
    return await _analyze_demo_file_and_save_bomb_stats(
        session=session,
        demo_file_path=payload.demo_file_path,
        tournament_name=payload.tournament_name,
        match_date=payload.match_date,
        map_name=payload.map_name,
        map_number=payload.map_number,
        team_a_name=payload.team_a_name,
        team_b_name=payload.team_b_name,
    )


@router.post(
    "/import/local-path",
    response_model=DemoLocalPathImportResponse,
)
async def import_local_demo_path_endpoint(
        payload: DemoLocalPathImportRequest,
        session: AsyncSession = Depends(get_db_session),
) -> DemoLocalPathImportResponse:
    source_path = _resolve_project_local_path(payload.path)
    demo_files = _collect_demo_files_from_local_path(source_path)

    items: list[DemoLocalPathImportItem] = []

    for demo_file in demo_files:
        metadata = build_prepared_demo_file_metadata(demo_file)

        if not metadata.metadata_detected_from_filename:
            items.append(
                DemoLocalPathImportItem(
                    demo_file_path=str(demo_file),
                    file_name=demo_file.name,
                    status="failed",
                    error_message=(
                        "Could not detect metadata from filename. "
                        "Expected format: team-a-vs-team-b-m1-map.dem"
                    ),
                )
            )
            continue

        if payload.replace_existing:
            await delete_existing_demo_parse_runs(
                session=session,
                tournament_name=payload.tournament_name,
                match_date=payload.match_date,
                map_name=metadata.detected_map_name,
                map_number=metadata.detected_map_number,
                team_a_name=metadata.detected_team_a_name,
                team_b_name=metadata.detected_team_b_name,
            )

        try:
            analyzed = await _analyze_demo_file_and_save_bomb_stats(
                session=session,
                demo_file_path=str(demo_file),
                tournament_name=payload.tournament_name,
                match_date=payload.match_date,
                map_name=metadata.detected_map_name,
                map_number=metadata.detected_map_number,
                team_a_name=metadata.detected_team_a_name,
                team_b_name=metadata.detected_team_b_name,
                artifact_id=metadata.artifact_id,
                demo_file_name=metadata.file_name,
            )
        except HTTPException as error:
            items.append(
                DemoLocalPathImportItem(
                    demo_file_path=str(demo_file),
                    file_name=demo_file.name,
                    detected_team_a_name=metadata.detected_team_a_name,
                    detected_team_b_name=metadata.detected_team_b_name,
                    detected_map_number=metadata.detected_map_number,
                    detected_map_name=metadata.detected_map_name,
                    status="failed",
                    error_message=str(error.detail),
                )
            )
            continue

        items.append(
            DemoLocalPathImportItem(
                parse_run_id=analyzed.parse_run_id,
                demo_file_path=analyzed.demo_file_path,
                file_name=metadata.file_name,
                detected_team_a_name=metadata.detected_team_a_name,
                detected_team_b_name=metadata.detected_team_b_name,
                detected_map_number=metadata.detected_map_number,
                detected_map_name=metadata.detected_map_name,
                rounds=analyzed.rounds,
                status="analyzed",
            )
        )

    analyzed_count = sum(1 for item in items if item.status == "analyzed")
    failed_count = sum(1 for item in items if item.status == "failed")

    return DemoLocalPathImportResponse(
        source_path=str(source_path),
        tournament_name=payload.tournament_name,
        match_date=payload.match_date,
        total_demo_files=len(items),
        analyzed_count=analyzed_count,
        failed_count=failed_count,
        items=items,
    )