"""Development helper; production applies this data through Alembic automatically."""
import argparse
import asyncio

from cs2eye.db.session import AsyncSessionLocal, engine
from cs2eye.deployment.bucharest_2026 import (
    NAME, OPENING, PARTICIPANTS, SWISS_RECORDS, build_matches, link_bracket, apply,
)


async def populate():
    async with AsyncSessionLocal() as session:
        tournament_id = await session.run_sync(apply)
        await session.commit()
        return tournament_id


async def main(predict=False):
    try:
        tournament_id = await populate()
        if predict:
            from cs2eye.services.prediction_history_service import PredictionHistoryService
            async with AsyncSessionLocal() as session:
                result = await PredictionHistoryService(session).capture_tournament(tournament_id)
                await session.commit()
                print(f'Forecast capture: {result}')
    finally:
        await engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--predict', action='store_true')
    asyncio.run(main(parser.parse_args().predict))
