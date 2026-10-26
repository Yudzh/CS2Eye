from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.core.config import settings
from cs2eye.db.session import get_db_session
from cs2eye.models.match import MatchResultAudit
from cs2eye.services.match_result_sync_service import MatchResultSyncService

router = APIRouter(prefix='/matches', tags=['match-results'])


class ResultChange(BaseModel):
    actor: str = Field(min_length=1, max_length=160)
    reason: str = Field(min_length=3, max_length=2000)


class ResultLink(ResultChange):
    external_id: int = Field(gt=0)
    team_a_external_id: int = Field(gt=0)
    team_b_external_id: int = Field(gt=0)


class ResultCorrection(ResultChange):
    team_a: int = Field(ge=0, le=3)
    team_b: int = Field(ge=0, le=3)
    winner_team_id: int = Field(gt=0)


def author(request, payload):
    # Production nginx overwrites this header using the authenticated Basic user.
    actor = request.headers.get('x-cs2eye-admin') if settings.app_env == 'production' else payload.actor
    if not actor or not actor.strip() or not payload.reason.strip():
        raise HTTPException(422, 'Требуются автор и причина изменения.')
    return actor.strip()


@router.post('/{match_id}/result/check')
async def check(match_id: int, session: AsyncSession = Depends(get_db_session)):
    try:
        return await MatchResultSyncService(session).run(match_id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.put('/{match_id}/result/link')
async def link(match_id: int, payload: ResultLink, request: Request, session: AsyncSession = Depends(get_db_session)):
    try:
        await MatchResultSyncService(session).bind(match_id, payload.external_id,
            payload.team_a_external_id, payload.team_b_external_id, author(request, payload), payload.reason.strip())
        return {'status': 'linked'}
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.put('/{match_id}/result')
async def correct(match_id: int, payload: ResultCorrection, request: Request, session: AsyncSession = Depends(get_db_session)):
    try:
        await MatchResultSyncService(session).correct(match_id, payload.team_a, payload.team_b,
            payload.winner_team_id, author(request, payload), payload.reason.strip())
        return {'status': 'manual'}
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.get('/{match_id}/result/audit')
async def audit(match_id: int, session: AsyncSession = Depends(get_db_session)):
    rows = (await session.scalars(select(MatchResultAudit).where(MatchResultAudit.match_id == match_id).order_by(MatchResultAudit.id.desc()))).all()
    return {'items': [{'id': r.id, 'at': r.created_at.isoformat(), 'actor': r.actor,
                       'reason': r.reason, 'before': r.before, 'after': r.after} for r in rows]}
