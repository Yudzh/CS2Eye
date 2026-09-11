from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.api.schemas.players import PlayerResponse, PlayerTeamResponse
from cs2eye.db.session import get_db_session
from cs2eye.services.player_service import get_player, refresh_player
from cs2eye.services.leadership_service import LeadershipService
from cs2eye.services.round_swing_service import player_round_swing
from cs2eye.services.player_strength_v3_service import PlayerStrengthV3Service
from cs2eye.services.player_form_v3_service import PlayerFormV3Service
from cs2eye.services.performance_profile_service import PerformanceProfileService
from cs2eye.models.team import Player


router = APIRouter(prefix="/players", tags=["players"])


async def _response(result, session: AsyncSession) -> PlayerResponse:
    player, statuses = result
    leadership = await LeadershipService(session).player(player.id)
    igl = leadership.get("igl") if leadership else None
    return PlayerResponse(
        id=player.id, bo3_id=player.bo3_id, bo3_slug=player.bo3_slug,
        nickname=player.nickname, first_name=player.first_name,
        last_name=player.last_name, image_url=player.image_url,
        country_code=player.country_code, country_name=player.country_name,
        bo3_rating=player.bo3_rating, player_strength=player.player_strength,
        player_strength_raw_score=(player.strength_breakdown or {}).get("raw_score"),
        player_strength_reliability=(player.strength_breakdown or {}).get("reliability"),
        player_strength_model_version=(player.strength_breakdown or {}).get("model_version"),
        mechanical_strength_v3=player.mechanical_strength_v3,
        supporting_strength_v3=player.supporting_strength_v3,
        player_strength_v3=player.player_strength_v3,
        player_strength_v3_reliability=player.player_strength_v3_reliability,
        player_strength_v3_breakdown=player.player_strength_v3_breakdown,
        player_strength_v3_model_version=player.player_strength_v3_model_version,
        player_form_v3=await PlayerFormV3Service(session).calculate(player.id),
        performance_profile=await PerformanceProfileService(session).player(player.id),
        bo3_avg_rating=player.bo3_rating,
        steam_id=player.steam_id, internal_rating=player.internal_rating,
        internal_rating_maps_count=player.internal_rating_maps_count,
        internal_rating_rounds_count=player.internal_rating_rounds_count,
        internal_rating_updated_at=player.internal_rating_updated_at,
        internal_rating_version=player.internal_rating_version,
        internal_rating_top15=player.internal_rating_top15,
        internal_rating_top15_maps_count=player.internal_rating_top15_maps_count,
        internal_rating_top15_rounds_count=player.internal_rating_top15_rounds_count,
        internal_rating_top16_30=player.internal_rating_top16_30,
        internal_rating_top16_30_maps_count=player.internal_rating_top16_30_maps_count,
        internal_rating_top16_30_rounds_count=player.internal_rating_top16_30_rounds_count,
        strength_breakdown=player.strength_breakdown,
        combat=player.combat,
        utility=player.utility,
        round_swing=getattr(player, "round_swing", None) or await player_round_swing(session, player.id),
        stats_synced_at=player.stats_synced_at,
        source_updated_at=player.source_updated_at,
        teams=[PlayerTeamResponse(
            id=item.team.id, bo3_id=item.team.bo3_id, bo3_slug=item.team.bo3_slug,
            name=item.team.name, logo_url=item.team.logo_url,
            is_active=item.is_active, participant_type=item.participant_type,
        ) for item in statuses],
        igl=igl, captain_strength=igl.get("captain_strength") if igl else None,
    )


@router.get("/{player_id}", response_model=PlayerResponse)
async def read_player(player_id: int, session: AsyncSession = Depends(get_db_session)):
    result = await get_player(session, player_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Игрок не найден.")
    return await _response(result, session)


@router.get("/{player_id}/performance-profile")
async def read_performance_profile(player_id: int, as_of: date | None = None, session: AsyncSession = Depends(get_db_session)):
    if await session.get(Player, player_id) is None:
        raise HTTPException(status_code=404, detail="Игрок не найден.")
    return await PerformanceProfileService(session).player(player_id, as_of)


@router.get("/{player_id}/strength-v3")
async def read_strength_v3(player_id: int, as_of: date | None = None,
                           exclude_match_id: int | None = None,
                           session: AsyncSession = Depends(get_db_session)):
    if await session.get(Player, player_id) is None:
        raise HTTPException(status_code=404, detail="Игрок не найден.")
    return await PlayerStrengthV3Service(session).calculate(
        player_id, as_of, exclude_match_id=exclude_match_id)


@router.post("/{player_id}/refresh", response_model=PlayerResponse)
async def update_player(player_id: int, session: AsyncSession = Depends(get_db_session)):
    result = await refresh_player(session, player_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Игрок не найден.")
    return await _response(result, session)

@router.post("/{player_id}/strength-v3/recalculate", response_model=PlayerResponse)
async def recalculate_strength_v3(player_id:int,session:AsyncSession=Depends(get_db_session)):
    player=await session.get(Player,player_id)
    if player is None:raise HTTPException(404,"Игрок не найден.")
    await PlayerStrengthV3Service(session).calculate_and_store(player);await session.commit()
    result=await get_player(session,player_id)
    return await _response(result,session)


@router.get("/{player_id}/form-v3")
async def read_form_v3(player_id:int,as_of:date|None=None,session:AsyncSession=Depends(get_db_session)):
    if await session.get(Player,player_id) is None:raise HTTPException(404,"Игрок не найден.")
    return await PlayerFormV3Service(session).calculate(player_id,as_of)
