"""Read the released API and verify real tournament/forecast/result visibility.

Run inside the API container after preparation and startup. Never generates a
prediction or modifies a result. Release success requires these checks to pass.
"""
import asyncio
import json

import httpx
from sqlalchemy import select

from cs2eye.db.session import AsyncSessionLocal, engine
from cs2eye.models.match import Match, ResultSyncQuota, Tournament
from cs2eye.models.prediction import PredictionHistorySnapshot


async def verify(factory=AsyncSessionLocal, base_url='http://127.0.0.1:8000', transport=None):
    async with factory() as session:
        quota = await session.get(ResultSyncQuota, 1)
        if quota is None:
            raise ValueError('Result synchronization migration has not seeded the shared quota.')
        tournament_ids = set((await session.scalars(select(Tournament.id))).all())
        snapshots = (await session.scalars(select(PredictionHistorySnapshot))).all()
        matches = (await session.scalars(select(Match).where(Match.result_source.is_not(None)))).all()
    async with httpx.AsyncClient(base_url=base_url, timeout=120, transport=transport) as client:
        async def get(path):
            response = await client.get('/api/v1' + path)
            response.raise_for_status()
            return response.json()
        teams = await get('/teams')
        if teams:
            team = await get(f"/teams/{teams[0]['id']}")
            if team['id'] != teams[0]['id']:
                raise ValueError('Released API does not expose the team detail page.')
        tournaments = await get('/tournaments')
        visible = {row['id'] for row in tournaments['items']}
        if not tournament_ids.issubset(visible):
            raise ValueError('Released API does not expose required tournaments.')
        history = await get('/prediction-history')
        seen = {row['match_id']: row for row in history['items']}
        for snapshot in snapshots:
            row = seen.get(snapshot.match_id)
            if row is None or row['versions']['ml'] != snapshot.ml_model_version:
                raise ValueError(f'Released API does not expose saved forecast for match {snapshot.match_id}.')
        for match in matches:
            row = await get(f'/matches/{match.id}')
            if (row['winner_team_id'] != match.winner_team_id or
                    row['score'] != {'team_a': match.team_a_maps_won, 'team_b': match.team_b_maps_won} or
                    row.get('result_sync', {}).get('source') != match.result_source):
                raise ValueError(f'Released API does not expose saved result for match {match.id}.')
        return {'tournaments': len(visible), 'saved_forecasts': len(snapshots), 'saved_results': len(matches)}


async def main():
    try:
        print('Released API data: ' + json.dumps(await verify()), flush=True)
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
