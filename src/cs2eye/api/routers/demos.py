from uuid import UUID

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status
from starlette.concurrency import run_in_threadpool

from cs2eye.api.schemas.demos import DemoListResponse, DemoUploadResponse, DemoArtifactPrepareResponse, \
    DemoArtifactPrepareRequest, DemoBasicStatsAnalyzeResponse, DemoBasicStatsAnalyzeRequest, \
    DemoBombRoundStats, DemoBombRoundStatsResponse, DemoBombAnalysisResponse, DemoBombAnalysisMeeting, PreparedDemoFile
from cs2eye.db.session import get_db_session
from cs2eye.services.demo_artifact_extractor import prepare_demo_artifact, DemoArtifactExtractionError
from cs2eye.services.demo_artifact_storage import save_uploaded_demo_artifact, DemoArtifactStorageError
from cs2eye.services.demo_basic_stats_analyzer import analyze_demo_basic_stats, DemoBasicStatsAnalyzeError
from cs2eye.services.demo_bomb_analysis_service import get_bomb_analysis
from cs2eye.services.demo_filename_metadata import build_prepared_demo_file_metadata
from cs2eye.services.demo_parse_run_service import create_demo_parse_run, mark_demo_parse_run_failed, \
    mark_demo_parse_run_success, get_demo_bomb_round_stats

router = APIRouter(prefix="/demos", tags=["demos"])


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
        map_name: str,
        team_a_name: str | None = None,
        team_b_name: str | None = None,
        session: AsyncSession = Depends(get_db_session),
) -> DemoBombAnalysisResponse:
    if (team_a_name is None) != (team_b_name is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="team_a_name and team_b_name must be provided together",
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
        matches_count=analysis.matches_count,
        average_exploded_bombs_per_map=analysis.average_exploded_bombs_per_map,
        average_defused_bombs_per_map=analysis.average_defused_bombs_per_map,
        meetings=[
            DemoBombAnalysisMeeting(
                parse_run_id=meeting.parse_run_id,
                demo_file_path=meeting.demo_file_path,
                map_name=meeting.map_name,
                team_a_name=meeting.team_a_name,
                team_b_name=meeting.team_b_name,
                rounds_count=meeting.rounds_count,
                exploded_bombs=meeting.exploded_bombs,
                defused_bombs=meeting.defused_bombs,
            )
            for meeting in analysis.meetings
        ],
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
            )
            for metadata in [
                build_prepared_demo_file_metadata(demo_file)
                for demo_file in prepared_artifact.demo_files
            ]
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
        tournament_name=payload.tournament_name,
        match_date=payload.match_date,
        map_name=payload.map_name,
        team_a_name=payload.team_a_name,
        team_b_name=payload.team_b_name,
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


