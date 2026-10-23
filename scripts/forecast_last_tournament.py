"""Reconstruct forecasts without relabeling them as saved pre-match predictions."""
import asyncio
import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from sqlalchemy import select
from cs2eye.db.session import AsyncSessionLocal
from cs2eye.models.match import Match, Tournament
from cs2eye.models.team import Team
from cs2eye.services.win_probability_service import active_model, predict_win_probability

async def main():
    async with AsyncSessionLocal() as session:
        tournament = await session.scalar(select(Tournament).order_by(Tournament.start_date.desc().nullslast(), Tournament.id.desc()).limit(1))
        matches = list((await session.scalars(select(Match).where(Match.tournament_id == tournament.id).order_by(Match.match_date, Match.id))).all())
        model = await active_model(session)
        earliest = min(match.match_date for match in matches)
        if model is None or model.trained_at.date() >= earliest:
            raise ValueError("Active model was not trained before this tournament")
        split = model.metrics.get('split', {})
        for key in ('train_dates', 'validation_dates', 'test_dates'):
            dates = split.get(key)
            if not dates or dates[-1] >= earliest.isoformat():
                raise ValueError(f"Model {key} overlap tournament or have no recorded cutoff")
        names = dict((await session.execute(select(Team.id, Team.name))).all())
        rows = []
        for match in matches:
            result = await predict_win_probability(session, match.team_a_id, match.team_b_id,
                match.format, 'pre_veto', match.match_date, match.id, tournament_id=tournament.id)
            if result['model_version'] != model.model_version:
                raise ValueError('Active model changed during calculation')
            adjustment = result.get('manual_adjustment')
            p = adjustment['base_team_a_probability'] if adjustment else result['team_a']['probability']
            pick = None if p is None or p == .5 else names[match.team_a_id if p > .5 else match.team_b_id]
            row = dict(match_id=match.id, match_date=match.match_date.isoformat(),
                team_a=names.get(match.team_a_id), team_b=names.get(match.team_b_id),
                model_version=model.model_version, team_a_probability=p,
                team_b_probability=None if p is None else 1-p, predicted_winner=pick,
                status=result['prediction_status'])
            rows.append(row)
            print(f"{len(rows)}/{len(matches)} {row['team_a']} vs {row['team_b']}: {pick} {p}", flush=True)
        output = Path('artifacts') / f'tournament_{tournament.id}_reconstructed_forecasts'
        payload = dict(tournament=tournament.name, tournament_id=tournament.id,
            source='historical_reconstruction', calculated_at=datetime.now(UTC).isoformat(),
            model_version=model.model_version, model_trained_at=model.trained_at.isoformat(),
            policy='strictly_before_match_date; pre_veto; no current manual adjustments; no archive writes', rows=rows)
        output.with_suffix('.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        with output.with_suffix('.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)
        print(f"Saved {len(rows)} reconstructed forecasts to {output}", flush=True)

if __name__ == '__main__':
    asyncio.run(main())
