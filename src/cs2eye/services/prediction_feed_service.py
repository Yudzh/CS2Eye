"""One archived pick per match for the upcoming/results interface."""
from sqlalchemy import select
from cs2eye.services.prediction_result_eligibility import eligibility
from cs2eye.services.match_result_sync_service import result_metadata
from cs2eye.services.analyst_probability_service import analyst_probability_adjustment
from cs2eye.models.match import Match, Tournament
from cs2eye.models.team import Team
from cs2eye.models.prediction import MatchPrediction, PredictionHistorySnapshot


class PredictionFeedService:
    def __init__(self, session):
        self.session = session

    async def feed(self):
        teams = dict((await self.session.execute(select(Team.id, Team.name))).all())
        tournaments = dict((await self.session.execute(select(Tournament.id, Tournament.name))).all())
        picks = {}
        replays = (await self.session.scalars(select(MatchPrediction).where(
            MatchPrediction.source == 'historical_replay', MatchPrediction.mode == 'pre_veto',
            MatchPrediction.prediction_status == 'available',
        ).order_by(MatchPrediction.created_at, MatchPrediction.id))).all()
        for row in replays:
            picks[row.series_id] = (row, 'retrospective', row.team_a_probability, row.model_version, row.created_at)
        snapshots = (await self.session.scalars(select(PredictionHistorySnapshot).where(
            PredictionHistorySnapshot.source == 'pre_match',
        ))).all()
        for row in snapshots:
            picks[row.match_id] = (row, 'pre_match', row.ml_a_probability, row.ml_model_version, row.as_of)
        matches = (await self.session.scalars(select(Match).where(
            Match.team_a_id.is_not(None), Match.team_b_id.is_not(None),
            Match.status.in_(('scheduled', 'in_progress', 'completed')),
        ).order_by(Match.match_date, Match.id))).all()
        vitality_ids = {key for key, name in teams.items() if name == "Vitality"}
        items = []
        for match in matches:
            saved = picks.get(match.id)
            probability = version = source = captured_at = None
            eligible = True
            if saved:
                row, source, p, version, captured_at = saved
                if source == "pre_match":
                    eligible, _ = eligibility(row, match)
                if {row.team_a_id, row.team_b_id} != {match.team_a_id, match.team_b_id}:
                    saved = None
                elif p is not None and 0 <= float(p) <= 1:
                    probability = float(p) if row.team_a_id == match.team_a_id else 1 - float(p)
            completed = match.status == 'completed'
            if completed and probability is None:
                continue
            adjustment = None
            archived_probability = probability
            if source == 'retrospective' and probability is not None and vitality_ids.intersection({match.team_a_id, match.team_b_id}):
                probability, adjustment = await analyst_probability_adjustment(
                    self.session, match.team_a_id, match.team_b_id, probability,
                    series_id=match.id, team_ids=vitality_ids)
            winner_id = (match.team_a_id if probability > .5 else match.team_b_id if probability < .5 else None) if probability is not None else None
            items.append({
                'result_sync': result_metadata(match),
                'match_id': match.id, 'match_date': match.match_date.isoformat(),
                'starts_at': match.starts_at.isoformat() if match.starts_at else None,
                'status': match.status, 'tournament_id': match.tournament_id,
                'tournament': tournaments.get(match.tournament_id), 'format': match.format,
                'team_a': {'id': match.team_a_id, 'name': teams.get(match.team_a_id)},
                'team_b': {'id': match.team_b_id, 'name': teams.get(match.team_b_id)},
                'team_a_probability': probability,
                'predicted_winner': teams.get(winner_id),
                'probability': max(probability, 1-probability) if probability is not None else None,
                'actual_winner': teams.get(match.winner_team_id) if completed else None,
                'correct': winner_id == match.winner_team_id if eligible and completed and winner_id and match.winner_team_id else None,
                'score': {'team_a': match.team_a_maps_won, 'team_b': match.team_b_maps_won} if completed else None,
                'source': source if probability is not None else None,
                'model_version': version if probability is not None else None,
                'captured_at': captured_at.isoformat() if probability is not None and captured_at else None,
            })
            if adjustment is not None:
                archived_winner = match.team_a_id if archived_probability > .5 else match.team_b_id if archived_probability < .5 else None
                items[-1].update(
                    manual_adjustment=adjustment,
                    archived_correct=archived_winner == match.winner_team_id if completed and archived_winner and match.winner_team_id else None,
                )
        return {'items': items}
