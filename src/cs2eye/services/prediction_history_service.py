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
from cs2eye.services.matchup_service import MatchupService
from cs2eye.services.analytics_as_of_service import AnalyticsAsOfService
from cs2eye.services.team_comparison_service import TeamComparisonService
from cs2eye.services.win_probability_service import predict_win_probability


def _winner(a: float | None, b: float | None, team_a_id: int, team_b_id: int) -> int | None:
    if a is None or b is None or a == b:
        return None
    return team_a_id if a > b else team_b_id


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
        ml_a = ml.get("team_a", {}).get("probability") if ml.get("prediction_status") == "available" else None
        ml_b = ml.get("team_b", {}).get("probability") if ml.get("prediction_status") == "available" else None
        snapshot = PredictionHistorySnapshot(
            match_id=match.id, tournament_id=match.tournament_id, as_of=captured_at,
            source="retrospective" if retrospective else "live",
            team_a_id=match.team_a_id, team_b_id=match.team_b_id,
            team_strength_a=Decimal(str(strength_a)), team_strength_b=Decimal(str(strength_b)),
            team_strength_winner_id=_winner(strength_a, strength_b, match.team_a_id, match.team_b_id),
            matchup_a=Decimal(str(matchup_a)), matchup_b=Decimal(str(matchup_b)),
            matchup_winner_id=_winner(matchup_a, matchup_b, match.team_a_id, match.team_b_id),
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
        rows = list((await self.session.execute(query)).all())
        items = []
        for snapshot, match in rows:
            if match.winner_team_id is not None and snapshot.actual_winner_id != match.winner_team_id:
                snapshot.actual_winner_id = match.winner_team_id
            item = await self._item(snapshot, match)
            if consensus_3_3 and item["consensus"]["votes"] != 3:
                continue
            if conflict_only and item["conflict"]["type"] in {"none", "incomplete"}:
                continue
            if strong_conflicts and not item["conflict"]["strong"]:
                continue
            items.append(item)
        return {"items": items, "statistics": self._statistics(items),
                "tournaments": await self._tournaments()}

    async def _item(self, row: PredictionHistorySnapshot, match: Match) -> dict:
        teams = {team.id: team.name for team in (await self.session.scalars(
            select(Team).where(Team.id.in_((row.team_a_id, row.team_b_id)))
        )).all()}
        tournament = await self.session.get(Tournament, row.tournament_id) if row.tournament_id else None
        predictions = [row.team_strength_winner_id, row.matchup_winner_id, row.ml_winner_id]
        votes = {team_id: predictions.count(team_id) for team_id in set(predictions) if team_id is not None}
        consensus_winner = max(votes, key=votes.get) if len(predictions) == 3 and all(predictions) else None
        consensus_votes = votes.get(consensus_winner, 0) if consensus_winner else 0
        def prediction(winner_id, a, b, *, probability=False):
            return {"team_a_value": None if a is None else float(a), "team_b_value": None if b is None else float(b),
                    "predicted_winner_id": winner_id, "predicted_winner": teams.get(winner_id),
                    "correct": None if row.actual_winner_id is None or winner_id is None else winner_id == row.actual_winner_id,
                    "probability": probability}
        conflict = self._conflict(row, predictions)
        return {
            "id": row.id, "match_id": row.match_id, "tournament_id": row.tournament_id,
            "tournament": tournament.name if tournament else None, "match_date": match.match_date.isoformat(),
            "as_of": row.as_of.isoformat(), "created_at": row.created_at.isoformat(), "source": row.source,
            "team_a": {"id": row.team_a_id, "name": teams.get(row.team_a_id)},
            "team_b": {"id": row.team_b_id, "name": teams.get(row.team_b_id)},
            "actual_winner_id": row.actual_winner_id, "actual_winner": teams.get(row.actual_winner_id),
            "completed": row.actual_winner_id is not None,
            "team_strength": prediction(row.team_strength_winner_id, row.team_strength_a, row.team_strength_b),
            "matchup": prediction(row.matchup_winner_id, row.matchup_a, row.matchup_b),
            "ml": prediction(row.ml_winner_id, row.ml_a_probability, row.ml_b_probability, probability=True),
            "consensus": {"winner_id": consensus_winner, "winner": teams.get(consensus_winner),
                          "votes": consensus_votes, "total": 3 if consensus_winner else 0,
                          "correct": None if row.actual_winner_id is None or consensus_winner is None else consensus_winner == row.actual_winner_id},
            "conflict": {**conflict,
                         "majority_winner": teams.get(conflict["majority_winner_id"]),
                         "dissent_winner": teams.get(conflict["dissent_winner_id"])},
        }

    @staticmethod
    def _conflict(row: PredictionHistorySnapshot, predictions: list[int | None]) -> dict:
        base = {"type": "none", "strength": None, "strong": False,
                "majority_winner_id": None, "dissent_winner_id": None,
                "dissenting_prediction": None}
        if any(value is None for value in predictions):
            return {**base, "type": "incomplete"}
        margins = [abs(float(row.team_strength_a) - float(row.team_strength_b)),
                   abs(float(row.matchup_a) - float(row.matchup_b)),
                   abs(float(row.ml_a_probability) - float(row.ml_b_probability)) * 100]
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
    def _statistics(items: list[dict]) -> dict:
        def metric(key: str) -> dict:
            eligible = [item[key] for item in items if item["completed"] and item[key]["predicted_winner_id"] is not None]
            correct = sum(value["correct"] is True for value in eligible)
            return {"correct": correct, "total": len(eligible), "accuracy": None if not eligible else correct / len(eligible)}
        consensus = [item["consensus"] for item in items if item["completed"] and item["consensus"]["votes"] == 3]
        correct = sum(value["correct"] is True for value in consensus)
        conflict_statistics = {}
        for conflict_type in ("ts_matchup_vs_ml", "ts_ml_vs_matchup", "matchup_ml_vs_ts"):
            eligible = [item for item in items if item["completed"] and item["conflict"]["type"] == conflict_type]
            majority_correct = sum(item["conflict"]["majority_winner_id"] == item["actual_winner_id"] for item in eligible)
            dissent_correct = sum(item["conflict"]["dissent_winner_id"] == item["actual_winner_id"] for item in eligible)
            total = len(eligible)
            conflict_statistics[conflict_type] = {
                "total": total, "majority_correct": majority_correct, "dissent_correct": dissent_correct,
                "majority_accuracy": None if not total else majority_correct / total,
                "dissent_accuracy": None if not total else dissent_correct / total,
            }
        return {"team_strength": metric("team_strength"), "matchup": metric("matchup"), "ml": metric("ml"),
                "consensus_3_3": {"correct": correct, "total": len(consensus),
                                  "accuracy": None if not consensus else correct / len(consensus)},
                "conflicts": conflict_statistics,
                "strong_conflict_threshold": settings.prediction_history_strong_conflict_threshold}

    async def _tournaments(self) -> list[dict]:
        rows = (await self.session.execute(select(Tournament.id, Tournament.name).join(
            PredictionHistorySnapshot, PredictionHistorySnapshot.tournament_id == Tournament.id,
        ).distinct().order_by(Tournament.name))).all()
        return [{"id": item.id, "name": item.name} for item in rows]
