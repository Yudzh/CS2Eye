"""Restore match 378's actual pre-match forecast from immutable LLM context 78."""
import asyncio
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from sqlalchemy import select, text
from cs2eye.db.session import AsyncSessionLocal, dispose_engine
from cs2eye.models.match import Match
from cs2eye.models.prediction import PredictionHistorySnapshot, MatchPrediction, WinProbabilityModelArtifact

def dec(value):
    return Decimal(str(value))

def winner(a, b, team_a, team_b):
    return team_a if a > b else team_b if b > a else None

async def main():
    async with AsyncSessionLocal() as session:
        evidence = (await session.execute(text('SELECT id,match_id,created_at,context_snapshot FROM match_llm_analysis_runs WHERE id=78'))).mappings().one()
        context = evidence['context_snapshot']
        match = await session.get(Match, 378)
        assert evidence['match_id'] == match.id and evidence['created_at'] < match.starts_at
        a, b = context['teams']['team_a'], context['teams']['team_b']
        assert (a['id'], b['id']) == (match.team_a_id, match.team_b_id)
        prediction = context['prediction']
        assert prediction['status'] == 'available' and prediction['model_version'] == 'v12'
        assert context['analysis_mode'] == 'pre_match' and context['veto']['basis'] == 'calculated_veto'
        snapshot = await session.scalar(select(PredictionHistorySnapshot).where(PredictionHistorySnapshot.match_id == 378).with_for_update())
        assert snapshot is not None
        if snapshot.source == 'pre_match':
            assert (snapshot.matchup_factors or {}).get('recovery', {}).get('source_id') == 78
            print('Original context 78 already restored; unchanged')
            await dispose_engine()
            return
        assert snapshot.source == 'retrospective'
        Path('storage/backups/thunderpick_378_before_original_restore.json').write_text(json.dumps(
            {col.name: getattr(snapshot, col.name) for col in snapshot.__table__.columns}, default=str, ensure_ascii=False, indent=2))
        snapshot.source = 'pre_match'
        generated_at = datetime.fromisoformat(context['generated_at'].replace('Z', '+00:00'))
        assert generated_at < match.starts_at
        snapshot.as_of = datetime.fromisoformat(context['as_of'].replace('Z', '+00:00'))
        snapshot.team_strength_model_version = None
        snapshot.team_strength_a = dec(a['team_strength']['score'])
        snapshot.team_strength_b = dec(b['team_strength']['score'])
        snapshot.team_strength_winner_id = winner(snapshot.team_strength_a, snapshot.team_strength_b, a['id'], b['id'])
        # The context preserves scores but omits the original Matchup advantage selection.
        snapshot.matchup_a = dec(context['matchup']['team_a_score'])
        snapshot.matchup_b = dec(context['matchup']['team_b_score'])
        snapshot.matchup_winner_id = None
        snapshot.matchup_model_version = context['matchup']['model_version']
        snapshot.ml_a_probability = dec(prediction['team_a_probability'])
        snapshot.ml_b_probability = dec(prediction['team_b_probability'])
        snapshot.ml_model_version = prediction['model_version']
        model = await session.scalar(select(WinProbabilityModelArtifact).where(WinProbabilityModelArtifact.model_version == 'v12'))
        snapshot.ml_feature_schema_version = model.feature_schema_version
        snapshot.ml_winner_id = winner(snapshot.ml_a_probability, snapshot.ml_b_probability, a['id'], b['id'])
        snapshot.actual_winner_id = match.winner_team_id
        snapshot.matchup_factors = {'factors': {}, 'recovery': {
            'original_values_recovered': True, 'source_table': 'match_llm_analysis_runs', 'source_id': 78,
            'source_created_at': evidence['created_at'].isoformat(),
            'source_generated_at': context['generated_at'],
            'limitations': 'Original factor contributions and Matchup winner selection were not preserved in context.'}}
        # Remove only the replay made by this recovery, now superseded by original evidence.
        replay = await session.scalar(select(MatchPrediction).where(MatchPrediction.series_id == 378,
            MatchPrediction.model_version == 'v12', MatchPrediction.source == 'historical_replay'))
        if replay is not None:
            assert replay.feature_snapshot.get('original_values_recovered') is False
            await session.delete(replay)
        await session.commit()
        print('Restored original Legacy vs PARIVISION:', snapshot.ml_a_probability, snapshot.ml_b_probability)
    await dispose_engine()

if __name__ == '__main__':
    asyncio.run(main())
