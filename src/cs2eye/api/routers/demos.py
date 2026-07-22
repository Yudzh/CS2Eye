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
    DemoLocalPathImportResponse, DemoLocalPathImportRequest, DemoLocalPathImportItem, DemoBombAnalysisMap, \
    DemoTeamMapStatsResponse, DemoTeamMapStatsItem, DemoTeamMapRecentMatch, DemoRoundStatsResponse, DemoRoundStats, \
    DemoTeamMapMatchupTeamStats, DemoTeamMapMatchupResponse, DemoTeamMapMatchupItem, DemoParseRunListResponse, \
    DemoParseRunListItem, DemoPlayerMapStat as DemoPlayerMapStatSchema, DemoPlayerMapStatsResponse
from cs2eye.db.session import get_db_session
from cs2eye.services.demo_artifact_extractor import prepare_demo_artifact, DemoArtifactExtractionError
from cs2eye.services.demo_artifact_storage import save_uploaded_demo_artifact, DemoArtifactStorageError
from cs2eye.services.demo_basic_stats_analyzer import analyze_demo_basic_stats, DemoBasicStatsAnalyzeError
from cs2eye.services.demo_bomb_analysis_service import get_bomb_analysis
from cs2eye.services.demo_filename_metadata import build_prepared_demo_file_metadata
from cs2eye.services.demo_parse_run_service import create_demo_parse_run, mark_demo_parse_run_failed, \
    mark_demo_parse_run_success, get_demo_bomb_round_stats, clear_demo_parse_data, delete_existing_demo_parse_runs, \
    get_demo_round_stats, list_demo_parse_runs, get_demo_player_map_stats
from cs2eye.services.demo_team_map_stats_service import get_team_map_stats, get_team_map_matchup

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
        player_stats=stats.players,
        round_stats=stats.round_stats,
    )

    return DemoBasicStatsAnalyzeResponse(
        parse_run_id=parse_run.id,
        demo_file_path=str(stats.demo_file_path),
        map_name=parse_run.map_name,
        map_number=parse_run.map_number,
        team_a_name=parse_run.team_a_name,
        team_b_name=parse_run.team_b_name,
        rounds=stats.rounds,
        players=[
            DemoPlayerMapStatSchema(
                player_id=None,
                player_name=player.player_name,
                team_name=player.team_name,
                rounds_count=player.rounds,
                total_damage=player.total_damage,
                average_damage_per_round=(
                    player.average_damage_per_round
                ),
            )
            for player in stats.players
        ],
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
        player_stats=stats.players,
        round_stats=stats.round_stats,
    )

    return DemoBasicStatsAnalyzeResponse(
        parse_run_id=parse_run.id,
        demo_file_path=str(stats.demo_file_path),
        map_name=parse_run.map_name,
        map_number=parse_run.map_number,
        team_a_name=parse_run.team_a_name,
        team_b_name=parse_run.team_b_name,
        rounds=stats.rounds,
        players=[
            DemoPlayerMapStatSchema(
                player_id=None,
                player_name=player.player_name,
                team_name=player.team_name,
                rounds_count=player.rounds,
                total_damage=player.total_damage,
                average_damage_per_round=(
                    player.average_damage_per_round
                ),
            )
            for player in stats.players
        ],
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
    "/parse-runs",
    response_model=DemoParseRunListResponse,
)
async def list_demo_parse_runs_endpoint(
        limit: int = 50,
        status_filter: str | None = None,
        team_name: str | None = None,
        session: AsyncSession = Depends(get_db_session),
) -> DemoParseRunListResponse:
    safe_limit = max(1, min(limit, 200))

    parse_runs = await list_demo_parse_runs(
        session=session,
        limit=safe_limit,
        status=status_filter,
        team_name=team_name,
    )

    return DemoParseRunListResponse(
        items=[
            DemoParseRunListItem(
                id=parse_run.id,
                demo_file_name=parse_run.demo_file_name,
                demo_file_path=parse_run.demo_file_path,
                tournament_name=parse_run.tournament_name,
                match_date=parse_run.match_date,
                map_name=parse_run.map_name,
                map_number=parse_run.map_number,
                team_a_name=parse_run.team_a_name,
                team_b_name=parse_run.team_b_name,
                status=parse_run.status,
                rounds_count=parse_run.rounds_count,
                error_message=parse_run.error_message,
                started_at=parse_run.started_at,
                finished_at=parse_run.finished_at,
            )
            for parse_run in parse_runs
        ],
        total=len(parse_runs),
    )



