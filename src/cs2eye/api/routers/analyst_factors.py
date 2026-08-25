from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from cs2eye.api.schemas.analyst_factors import AnalystFactorCreate, AnalystFactorResponse, AnalystFactorUpdate, AnalystPerson
from cs2eye.db.session import get_db_session
from cs2eye.models.team import AnalystFactor, Player, Team, TeamParticipantMembership
from cs2eye.services.analyst_context_service import AnalystContextService, factor_status
from cs2eye.services.demo_map_result_service import STANDARD_MAPS

router = APIRouter(prefix="/analyst-factors", tags=["analyst-factors"])


async def load_factor(session: AsyncSession, factor_id: int) -> AnalystFactor:
    factor = (await session.scalars(select(AnalystFactor).options(
        selectinload(AnalystFactor.players), selectinload(AnalystFactor.coach),
    ).where(AnalystFactor.id == factor_id))).unique().one_or_none()
    if factor is None: raise HTTPException(404, "Аналитический фактор не найден.")
    return factor


async def response(session: AsyncSession, factor: AnalystFactor, as_of: datetime | None = None) -> AnalystFactorResponse:
    team = await session.get(Team, factor.team_id)
    return AnalystFactorResponse(id=factor.id, team_id=factor.team_id, team_name=team.name,
        factor_type=factor.factor_type, text=factor.text, category=factor.category, map_name=factor.map_name,
        environment=factor.environment, players=[AnalystPerson(id=p.id, nickname=p.nickname) for p in factor.players],
        coach=AnalystPerson(id=factor.coach.id, nickname=factor.coach.nickname) if factor.coach else None,
        valid_from=factor.valid_from, valid_until=factor.valid_until, is_active=factor.is_active,
        status=factor_status(factor, as_of), created_at=factor.created_at, updated_at=factor.updated_at)


async def validate_people(session: AsyncSession, team_id: int, player_ids: list[int], coach_id: int | None) -> tuple[list[Player], Player | None]:
    memberships = (await session.execute(select(TeamParticipantMembership, Player).join(Player).where(
        TeamParticipantMembership.team_id == team_id,
        TeamParticipantMembership.player_id.in_(set(player_ids + ([coach_id] if coach_id else []))),
    ))).all()
    by_id = {player.id: (membership, player) for membership, player in memberships}
    if any(pid not in by_id or by_id[pid][0].participant_type != "player" for pid in player_ids):
        raise HTTPException(422, "Можно выбрать только игроков, связанных с этой командой.")
    if coach_id is not None and (coach_id not in by_id or by_id[coach_id][0].participant_type != "coach"):
        raise HTTPException(422, "Можно выбрать только тренера этой команды.")
    return [by_id[pid][1] for pid in player_ids], by_id[coach_id][1] if coach_id else None


def validate_map(map_name: str | None) -> str | None:
    normalized = map_name.lower() if map_name else None
    if normalized is not None and normalized not in STANDARD_MAPS:
        raise HTTPException(422, "Карта не входит в известный map pool.")
    return normalized


@router.post("", response_model=AnalystFactorResponse, status_code=201)
async def create_factor(payload: AnalystFactorCreate, session: AsyncSession = Depends(get_db_session)):
    if await session.get(Team, payload.team_id) is None: raise HTTPException(404, "Команда не найдена.")
    players, coach = await validate_people(session, payload.team_id, payload.player_ids, payload.coach_id)
    data = payload.model_dump(exclude={"player_ids", "coach_id", "map_name"})
    factor = AnalystFactor(**data, map_name=validate_map(payload.map_name), coach_id=coach.id if coach else None, players=players)
    session.add(factor); await session.commit()
    return await response(session, await load_factor(session, factor.id))


@router.get("", response_model=list[AnalystFactorResponse])
async def list_factors(team_id: int | None = None, player_id: int | None = None, coach_id: int | None = None,
    map_name: str | None = None, environment: str | None = None, factor_type: str | None = None,
    category: str | None = None, is_active: bool | None = None, as_of: datetime | None = None,
    session: AsyncSession = Depends(get_db_session)):
    factors = await AnalystContextService(session).list(team_id=team_id, player_id=player_id, coach_id=coach_id,
        map_name=map_name, environment=environment, factor_type=factor_type, category=category, is_active=is_active,
        as_of=as_of, active_at=as_of is not None)
    return [await response(session, item, as_of) for item in factors]


@router.get("/{factor_id}", response_model=AnalystFactorResponse)
async def get_factor(factor_id: int, session: AsyncSession = Depends(get_db_session)):
    return await response(session, await load_factor(session, factor_id))


@router.patch("/{factor_id}", response_model=AnalystFactorResponse)
async def update_factor(factor_id: int, payload: AnalystFactorUpdate, session: AsyncSession = Depends(get_db_session)):
    factor = await load_factor(session, factor_id); fields = payload.model_fields_set
    player_ids = payload.player_ids if "player_ids" in fields else [p.id for p in factor.players]
    coach_id = payload.coach_id if "coach_id" in fields else factor.coach_id
    players, _ = await validate_people(session, factor.team_id, player_ids or [], coach_id)
    for name in fields - {"player_ids", "coach_id", "map_name"}: setattr(factor, name, getattr(payload, name))
    if "map_name" in fields: factor.map_name = validate_map(payload.map_name)
    if "coach_id" in fields: factor.coach_id = coach_id
    if "player_ids" in fields: factor.players = players
    if factor.valid_from and factor.valid_until and factor.valid_until <= factor.valid_from:
        raise HTTPException(422, "valid_until должен быть позже valid_from")
    await session.commit()
    return await response(session, await load_factor(session, factor.id))


@router.delete("/{factor_id}", status_code=204)
async def delete_factor(factor_id: int, session: AsyncSession = Depends(get_db_session)):
    await session.delete(await load_factor(session, factor_id)); await session.commit(); return Response(status_code=204)
