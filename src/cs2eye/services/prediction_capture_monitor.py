"""Capture every known scheduled matchup; each match uses an independent transaction."""
import asyncio
import logging
from datetime import UTC, datetime
from sqlalchemy import or_, select
from cs2eye.db.session import AsyncSessionLocal
from cs2eye.models.match import Match
from cs2eye.models.prediction import PredictionHistorySnapshot
from cs2eye.services.prediction_history_service import PredictionHistoryService

logger = logging.getLogger(__name__)


def due_query(now):
    return select(Match.id).where(
        Match.status == "scheduled", Match.winner_team_id.is_(None),
        Match.team_a_id.is_not(None), Match.team_b_id.is_not(None),
        ~select(PredictionHistorySnapshot.id).where(PredictionHistorySnapshot.match_id == Match.id).exists(),
        or_(Match.starts_at > now,
            Match.starts_at.is_(None) & (Match.match_date >= now.date())),
    ).order_by(Match.id)


async def capture_due():
    async with AsyncSessionLocal() as session:
        ids = list((await session.scalars(due_query(datetime.now(UTC)))).all())
    for match_id in ids:
        try:
            async with AsyncSessionLocal() as session:
                await PredictionHistoryService(session).capture(match_id)
                await session.commit()
        except Exception:
            logger.exception("Failed to save pre-match forecast for match %s; will retry", match_id)


async def recover_missed_forecasts():
    from cs2eye.services.historical_forecast_recovery import (
        missing_historical_forecasts_query, recover_historical_forecast,
    )
    async with AsyncSessionLocal() as session:
        ids = list((await session.scalars(missing_historical_forecasts_query(datetime.now(UTC).date()))).all())
    for match_id in ids:
        try:
            async with AsyncSessionLocal() as session:
                await recover_historical_forecast(session, match_id)
                await session.commit()
        except Exception:
            logger.exception("Failed to recover historical forecast for match %s", match_id)


async def prediction_capture_loop():
    while True:
        try:
            await capture_due()
            await recover_missed_forecasts()
        except Exception:
            logger.exception("Pre-match forecast monitor failed")
        await asyncio.sleep(60)
