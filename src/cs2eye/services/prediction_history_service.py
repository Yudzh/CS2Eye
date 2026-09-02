from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.match import Match, Tournament
from cs2eye.models.prediction import PredictionHistorySnapshot
from cs2eye.models.team import Team
from cs2eye.core.config import settings
from cs2eye.analytics.scoring import SCORING_MODEL_VERSION
from cs2eye.services.matchup_service import MatchupService
from cs2eye.services.analytics_as_of_service import AnalyticsAsOfService
from cs2eye.services.team_comparison_service import TeamComparisonService
from cs2eye.services.win_probability_service import predict_win_probability
from cs2eye.services.prediction_history_evaluation_service import (
    COMPARISON_TYPES, PredictionHistoryEvaluationService,
)
from cs2eye.services.prediction_history_error_analysis_service import PredictionHistoryErrorAnalysisService


def _winner(a: float | None, b: float | None, team_a_id: int, team_b_id: int) -> int | None:
    if a is None or b is None or a == b:
        return None
    return team_a_id if a > b else team_b_id


def _matchup_factor_snapshot(matchup: dict) -> dict:
    """Copy only stable, formula-relevant values from the Matchup result."""
    reliability = float(matchup.get("reliability") or 0)
    factors = {}
    for factor in matchup.get("factors", []):
        score = factor.get("score")
        impact = float(factor.get("impact") or 0)
        factors[factor["key"]] = {
            "label": factor.get("label") or factor["key"],
            "team_a_score": None if score is None else float(score),
            "team_b_score": None if score is None else 100 - float(score),
            "weight": float(factor.get("weight") or 0),
            "effective_weight": float(factor.get("effective_weight") or 0),
            "reliability": factor.get("confidence"),
            "sample": factor.get("sample"),
            "available": bool(factor.get("available", score is not None)),
            "raw_contribution": impact,
            "contribution": round(impact * reliability, 4),
        }
    return {"matchup_reliability": reliability, "factors": factors}


class PredictionHistoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def capture(self, match_id: int, *, as_of: datetime | None = None, retrospective: bool = False) -> PredictionHistorySnapshot:
        existing = await self.session.scalar(select(PredictionHistorySnapshot).where(
            PredictionHistorySnapshot.match_id == match_id,
        ))
        if existing is not None:
            return existing
        match = await self.session.get(Match, match_id)
        if match is None:
            raise LookupError("Матч не найден.")
        if match.team_a_id is None or match.team_b_id is None:
            raise ValueError("У матча ещё не определены обе команды.")
        if (match.status == "completed" or match.winner_team_id is not None) and not retrospective:
            raise ValueError("Нельзя создавать предматчевый snapshot после завершения матча.")
        captured_at = as_of or (datetime.combine(match.match_date, datetime.min.time(), UTC) if retrospective else datetime.now(UTC))
        if retrospective:
            matchup = await AnalyticsAsOfService(self.session).calculate(
                match.team_a_id, match.team_b_id, match.match_date,
                match.format, "pre_veto", match.id,
            )
            if matchup.get("prediction_status") == "unavailable" or matchup.get("team_strength") is None:
                raise ValueError("Недостаточно исторических данных до даты матча.")
            strength_a = float(matchup["team_strength"]["team_a_score"])
            strength_b = float(matchup["team_strength"]["team_b_score"])
            ml = None
        else:
            comparison = await TeamComparisonService(self.session, now=captured_at).compare(
                match.team_a_id, match.team_b_id,
            )
            matchup = await MatchupService(self.session).calculate(
                match.team_a_id, match.team_b_id, match.format, "pre_veto",
                captured_at.date(), match.id,
            )
            strength_a = float(comparison.team_a.strength.team_strength_score)
            strength_b = float(comparison.team_b.strength.team_strength_score)
            ml = await predict_win_probability(
                self.session, a=match.team_a_id, b=match.team_b_id,
                format=match.format, mode="pre_veto", as_of=captured_at.date(), series_id=match.id,
            )
        matchup_a = float(matchup["team_a"]["score"])
        matchup_b = float(matchup["team_b"]["score"])
        ml_a = ml.get("team_a", {}).get("probability") if ml and ml.get("prediction_status") == "available" else None
        ml_b = ml.get("team_b", {}).get("probability") if ml and ml.get("prediction_status") == "available" else None
        snapshot = PredictionHistorySnapshot(
            match_id=match.id, tournament_id=match.tournament_id, as_of=captured_at,
            source="retrospective" if retrospective else "pre_match",
            team_strength_model_version=SCORING_MODEL_VERSION,
            matchup_model_version=matchup.get("model_version"),
            ml_model_version=ml.get("model_version") if ml else None,
            ml_feature_schema_version=ml.get("feature_schema_version") if ml else None,
            team_a_id=match.team_a_id, team_b_id=match.team_b_id,
            team_strength_a=Decimal(str(strength_a)), team_strength_b=Decimal(str(strength_b)),
            team_strength_winner_id=_winner(strength_a, strength_b, match.team_a_id, match.team_b_id),
            matchup_a=Decimal(str(matchup_a)), matchup_b=Decimal(str(matchup_b)),
            matchup_winner_id=matchup.get("advantage", {}).get("team_id"),
            matchup_factors=_matchup_factor_snapshot(matchup),
            ml_a_probability=None if ml_a is None else Decimal(str(ml_a)),
            ml_b_probability=None if ml_b is None else Decimal(str(ml_b)),
            ml_winner_id=_winner(ml_a, ml_b, match.team_a_id, match.team_b_id),
        )
        # Capture can be triggered twice by concurrent UI requests. The unique
        # match_id constraint is the final arbiter; isolate a losing INSERT in
        # a savepoint so the outer request transaction remains usable.
        try:
            async with self.session.begin_nested():
                self.session.add(snapshot)
                await self.session.flush([snapshot])
            return snapshot
        except IntegrityError:
            existing = await self.session.scalar(select(PredictionHistorySnapshot).where(
                PredictionHistorySnapshot.match_id == match_id,
            ))
            if existing is not None:
                return existing
            raise

    async def capture_tournament(self, tournament_id: int) -> dict:
        if await self.session.get(Tournament, tournament_id) is None:
            raise LookupError("Турнир не найден.")
        match_ids = list((await self.session.scalars(select(Match.id).where(
            Match.tournament_id == tournament_id,
            Match.status == "scheduled",
            Match.team_a_id.is_not(None), Match.team_b_id.is_not(None),
        ).order_by(Match.match_date, Match.id))).all())
        existing = set((await self.session.scalars(select(PredictionHistorySnapshot.match_id).where(
            PredictionHistorySnapshot.match_id.in_(match_ids),
        ))).all()) if match_ids else set()
        created = []
        errors = []
        for match_id in match_ids:
            if match_id in existing:
                continue
            try:
                await self.capture(match_id)
                created.append(match_id)
            except (LookupError, ValueError) as error:
                errors.append({"match_id": match_id, "message": str(error)})
        return {"tournament_id": tournament_id, "eligible": len(match_ids),
                "created": len(created), "existing": len(existing),
                "created_match_ids": created, "errors": errors}

    async def history(
        self, *, tournament_id: int | None = None, match_date: date | None = None,
        status: str | None = None, consensus_3_3: bool = False,
        conflict_only: bool = False, strong_conflicts: bool = False,
        source: str | None = None, ml_model_version: str | None = None,
        team_strength_model_version: str | None = None, matchup_model_version: str | None = None,
        comparison_type: str | None = None, matchup_error_driver: str | None = None,
        error_result: str | None = None, ml_confidence_error: int | None = None,
    ) -> dict:
        query = select(PredictionHistorySnapshot, Match).join(
            Match, Match.id == PredictionHistorySnapshot.match_id,
        ).order_by(Match.match_date.desc(), PredictionHistorySnapshot.created_at.desc())
        if tournament_id is not None:
            query = query.where(PredictionHistorySnapshot.tournament_id == tournament_id)
        if match_date is not None:
            query = query.where(Match.match_date == match_date)
        if status == "completed":
            query = query.where(Match.status == "completed", Match.winner_team_id.is_not(None))
        elif status == "future":
            query = query.where(Match.status != "completed")
        elif status is not None:
            raise ValueError("status must be completed or future")
        if source not in {None, "pre_match", "retrospective"}:
            raise ValueError("source must be pre_match or retrospective")
        if comparison_type is not None and comparison_type not in COMPARISON_TYPES:
            raise ValueError("invalid comparison_type")
        if error_result not in {None, "any", "matchup", "team_strength", "ml"}:
            raise ValueError("invalid error_result")
        if ml_confidence_error not in {None, 60, 70, 80}:
            raise ValueError("ml_confidence_error must be 60, 70 or 80")
        if ml_model_version is not None:
            query = query.where(PredictionHistorySnapshot.ml_model_version.is_(None) if ml_model_version == "unknown" else PredictionHistorySnapshot.ml_model_version == ml_model_version)
        if team_strength_model_version is not None:
            query = query.where(PredictionHistorySnapshot.team_strength_model_version.is_(None) if team_strength_model_version == "unknown" else PredictionHistorySnapshot.team_strength_model_version == team_strength_model_version)
        if matchup_model_version is not None:
            query = query.where(PredictionHistorySnapshot.matchup_model_version.is_(None) if matchup_model_version == "unknown" else PredictionHistorySnapshot.matchup_model_version == matchup_model_version)
        rows = list((await self.session.execute(query)).all())
        all_items = []
        for snapshot, match in rows:
            if match.winner_team_id is not None and snapshot.actual_winner_id != match.winner_team_id:
                snapshot.actual_winner_id = match.winner_team_id
            item = await self._item(snapshot, match)
            all_items.append(item)
        statistics_items = []
        for item in all_items:
            if consensus_3_3 and item["consensus"]["votes"] != 3:
                continue
            if conflict_only and item["conflict"]["type"] in {"none", "incomplete"}:
                continue
            if strong_conflicts and not item["conflict"]["strong"]:
                continue
            if comparison_type is not None and item["comparison"]["type"] != comparison_type:
                continue
            analysis = item["error_analysis"]
            if error_result is not None and not (item["source"] == "pre_match" and item["completed"]):
                continue
            if error_result == "any" and not any(analysis[key]["is_correct"] is False for key in ("team_strength", "matchup", "ml")):
                continue
            if error_result in {"team_strength", "matchup", "ml"} and analysis[error_result]["is_correct"] is not False:
                continue
            matchup_analysis = analysis["matchup"]
            top_driver = matchup_analysis["error_drivers"][0]["factor"] if matchup_analysis["error_drivers"] else None
            if matchup_error_driver is not None and not (
                item["source"] == "pre_match" and item["completed"] and
                matchup_analysis["is_correct"] is False and top_driver == matchup_error_driver
            ):
                continue
            if ml_confidence_error is not None and not (
                analysis["ml"]["is_correct"] is False and analysis["ml"]["probability"] is not None
                and analysis["ml"]["probability"] >= ml_confidence_error / 100
            ):
                continue
            statistics_items.append(item)
        items = [item for item in statistics_items if source is None or item["source"] == source]
        statistics = PredictionHistoryEvaluationService().evaluate(statistics_items, count_items=all_items)
        statistics.update(PredictionHistoryErrorAnalysisService().aggregate(statistics_items))
        statistics["strong_conflict_threshold"] = settings.prediction_history_strong_conflict_threshold
        return {"items": items, "statistics": statistics,
                "tournaments": await self._tournaments(), "model_versions": self._model_versions(all_items)}

    async def _item(self, row: PredictionHistorySnapshot, match: Match) -> dict:
        teams = {team.id: team.name for team in (await self.session.scalars(
            select(Team).where(Team.id.in_((row.team_a_id, row.team_b_id)))
        )).all()}
        tournament = await self.session.get(Tournament, row.tournament_id) if row.tournament_id else None
        retrospective = row.source == "retrospective"
        effective_ml_winner = None if retrospective else row.ml_winner_id
        effective_ml_a = None if retrospective else row.ml_a_probability
        effective_ml_b = None if retrospective else row.ml_b_probability
        predictions = [row.team_strength_winner_id, row.matchup_winner_id, effective_ml_winner]
        votes = {team_id: predictions.count(team_id) for team_id in set(predictions) if team_id is not None}
        consensus_winner = max(votes, key=votes.get) if len(predictions) == 3 and all(predictions) else None
        consensus_votes = votes.get(consensus_winner, 0) if consensus_winner else 0
        def prediction(winner_id, a, b, *, probability=False, evaluation_status=None):
            return {"team_a_value": None if a is None else float(a), "team_b_value": None if b is None else float(b),
                    "predicted_winner_id": winner_id, "predicted_winner": teams.get(winner_id),
                    "correct": None if row.actual_winner_id is None or winner_id is None else winner_id == row.actual_winner_id,
                    "probability": probability,
                    "evaluation_status": evaluation_status or ("available" if winner_id is not None else "unavailable")}
        conflict = self._conflict_values(row, predictions, effective_ml_a, effective_ml_b)
        comparison = PredictionHistoryEvaluationService.comparison(predictions)
        item = {
            "id": row.id, "match_id": row.match_id, "tournament_id": row.tournament_id,
            "tournament": tournament.name if tournament else None, "match_date": match.match_date.isoformat(),
            "as_of": row.as_of.isoformat(), "created_at": row.created_at.isoformat(), "source": row.source,
            "evaluation": {"eligible": not retrospective, "reason": "retrospective" if retrospective else None},
            "versions": {"team_strength": row.team_strength_model_version,
                         "matchup": row.matchup_model_version, "ml": row.ml_model_version,
                         "ml_feature_schema": row.ml_feature_schema_version},
            "team_a": {"id": row.team_a_id, "name": teams.get(row.team_a_id)},
            "team_b": {"id": row.team_b_id, "name": teams.get(row.team_b_id)},
            "actual_winner_id": row.actual_winner_id, "actual_winner": teams.get(row.actual_winner_id),
            "completed": match.status == "completed" and row.actual_winner_id is not None,
            "team_strength": prediction(row.team_strength_winner_id, row.team_strength_a, row.team_strength_b),
            "matchup": prediction(row.matchup_winner_id, row.matchup_a, row.matchup_b),
            "ml": prediction(effective_ml_winner, effective_ml_a, effective_ml_b, probability=True,
                             evaluation_status="not_evaluable_retrospective" if retrospective else None),
            "consensus": {"winner_id": consensus_winner, "winner": teams.get(consensus_winner),
                          "votes": consensus_votes, "total": 3 if consensus_winner else 0,
                          "correct": None if row.actual_winner_id is None or consensus_winner is None else consensus_winner == row.actual_winner_id},
            "comparison": comparison,
            "conflict": {**conflict,
                         "majority_winner": teams.get(conflict["majority_winner_id"]),
                         "dissent_winner": teams.get(conflict["dissent_winner_id"])},
        }
        item["error_analysis"] = PredictionHistoryErrorAnalysisService.analyze_item(item, row.matchup_factors)
        return item

    @staticmethod
    def _conflict_values(row: PredictionHistorySnapshot, predictions: list[int | None],
                         ml_a: Decimal | None, ml_b: Decimal | None) -> dict:
        base = {"type": "none", "strength": None, "strong": False,
                "majority_winner_id": None, "dissent_winner_id": None,
                "dissenting_prediction": None}
        if any(value is None for value in predictions):
            return {**base, "type": "incomplete"}
        margins = [abs(float(row.team_strength_a) - float(row.team_strength_b)),
                   abs(float(row.matchup_a) - float(row.matchup_b)),
                   abs(float(ml_a) - float(ml_b)) * 100]
        strength = sum(margins) / len(margins)
        distinct = set(predictions)
        if len(distinct) == 1:
            return {**base, "strength": strength}
        if len(distinct) == 3:
            return {**base, "type": "all_three_different", "strength": strength,
                    "strong": strength >= settings.prediction_history_strong_conflict_threshold}
        ts, matchup, ml = predictions
        if ts == matchup:
            conflict_type, majority, dissent, layer = "ts_matchup_vs_ml", ts, ml, "ml"
        elif ts == ml:
            conflict_type, majority, dissent, layer = "ts_ml_vs_matchup", ts, matchup, "matchup"
        else:
            conflict_type, majority, dissent, layer = "matchup_ml_vs_ts", matchup, ts, "team_strength"
        return {**base, "type": conflict_type, "strength": strength,
                "strong": strength >= settings.prediction_history_strong_conflict_threshold,
                "majority_winner_id": majority, "dissent_winner_id": dissent,
                "dissenting_prediction": layer}

    @staticmethod
    def _model_versions(items: list[dict]) -> dict:
        return {key: sorted({item["versions"][key] or "unknown" for item in items})
                for key in ("team_strength", "matchup", "ml")}

    async def _tournaments(self) -> list[dict]:
        rows = (await self.session.execute(select(Tournament.id, Tournament.name).join(
            PredictionHistorySnapshot, PredictionHistorySnapshot.tournament_id == Tournament.id,
        ).distinct().order_by(Tournament.name))).all()
        return [{"id": item.id, "name": item.name} for item in rows]
