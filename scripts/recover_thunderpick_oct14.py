"""Reconstruct missing October 14 forecasts with v12 and pre-match-date data."""
import asyncio
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from sqlalchemy import select
from cs2eye.core.config import settings
from cs2eye.db.session import AsyncSessionLocal, dispose_engine
from cs2eye.models.match import Match
from cs2eye.models.prediction import MatchPrediction, PredictionHistorySnapshot
from cs2eye.models.team import Team
from cs2eye.services.win_probability_service import active_model, predict_win_probability
from cs2eye.services.prediction_history_service import PredictionHistoryService

MATCH_IDS = (377, 378, 379)
DAY = date(2026, 10, 14)

async def main():
    report = {'source': 'historical_reconstruction', 'calculated_at': datetime.now(UTC).isoformat(),
              'policy': 'strictly_before_match_date; original pre_match snapshot preserved; not original viewed values', 'rows': []}
    async with AsyncSessionLocal() as session:
        model = await active_model(session)
        if model is None or model.model_version != 'v12' or model.trained_at.date() >= DAY:
            raise ValueError('Expected the original v12 model trained before the matches')
        for key in ('train_dates', 'validation_dates', 'test_dates'):
            dates = model.metrics.get('split', {}).get(key)
            if not dates or date.fromisoformat(dates[-1]) >= DAY:
                raise ValueError(f'Unsafe model cutoff: {key}')
        names = dict((await session.execute(select(Team.id, Team.name))).all())
        for match_id in MATCH_IDS:
            match = await session.get(Match, match_id)
            if match is None or match.match_date != DAY or match.tournament_id != 13:
                raise ValueError(f'Unexpected match: {match_id}')
            original = await session.scalar(select(PredictionHistorySnapshot).where(
                PredictionHistorySnapshot.match_id == match_id,
                PredictionHistorySnapshot.source == 'pre_match'))
            if original is not None:
                print(f'{match_id}: original pre-match snapshot exists; unchanged', flush=True)
                continue
            existing = await session.scalar(select(MatchPrediction).where(
                MatchPrediction.series_id == match_id, MatchPrediction.as_of == DAY,
                MatchPrediction.mode == 'pre_veto', MatchPrediction.model_version == 'v12'))
            if existing is not None:
                print(f'{match_id}: already archived; unchanged', flush=True)
                continue
            print(f'Reconstructing {names[match.team_a_id]} vs {names[match.team_b_id]}', flush=True)
            result = await predict_win_probability(session, match.team_a_id, match.team_b_id,
                match.format, 'pre_veto', DAY, match_id, tournament_id=match.tournament_id)
            if result.get('prediction_status') != 'available' or result.get('model_version') != 'v12':
                raise ValueError(f'Unavailable historical prediction: {match_id}: {result.get("prediction_status")}')
            adjustment = result.get('manual_adjustment')
            p = adjustment['base_team_a_probability'] if adjustment else result['team_a']['probability']
            if p is None or not 0 <= p <= 1:
                raise ValueError('Invalid probability')
            row = {'match_id': match_id, 'team_a': names[match.team_a_id], 'team_b': names[match.team_b_id],
                   'model_version': 'v12', 'team_a_probability': p, 'team_b_probability': 1-p,
                   'features': result['features'], 'basis': result['basis'],
                   'historical_policy': result['matchup'].get('historical_policy'),
                   'limitations': result.get('limitations', [])}
            report['rows'].append(row)
            probability = Decimal(str(p))
            session.add(MatchPrediction(series_id=match_id, as_of=DAY, mode='pre_veto',
                source='historical_replay', model_version='v12', feature_schema_version=model.feature_schema_version,
                team_a_id=match.team_a_id, team_b_id=match.team_b_id,
                team_a_probability=probability, team_b_probability=1-probability,
                confidence=Decimal(str(result['confidence'])), prediction_status='available',
                feature_snapshot={'features': result['features'], 'basis': result['basis'],
                                  'strictly_before_match_date': True, 'recovery': report['policy'],
                                  'original_values_recovered': False, 'recovered_at': report['calculated_at']}))
            history = await session.scalar(select(PredictionHistorySnapshot).where(PredictionHistorySnapshot.match_id == match_id))
            if history is None:
                await PredictionHistoryService(session).capture(match_id, retrospective=True)
            print(f'Prepared {match_id}: {p:.8f} / {1-p:.8f}', flush=True)
        output = Path('artifacts/thunderpick_2026_oct14_recovered_forecasts.json')
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        await session.commit()
        print(f'Committed {len(report["rows"])} reconstructed forecasts. Report: {output}', flush=True)
    await dispose_engine()

if __name__ == '__main__':
    settings.debug = False
    asyncio.run(main())
