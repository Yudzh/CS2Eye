"""Saved ML picks graded against current match results, without recalculation."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.match import Match, Tournament
from cs2eye.models.prediction import MatchPrediction, PredictionHistorySnapshot, WinProbabilityModelArtifact
from cs2eye.models.team import Team


class PredictionResultsService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def results(self) -> dict:
        teams = dict((await self.session.execute(select(Team.id, Team.name))).all())
        tournaments = dict((await self.session.execute(select(Tournament.id, Tournament.name))).all())
        items = []

        def append(row, match, probability, version, source, captured_at):
            if probability is None or version is None:
                return
            # A bracket slot may have changed participants since capture.
            if {row.team_a_id, row.team_b_id} != {match.team_a_id, match.team_b_id}:
                return
            p = float(probability)
            if not 0 <= p <= 1:
                return
            winner = row.team_a_id if p > .5 else row.team_b_id if p < .5 else None
            score = (match.team_a_maps_won, match.team_b_maps_won)
            if row.team_a_id != match.team_a_id:
                score = score[::-1]
            items.append({
                "id": f"{source}:{row.id}", "match_id": match.id,
                "tournament_id": match.tournament_id,
                "tournament": tournaments.get(match.tournament_id),
                "match_date": match.match_date.isoformat(),
                "format": match.format, "score": {"team_a": score[0], "team_b": score[1]},
                "team_a": {"id": row.team_a_id, "name": teams.get(row.team_a_id)},
                "team_b": {"id": row.team_b_id, "name": teams.get(row.team_b_id)},
                "model_version": version, "source": source,
                "captured_at": captured_at.isoformat(), "team_a_probability": p,
                "predicted_winner": teams.get(winner),
                "probability": max(p, 1-p) if winner is not None else None,
                "actual_winner": teams.get(match.winner_team_id),
                "correct": winner == match.winner_team_id if winner is not None else None,
            })

        completed = (Match.status == "completed", Match.winner_team_id.is_not(None))
        snapshots = (await self.session.execute(select(PredictionHistorySnapshot, Match).join(
            Match, Match.id == PredictionHistorySnapshot.match_id,
        ).where(*completed, PredictionHistorySnapshot.source == "pre_match"))).all()
        for row, match in snapshots:
            append(row, match, row.ml_a_probability, row.ml_model_version, "pre_match", row.created_at)
        replays = (await self.session.execute(select(MatchPrediction, Match).join(
            Match, Match.id == MatchPrediction.series_id,
        ).where(*completed, MatchPrediction.source == "historical_replay",
                MatchPrediction.prediction_status == "available"))).all()
        for row, match in replays:
            append(row, match, row.team_a_probability, row.model_version, "retrospective", row.created_at)
        # Explicit Vitality +15pp rule applies to the displayed reconstructed pick.
        # Keep the stored model probability and its grade unchanged.
        from cs2eye.services.analyst_probability_service import analyst_probability_adjustment
        vitality_ids = {team_id for team_id, name in teams.items() if name == "Vitality"}
        for item in items:
            if item["source"] != "retrospective" or not vitality_ids.intersection({item["team_a"]["id"], item["team_b"]["id"]}):
                continue
            p, adjustment = await analyst_probability_adjustment(self.session,
                item["team_a"]["id"], item["team_b"]["id"], item["team_a_probability"],
                series_id=item["match_id"], team_ids=vitality_ids)
            if adjustment is None:
                continue
            winner_id = item["team_a"]["id"] if p > .5 else item["team_b"]["id"] if p < .5 else None
            item.update(archived_correct=item["correct"], team_a_probability=p,
                        predicted_winner=teams.get(winner_id), probability=max(p,1-p) if winner_id else None,
                        correct=teams.get(winner_id) == item["actual_winner"] if winner_id else None,
                        manual_adjustment=adjustment)
        items.sort(key=lambda item: (item["match_date"], item["match_id"], item["model_version"]), reverse=True)
        active = await self.session.scalar(select(WinProbabilityModelArtifact.model_version).where(
            WinProbabilityModelArtifact.active.is_(True)))
        return {"items": items, "active_model_version": active}
