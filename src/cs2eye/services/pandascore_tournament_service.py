"""Server-side discovery and atomic import of whole PandaScore series."""
import re
from sqlalchemy import text, select
from cs2eye.models.match import Match
from cs2eye.services.prediction_history_service import PredictionHistoryService
from cs2eye.deployment.pandascore_tournaments import apply, event_name
from cs2eye.integrations.pandascore.client import PandaScoreError
from cs2eye.services.pandascore_roster_service import PandaScoreRosterService


class PandaScoreTournamentService(PandaScoreRosterService):
    async def search(self, query):
        words = query.strip().split()
        years = [int(w) for w in words if re.fullmatch(r'20\d\d', w)]
        words = [w for w in words if not re.fullmatch(r'20\d\d', w) and w.lower() not in {'iem','pgl','masters','blast','premier','esl','starladder'}]
        term = ' '.join(words)
        if len(term) < 2:
            raise ValueError('Укажите название события, например IEM Beijing 2026.')
        params = {'search[name]':term}
        if years:
            params['filter[year]'] = years[-1]
        rows = await self.fetch(lambda c: c.list_items('/csgo/series', '-begin_at', **params))
        return [{'id':r['id'], 'name':event_name(r), 'year':r['year'], 'begin_at':r.get('begin_at'),
                 'end_at':r.get('end_at'), 'stages':[{'id':t['id'],'name':t['name']} for t in r.get('tournaments',[])]}
                for r in rows]

    async def bundle(self, external_id):
        async def collect(client):
            series = await client.get_json(f'/series/{external_id}')
            if not isinstance(series, dict) or series.get('id') != external_id or not isinstance(series.get('tournaments'), list):
                raise PandaScoreError('PandaScore: неполные сведения о событии.')
            if (series.get('videogame') or {}).get('id') != 3:
                raise ValueError('Выбранное событие не относится к Counter-Strike.')
            stages = []
            for stage in series.get('tournaments', []):
                matches = await client.list_items(f"/tournaments/{stage['id']}/matches", 'id')
                brackets = await client.list_items(f"/tournaments/{stage['id']}/brackets", 'id') if stage.get('has_bracket') else []
                stages.append({**stage, 'matches':matches, 'brackets':brackets})
            return {'series':series, 'stages':stages}
        return await self.fetch(collect)

    async def import_event(self, external_id):
        bundle = await self.bundle(external_id)
        # Fetch completes before writes. Serialize writers across API processes.
        if self.session.bind.dialect.name == 'postgresql':
            await self.session.execute(text('SELECT pg_advisory_xact_lock(643920262)'))
        result = await self.session.run_sync(lambda session: apply(session, bundle))
        from cs2eye.services.match_result_sync_service import MatchResultSyncService
        from cs2eye.services.tournament_prediction_service import invalidate_tournament_predictions
        await invalidate_tournament_predictions(self.session, result['id'])
        completed = (await self.session.scalars(select(Match).where(
            Match.tournament_id == result['id'], Match.status == 'completed'))).all()
        for match in completed:
            await MatchResultSyncService(self.session).update_history(match)
        # Save eligible forecasts on the server; never calculate them after kickoff.
        history = PredictionHistoryService(self.session)
        matches = list((await self.session.scalars(select(Match).where(
            Match.tournament_id == result['id'], Match.status == 'scheduled',
            Match.team_a_id.is_not(None), Match.team_b_id.is_not(None)))).all())
        for match in matches:
            try:
                history.ensure_before_start(match)
            except ValueError:
                continue
            try:
                async with self.session.begin_nested():
                    await history.capture(match.id)
            except (ValueError, LookupError) as error:
                result['warnings'].append(f'Матч #{match.id}: прогноз не подготовлен — {error}')
        return result
