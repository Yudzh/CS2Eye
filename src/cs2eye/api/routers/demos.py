from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status
from starlette.concurrency import run_in_threadpool

from cs2eye.api.schemas.demos import DemoListResponse, DemoUploadResponse, DemoArtifactPrepareResponse, \
    DemoArtifactPrepareRequest, DemoBasicStatsAnalyzeResponse, DemoBasicStatsAnalyzeRequest, DemoPlayerDamageStats
from cs2eye.db.session import get_db_session
from cs2eye.services.demo_artifact_extractor import prepare_demo_artifact, DemoArtifactExtractionError
from cs2eye.services.demo_artifact_storage import save_uploaded_demo_artifact, DemoArtifactStorageError
from cs2eye.services.demo_basic_stats_analyzer import analyze_demo_basic_stats, DemoBasicStatsAnalyzeError
from cs2eye.services.demo_parse_run_service import create_demo_parse_run, mark_demo_parse_run_failed, \
    mark_demo_parse_run_success_with_player_damage_stats

router = APIRouter(prefix="/demos", tags=["demos"])


@router.get("", response_model=DemoListResponse)
async def list_demos() -> DemoListResponse:
    return DemoListResponse()


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
            str(demo_file)
            for demo_file in prepared_artifact.demo_files
        ],
        status="prepared",
    )


@router.post("/analyze/basic", response_model=DemoBasicStatsAnalyzeResponse)
async def analyze_demo_basic_stats_endpoint(
        payload: DemoBasicStatsAnalyzeRequest,
        session: AsyncSession = Depends(get_db_session),
) -> DemoBasicStatsAnalyzeResponse:
    parse_run = await create_demo_parse_run(
        session=session,
        demo_file_path=payload.demo_file_path,
    )

    try:
        stats = await run_in_threadpool(
            analyze_demo_basic_stats,
            payload.demo_file_path,
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

    parse_run = await mark_demo_parse_run_success_with_player_damage_stats(
        session=session,
        parse_run=parse_run,
        demo_file_path=str(stats.demo_file_path),
        rounds_count=stats.rounds,
        players=stats.players,
    )

    return DemoBasicStatsAnalyzeResponse(
        parse_run_id=parse_run.id,
        demo_file_path=str(stats.demo_file_path),
        rounds=stats.rounds,
        players=[
            DemoPlayerDamageStats(
                player_name=player.player_name,
                team_name=player.team_name,
                total_damage=player.total_damage,
                rounds=player.rounds,
                average_damage_per_round=player.average_damage_per_round,
            )
            for player in stats.players
        ],
        status="analyzed",
    )


