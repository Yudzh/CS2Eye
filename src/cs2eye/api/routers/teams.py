from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.api.schemas.teams import (
    TeamListItem,
    TeamParticipantResponse,
)
from cs2eye.db.session import get_db_session
from cs2eye.services.top_teams_service import (
    list_active_teams,
    list_active_rosters,
)


router = APIRouter(
    prefix="/teams",
    tags=["teams"],
)


@router.get(
    "",
    response_model=list[TeamListItem],
)
async def get_teams(
    session: AsyncSession = Depends(
        get_db_session,
    ),
) -> list[TeamListItem]:
    teams = await list_active_teams(session)
    rosters = await list_active_rosters(session)
    return [
        TeamListItem(
            **TeamListItem.model_validate(team).model_dump(
                exclude={"roster"},
            ),
            roster=[
                TeamParticipantResponse(
                    id=player.id,
                    bo3_id=player.bo3_id,
                    bo3_slug=player.bo3_slug,
                    nickname=player.nickname,
                    image_url=player.image_url,
                    country_code=player.country_code,
                    country_name=player.country_name,
                    participant_type=participant_type,
                )
                for player, participant_type
                in rosters.get(team.id, [])
            ],
        )
        for team in teams
    ]
