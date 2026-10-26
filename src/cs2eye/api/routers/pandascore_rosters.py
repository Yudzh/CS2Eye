from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.db.session import get_db_session
from cs2eye.integrations.pandascore.client import PandaScoreError
from cs2eye.models.team import Team
from cs2eye.models.match import Tournament
from cs2eye.services.pandascore_roster_service import PandaScoreRosterService

router = APIRouter(tags=['PandaScore rosters'])


class RosterSelection(BaseModel):
    player_ids: list[int] = Field(min_length=5, max_length=5)


class TournamentBinding(BaseModel):
    external_id: int = Field(gt=0)


async def mutate(session, action):
    try:
        result = await action()
        await session.commit()
        return result
    except PandaScoreError as exc:
        await session.rollback()
        raise HTTPException(502, str(exc)) from exc
    except (ValueError, IntegrityError) as exc:
        await session.rollback()
        message = str(exc) if isinstance(exc, ValueError) else 'Конфликт привязки PandaScore; обновите страницу.'
        raise HTTPException(422, message) from exc


@router.get('/teams/{team_id}/pandascore/roster')
async def main_roster(team_id: int, session: AsyncSession = Depends(get_db_session)):
    team = await session.get(Team, team_id)
    if team is None:
        raise HTTPException(404, 'Команда не найдена.')
    return team.pandascore_roster_data


@router.post('/teams/{team_id}/pandascore/roster/refresh')
async def refresh_main_roster(team_id: int, session: AsyncSession = Depends(get_db_session)):
    return await mutate(session, lambda: PandaScoreRosterService(session).refresh_main(team_id))


@router.post('/teams/{team_id}/pandascore/roster/select')
async def select_main_roster(team_id: int, payload: RosterSelection, session: AsyncSession = Depends(get_db_session)):
    return await mutate(session, lambda: PandaScoreRosterService(session).apply_main(team_id, payload.player_ids))


@router.get('/tournaments/{tournament_id}/pandascore')
async def tournament_binding(tournament_id: int, session: AsyncSession = Depends(get_db_session)):
    tournament = await session.get(Tournament, tournament_id)
    if not tournament:
        raise HTTPException(404, 'Турнир не найден.')
    external_id = await PandaScoreRosterService(session).tournament_external_id(tournament)
    return {'external_id':external_id, 'event':tournament.pandascore_data}


@router.post('/tournaments/{tournament_id}/pandascore')
async def bind_tournament(tournament_id: int, payload: TournamentBinding, session: AsyncSession = Depends(get_db_session)):
    return await mutate(session, lambda: PandaScoreRosterService(session).bind_tournament(tournament_id, payload.external_id))


@router.get('/pandascore/tournaments/{external_id}')
async def preview_tournament(external_id: int, session: AsyncSession = Depends(get_db_session)):
    if external_id <= 0:
        raise HTTPException(422, 'Нужен положительный ID стадии турнира.')
    async def preview():
        row = await PandaScoreRosterService(session).fetch(lambda c: c.tournament(external_id))
        if not isinstance(row, dict) or row.get('id') != external_id:
            raise ValueError('Стадия PandaScore не найдена.')
        return {k:row.get(k) for k in ['id','name','league','serie','videogame']}
    return await mutate(session, preview)
