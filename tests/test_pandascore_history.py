from copy import deepcopy
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from cs2eye.integrations.pandascore.client import PandaScoreClient, PandaScoreError
from cs2eye.models.team import Team
from cs2eye.services.pandascore_history_service import PandaScoreHistoryService
from tests.test_pandascore_results import db, row


def service(session, rows, status=200):
    def respond(request):
        assert request.url.path == '/teams/3210/matches'
        assert request.url.params['filter[status]'] == 'finished'
        assert 'range[begin_at]' in request.url.params
        return httpx.Response(status, json=rows)
    return PandaScoreHistoryService(session, lambda q, r: PandaScoreClient(q, r, transport=httpx.MockTransport(respond)))


async def prepare(db, row):
    (await db.get(Team, 1)).pandascore_id = 3210
    (await db.get(Team, 2)).pandascore_id = 3216
    row['begin_at'] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    await db.commit()


async def test_saved_history_h2h_and_cache(db, row):
    await prepare(db, row)
    svc = service(db, [row, row])
    result = await svc.history(1, 2)
    assert result['series_played'] == 1
    assert result['losses'] == 1
    await db.commit()
    # A fresh persisted snapshot serves requests without a provider call.
    cached = await service(db, [], 503).history(1, 2)
    assert cached == result
    assert await db.get(Team, 1)
    assert (await svc.history(1, 2, as_of=datetime.now(UTC) - timedelta(days=2)))['series_played'] == 0


async def test_invalid_refresh_preserves_cache(db, row):
    await prepare(db, row)
    await service(db, [row]).history(1)
    await db.commit()
    previous = deepcopy((await db.get(Team, 1)).pandascore_history_data)
    row['results'][0]['score'] = 3
    with pytest.raises(PandaScoreError, match='противоречивая'):
        await service(db, [row]).history(1, refresh=True)
    assert (await db.get(Team, 1)).pandascore_history_data == previous


async def test_stale_cache_survives_provider_failure(db, row):
    await prepare(db, row)
    await service(db, [row]).history(1)
    team = await db.get(Team, 1)
    team.pandascore_history_data = {**team.pandascore_history_data,
        'synced_at': (datetime.now(UTC) - timedelta(days=1)).isoformat()}
    await db.commit()
    result = await service(db, [], 503).history(1)
    assert result['series_played'] == 1
    assert result['warning']


async def test_identity_and_forfeit_filters(db, row):
    with pytest.raises(ValueError, match='привяжите'):
        await service(db, []).history(1)
    await prepare(db, row)
    with pytest.raises(ValueError, match='разные'):
        await service(db, []).history(1, 1)
    row['forfeit'] = True
    assert (await service(db, [row]).history(1))['series_played'] == 0


async def test_api_returns_persisted_h2h_and_missing_identity(db, row):
    from fastapi import FastAPI
    from cs2eye.api.routers.teams import router
    from cs2eye.db.session import get_db_session
    app = FastAPI()
    app.include_router(router, prefix='/api/v1')
    async def override():
        yield db
    app.dependency_overrides[get_db_session] = override
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/api/v1/teams/1/pandascore/history')
        assert response.status_code == 409
        await prepare(db, row)
        await service(db, [row]).history(1)
        await db.commit()
        response = await client.get('/api/v1/teams/1/pandascore/history?opponent_id=2')
        assert response.status_code == 200
        assert response.json()['losses'] == 1
        response = await client.get('/api/v1/teams/1/pandascore/history?as_of=2026-10-01T00:00:00')
        assert response.status_code == 409


async def test_partial_pagination_never_replaces_cache(db, row, monkeypatch):
    from cs2eye.core.config import settings
    await prepare(db, row)
    await service(db, [row]).history(1)
    previous = deepcopy((await db.get(Team, 1)).pandascore_history_data)
    await db.commit()
    monkeypatch.setattr(settings, 'result_sync_max_requests', 1)
    with pytest.raises(PandaScoreError, match='страниц'):
        await service(db, [row] * 100).history(1, refresh=True)
    assert (await db.get(Team, 1)).pandascore_history_data == previous
