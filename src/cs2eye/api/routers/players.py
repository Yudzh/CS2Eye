from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.api.schemas.players import PlayerResponse, PlayerTeamResponse
from cs2eye.db.session import get_db_session
from cs2eye.services.player_service import get_player, refresh_player


router = APIRouter(prefix="/players", tags=["players"])


def _response(result) -> PlayerResponse:
    player, statuses = result
    return PlayerResponse(
        id=player.id, bo3_id=player.bo3_id, bo3_slug=player.bo3_slug,
        nickname=player.nickname, first_name=player.first_name,
        last_name=player.last_name, image_url=player.image_url,
        country_code=player.country_code, country_name=player.country_name,
        bo3_rating=player.bo3_rating, player_strength=player.player_strength,
        strength_breakdown=player.strength_breakdown,
        stats_synced_at=player.stats_synced_at,
        source_updated_at=player.source_updated_at,
        teams=[PlayerTeamResponse(
            id=item.team.id, bo3_id=item.team.bo3_id, bo3_slug=item.team.bo3_slug,
            name=item.team.name, logo_url=item.team.logo_url,
            is_active=item.is_active, participant_type=item.participant_type,
        ) for item in statuses],
    )


@router.get("/{player_id}", response_model=PlayerResponse)
async def read_player(player_id: int, session: AsyncSession = Depends(get_db_session)):
    result = await get_player(session, player_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Игрок не найден.")
    return _response(result)


@router.post("/{player_id}/refresh", response_model=PlayerResponse)
async def update_player(player_id: int, session: AsyncSession = Depends(get_db_session)):
    result = await refresh_player(session, player_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Игрок не найден.")
    return _response(result)