@router.get(
    "/parse-runs/{parse_run_id}/players",
    response_model=DemoPlayerMapStatsResponse,
)
async def get_demo_players(
        parse_run_id: UUID,
        session: AsyncSession = Depends(get_db_session),
) -> DemoPlayerMapStatsResponse:
    player_stats = await get_demo_player_map_stats(
        session=session,
        parse_run_id=parse_run_id,
    )

    return DemoPlayerMapStatsResponse(
        parse_run_id=parse_run_id,
        items=[
            DemoPlayerMapStatSchema(
                player_id=player_stat.player_id,
                player_name=player_stat.player_name,
                team_name=player_stat.team_name,
                rounds_count=player_stat.rounds_count,
                total_damage=player_stat.total_damage,
                average_damage_per_round=(
                    player_stat.average_damage_per_round
                ),
            )
            for player_stat in player_stats
        ],
        total=len(player_stats),
    )


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
    "/parse-runs/{parse_run_id}/rounds",
    response_model=DemoRoundStatsResponse,
)
async def get_demo_rounds(
        parse_run_id: UUID,
        session: AsyncSession = Depends(get_db_session),
) -> DemoRoundStatsResponse:
    round_stats = await get_demo_round_stats(
        session=session,
        parse_run_id=parse_run_id,
    )

    return DemoRoundStatsResponse(
        parse_run_id=parse_run_id,
        items=[
            DemoRoundStats(
                round_number=round_stat.round_number,
                winner_team_name=round_stat.winner_team_name,
                winner_side=round_stat.winner_side,
                ct_team_name=round_stat.ct_team_name,
                t_team_name=round_stat.t_team_name,
                reason=round_stat.reason,
            )
            for round_stat in round_stats
        ],
        total=len(round_stats),
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


@router.get(
    "/analysis/team-maps",
    response_model=DemoTeamMapStatsResponse,
)
async def get_demo_team_map_stats_endpoint(
        team_name: str | None = None,
        map_name: str | None = None,
        session: AsyncSession = Depends(get_db_session),
) -> DemoTeamMapStatsResponse:
    analysis = await get_team_map_stats(
        session=session,
        team_name=team_name,
        map_name=map_name,
    )

    return DemoTeamMapStatsResponse(
        team_name=analysis.team_name,
        map_name=analysis.map_name,
        items=[
            DemoTeamMapStatsItem(
                team_name=item.team_name,
                map_name=item.map_name,

                total_matches_on_map=item.total_matches_on_map,
                wins_on_map=item.wins_on_map,
                losses_on_map=item.losses_on_map,
                win_rate_on_map=item.win_rate_on_map,

                rounds_won_total=item.rounds_won_total,
                rounds_lost_total=item.rounds_lost_total,
                avg_round_diff=item.avg_round_diff,
                avg_rounds_won_per_map=item.avg_rounds_won_per_map,
                avg_rounds_lost_per_map=item.avg_rounds_lost_per_map,

                win_rate_last_5_maps=item.win_rate_last_5_maps,
                win_rate_last_10_maps=item.win_rate_last_10_maps,
                win_rate_last_20_maps=item.win_rate_last_20_maps,
                current_win_streak_on_map=item.current_win_streak_on_map,
                current_lose_streak_on_map=item.current_lose_streak_on_map,
                last_played_date_on_map=item.last_played_date_on_map,
                days_since_last_played_map=item.days_since_last_played_map,

                win_rate_30_days=item.win_rate_30_days,
                win_rate_60_days=item.win_rate_60_days,
                win_rate_90_days=item.win_rate_90_days,
                matches_30_days=item.matches_30_days,
                matches_60_days=item.matches_60_days,
                matches_90_days=item.matches_90_days,

                ct_rounds_played=item.ct_rounds_played,
                ct_rounds_won=item.ct_rounds_won,
                ct_win_rate=item.ct_win_rate,

                t_rounds_played=item.t_rounds_played,
                t_rounds_won=item.t_rounds_won,
                t_win_rate=item.t_win_rate,

                avg_bomb_plants_per_map=item.avg_bomb_plants_per_map,
                avg_bomb_explosions_per_map=item.avg_bomb_explosions_per_map,
                avg_bomb_defuses_per_map=item.avg_bomb_defuses_per_map,

                map_sample_size_score=item.map_sample_size_score,
                recent_form_score=item.recent_form_score,
                map_strength_score=item.map_strength_score,
                map_confidence_score=item.map_confidence_score,
                map_confidence_level=item.map_confidence_level,
                map_tier=item.map_tier,

                is_strong_map=item.is_strong_map,
                is_weak_map=item.is_weak_map,
                is_permaban_map=item.is_permaban_map,

                recent_matches=[
                    DemoTeamMapRecentMatch(
                        parse_run_id=recent_match.parse_run_id,
                        tournament_name=recent_match.tournament_name,
                        match_date=recent_match.match_date,
                        map_name=recent_match.map_name,
                        team_name=recent_match.team_name,
                        opponent_name=recent_match.opponent_name,
                        rounds_won=recent_match.rounds_won,
                        rounds_lost=recent_match.rounds_lost,
                        won=recent_match.won,
                    )
                    for recent_match in item.recent_matches
                ],
            )
            for item in analysis.items
        ],
        total=len(analysis.items),
    )

@router.get(
    "/analysis/matchup",
    response_model=DemoTeamMapMatchupResponse,
)
async def get_demo_team_map_matchup_endpoint(
        team_a_name: str,
        team_b_name: str,
        map_name: str | None = None,
        session: AsyncSession = Depends(get_db_session),
) -> DemoTeamMapMatchupResponse:
    if team_a_name.strip().casefold() == team_b_name.strip().casefold():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="team_a_name and team_b_name must be different",
        )

    try:
        matchup = await get_team_map_matchup(
            session=session,
            team_a_name=team_a_name,
            team_b_name=team_b_name,
            map_name=map_name,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    return DemoTeamMapMatchupResponse(
        team_a_name=matchup.team_a_name,
        team_b_name=matchup.team_b_name,
        map_name=matchup.map_name,
        items=[
            DemoTeamMapMatchupItem(
                map_name=item.map_name,
                team_a=_build_demo_team_map_matchup_team_stats(item.team_a),
                team_b=_build_demo_team_map_matchup_team_stats(item.team_b),
                advantage_team_name=item.advantage_team_name,
                advantage_score=item.advantage_score,
                matchup_confidence_level=item.matchup_confidence_level,
                recommendation=item.recommendation,
            )
            for item in matchup.items
        ],
        total=len(matchup.items),
    )

def _build_demo_team_map_matchup_team_stats(
        item,
) -> DemoTeamMapMatchupTeamStats:
    return DemoTeamMapMatchupTeamStats(
        team_name=item.team_name,
        map_name=item.map_name,

        total_matches_on_map=item.total_matches_on_map,
        win_rate_on_map=item.win_rate_on_map,

        ct_win_rate=item.ct_win_rate,
        t_win_rate=item.t_win_rate,

        avg_bomb_plants_per_map=item.avg_bomb_plants_per_map,
        avg_bomb_explosions_per_map=item.avg_bomb_explosions_per_map,
        avg_bomb_defuses_per_map=item.avg_bomb_defuses_per_map,

        map_strength_score=item.map_strength_score,
        map_confidence_score=item.map_confidence_score,
        map_confidence_level=item.map_confidence_level,
        map_tier=item.map_tier,
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