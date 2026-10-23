"""Recover missed forecasts without representing them as pre-match captures."""
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from cs2eye.models.match import Match
from cs2eye.models.prediction import MatchPrediction, PredictionHistorySnapshot
from cs2eye.services.win_probability_service import active_model, predict_win_probability


def missing_historical_forecasts_query(today):
    return select(Match.id).where(
        Match.status == "scheduled", Match.winner_team_id.is_(None),
        Match.team_a_id.is_not(None), Match.team_b_id.is_not(None),
        Match.match_date < today,
        ~select(PredictionHistorySnapshot.id).where(
            PredictionHistorySnapshot.match_id == Match.id,
            PredictionHistorySnapshot.source == "pre_match",
        ).exists(),
        ~select(MatchPrediction.id).where(
            MatchPrediction.series_id == Match.id,
            MatchPrediction.source == "historical_replay",
            MatchPrediction.mode == "pre_veto",
            MatchPrediction.prediction_status == "available",
        ).exists(),
    ).order_by(Match.id)


async def recover_historical_forecast(session, match_id):
    # Serialize the check and insert with other recovery callers.
    match = await session.scalar(select(Match).where(Match.id == match_id).with_for_update())
    if match is None or match.match_date >= datetime.now(UTC).date():
        return None
    eligible = await session.scalar(missing_historical_forecasts_query(datetime.now(UTC).date()).where(Match.id == match_id))
    if eligible is None:
        return None
    model = await active_model(session)
    if model is None or model.trained_at.date() >= match.match_date:
        return None
    for key in ("train_dates", "validation_dates", "test_dates"):
        dates = model.metrics.get("split", {}).get(key)
        if not dates or date.fromisoformat(dates[-1]) >= match.match_date:
            return None
    result = await predict_win_probability(
        session, match.team_a_id, match.team_b_id, match.format,
        "pre_veto", match.match_date, match.id, tournament_id=match.tournament_id,
    )
    if result.get("prediction_status") != "available":
        return None
    if result.get("model_version") != model.model_version:
        raise ValueError("Active model changed during historical recovery")
    adjustment = result.get("manual_adjustment")
    p = Decimal(str(adjustment["base_team_a_probability"] if adjustment else result["team_a"]["probability"]))
    if not 0 <= p <= 1:
        raise ValueError("Invalid historical probability")
    row = MatchPrediction(
        series_id=match.id, as_of=match.match_date, mode="pre_veto",
        source="historical_replay", model_version=model.model_version,
        feature_schema_version=model.feature_schema_version,
        team_a_id=match.team_a_id, team_b_id=match.team_b_id,
        team_a_probability=p, team_b_probability=1-p,
        confidence=Decimal(str(result["confidence"])), prediction_status="available",
        feature_snapshot={"features": result["features"], "basis": result["basis"],
            "strictly_before_match_date": True, "original_values_recovered": False,
            "recovered_at": datetime.now(UTC).isoformat(),
            "recovery": "missed_scheduled_forecast"},
    )
    session.add(row)
    await session.flush()
    return row
