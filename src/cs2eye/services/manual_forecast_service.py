"""Generate an original or clearly labelled historical forecast on request."""
from sqlalchemy import select

from cs2eye.models.match import Match
from cs2eye.models.prediction import PredictionHistorySnapshot
from cs2eye.services.historical_forecast_recovery import recover_historical_forecast
from cs2eye.services.prediction_history_service import PredictionHistoryService


async def generate_manual_forecast(session, match_id):
    match = await session.scalar(select(Match).where(Match.id == match_id).with_for_update())
    if match is None:
        raise LookupError("Матч не найден.")
    if match.team_a_id is None or match.team_b_id is None:
        raise ValueError("Сначала нужно определить обе команды матча.")
    original = await session.scalar(select(PredictionHistorySnapshot).where(
        PredictionHistorySnapshot.match_id == match_id,
        PredictionHistorySnapshot.source == "pre_match"))
    if original is not None:
        if {original.team_a_id, original.team_b_id} != {match.team_a_id, match.team_b_id}:
            raise ValueError("Команды изменились: сохранённый прогноз относится к другой паре.")
        return
    try:
        PredictionHistoryService.ensure_before_start(match)
        before_start = match.status != "completed" and match.winner_team_id is None
    except ValueError:
        before_start = False
    if before_start:
        await PredictionHistoryService(session).capture(match_id)
    else:
        row = await recover_historical_forecast(session, match_id, manual=True)
        if row is None:
            raise ValueError("Не хватает истории или модели, обученной до даты матча, "
                             "для ретроспективного расчёта. Нужны данные более ранних игр.")
