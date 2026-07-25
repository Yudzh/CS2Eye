from fastapi import (
    APIRouter,
    HTTPException,
    status,
)
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import ProgrammingError

from cs2eye.api.schemas.teams import (
    ProbeTeamResponse,
    RankingRunResponse,
    TopTeamsProbeResponse,
)
from cs2eye.db.session import get_db_session
from cs2eye.integrations.bo3.client import (
    Bo3Client,
    Bo3RankingError,
)
from cs2eye.services.top_teams_service import (
    TopTeamsService,
    get_latest_import_run,
)


router = APIRouter(
    prefix="/admin/bo3/top-teams",
    tags=["admin", "bo3"],
)


@router.get(
    "/probe",
    response_model=TopTeamsProbeResponse,
)
async def probe_top_teams(
) -> TopTeamsProbeResponse:
    try:
        async with Bo3Client() as client:
            ranking = await client.fetch_top_teams()
    except Bo3RankingError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    return TopTeamsProbeResponse(
        ranking_date=ranking.meta.ranking_date,
        teams_received=len(ranking.data),
        teams=[
            ProbeTeamResponse(
                rank=item.rank,
                name=item.team.name,
                bo3_id=item.team.id,
                bo3_slug=item.team.slug,
                points=item.score,
                rank_change=item.rank_diff,
                region=item.region,
                roster_size=len(
                    item.roster_players
                ),
            )
            for item in sorted(
                ranking.data,
                key=lambda value: value.rank,
            )
        ],
    )


@router.post(
    "/refresh",
    response_model=RankingRunResponse,
)
async def refresh_top_teams(
    session: AsyncSession = Depends(
        get_db_session,
    ),
) -> RankingRunResponse:
    try:
        run = await TopTeamsService(
            session,
        ).refresh()
    except Bo3RankingError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ProgrammingError as exc:
        database_error = str(exc.orig).splitlines()[0]
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Ошибка запроса PostgreSQL: "
                f"{database_error}"
            ),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Обновление BO3.gg завершилось ошибкой: "
                f"{type(exc).__name__}: {exc}"
            ),
        ) from exc

    return RankingRunResponse.model_validate(run)


@router.get(
    "/runs/latest",
    response_model=RankingRunResponse,
)
async def latest_run(
    session: AsyncSession = Depends(
        get_db_session,
    ),
) -> RankingRunResponse:
    try:
        run = await get_latest_import_run(session)
    except ProgrammingError as exc:
        database_error = str(exc.orig).splitlines()[0]
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Ошибка запроса PostgreSQL: "
                f"{database_error}"
            ),
        ) from exc
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ranking import has not run yet.",
        )
    return RankingRunResponse.model_validate(run)
