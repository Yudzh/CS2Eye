"""Conservative result ingestion. Forecast calculations never run here.

All entry points hold a shared PostgreSQL transaction advisory lock, including
manual writes. The quota is persisted in that transaction, across workers/restarts.
Requests are serial (concurrency=1), capped per run and within a rolling hour.
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, time, timedelta
import re

from sqlalchemy import or_, select, text

from cs2eye.core.config import settings
from cs2eye.integrations.pandascore.client import PandaScoreClient, PandaScoreError
from cs2eye.models.match import Match, MatchResultAudit, ResultSyncQuota, Tournament
from cs2eye.models.prediction import PredictionHistorySnapshot
from cs2eye.models.team import Team

_local_lock = asyncio.Lock()


def utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def normalized(value):
    name = re.sub(r'[^a-z0-9]', '', (value or '').lower())
    return {'navi': 'natusvincere', 'g2esports': 'g2'}.get(name, name)


def state(match):
    return {key: getattr(match, key) for key in (
        'status', 'team_a_maps_won', 'team_b_maps_won', 'winner_team_id',
        'result_source', 'result_external_id', 'result_link', 'result_manual')}


def valid_score(match, a, b, winner):
    needed = {'bo1': 1, 'bo3': 2, 'bo5': 3}.get(match.format)
    if (needed is None or type(a) is not int or type(b) is not int or
            min(a, b) < 0 or max(a, b) != needed or min(a, b) >= needed or
            winner != (match.team_a_id if a > b else match.team_b_id) or
            not match.team_a_id or not match.team_b_id or match.team_a_id == match.team_b_id):
        raise ValueError('Счёт, победитель или формат серии противоречат друг другу.')


class MatchResultSyncService:
    def __init__(self, session, client_factory=PandaScoreClient):
        self.session = session
        self.client_factory = client_factory

    @asynccontextmanager
    async def locked(self):
        async with _local_lock:
            if self.session.bind.dialect.name == 'postgresql':
                await self.session.execute(text('SELECT pg_advisory_xact_lock(643920261)'))
            try:
                yield
                await self.session.commit()
            except Exception:
                await self.session.rollback()
                raise

    async def get(self, match_id):
        match = await self.session.scalar(select(Match).where(Match.id == match_id).with_for_update().execution_options(populate_existing=True))
        if match is None:
            raise ValueError('Матч не найден.')
        return match

    def audit(self, match, before, actor, reason, after=None):
        self.session.add(MatchResultAudit(match_id=match.id, actor=actor, reason=reason,
                                          before=before, after=after or state(match)))

    async def quota(self):
        quota = await self.session.scalar(select(ResultSyncQuota).where(
            ResultSyncQuota.id == 1).with_for_update().execution_options(populate_existing=True))
        if quota is None:  # create_all test databases; production migration seeds it
            quota = ResultSyncQuota(id=1, requests=[])
            self.session.add(quota)
            await self.session.flush()
        return quota

    async def reserve(self, quota):
        now = datetime.now(UTC)
        if quota.blocked_until and utc(quota.blocked_until) > now:
            raise PandaScoreError('PandaScore: повтор отложен из-за ограничений API.')
        requests = [stamp for stamp in quota.requests if stamp > now.timestamp() - 3600]
        if len(requests) >= 950:  # leave headroom below the free 1000/hour limit
            raise PandaScoreError('PandaScore: локальный часовой бюджет исчерпан.')
        quota.requests = requests + [now.timestamp()]
        await self.session.flush()

    async def names(self, match):
        teams = (await self.session.scalars(select(Team).where(Team.id.in_([match.team_a_id, match.team_b_id])))).all()
        return {t.id: normalized(t.name) for t in teams}

    async def mapping(self, match, row):
        opponents = row.get('opponents') or []
        if len(opponents) != 2 or any(o.get('type') != 'Team' or not o.get('opponent') for o in opponents):
            return None
        teams = await self.names(match)
        mapping = {}
        for local_id in (match.team_a_id, match.team_b_id):
            candidates = [o['opponent']['id'] for o in opponents if teams.get(local_id) and teams[local_id] in {
                normalized(o['opponent'].get('name')), normalized(o['opponent'].get('acronym'))}]
            if len(candidates) != 1:
                return None
            mapping[str(local_id)] = candidates[0]
        return mapping if len(set(mapping.values())) == 2 else None

    async def candidates(self, match, rows):
        tournament = await self.session.get(Tournament, match.tournament_id) if match.tournament_id else None
        if tournament is None or match.starts_at is None:
            return []  # no safe automatic time/event match
        result = []
        for row in rows:
            try:
                begin = datetime.fromisoformat(row['begin_at'].replace('Z', '+00:00'))
                if abs((utc(begin) - utc(match.starts_at)).total_seconds()) > 6 * 3600:
                    continue
                league, serie = row.get('league') or {}, row.get('serie') or {}
                # Tournament is a stage, not the event. Compare League + Series.
                event = normalized(' '.join(str(v or '') for v in (league.get('name'), serie.get('full_name'))))
                local_event = normalized(tournament.name)
                if serie.get('year') != tournament.year:
                    continue
                if local_event not in {event, normalized(' '.join(str(v or '') for v in (league.get('name'), serie.get('name'))))}:
                    continue
                if await self.mapping(match, row):
                    result.append(row)
            except (KeyError, ValueError, TypeError, AttributeError, OverflowError):
                continue
        return result

    def review(self, match, reason, row):
        if match.result_proposal != row:
            self.audit(match, state(match), 'pandascore', reason, {'proposal': row})
        match.result_proposal = row
        match.result_check_status = 'needs_review'
        match.result_error = reason

    def remember_provider_match(self, match, row):
        # Compact server-fetched evidence, separate from the local/external team mapping.
        # No arbitrary provider URLs or credentials are sent to the browser.
        def reference(value):
            value = value if isinstance(value, dict) else {}
            return {key: value.get(key) for key in ('id', 'name', 'full_name', 'year')}
        opponents = row.get('opponents') or []
        evidence = {
            'id': row.get('id'), 'name': row.get('name'), 'status': row.get('status'),
            'begin_at': row.get('begin_at'), 'scheduled_at': row.get('scheduled_at'),
            'league': reference(row.get('league')), 'serie': reference(row.get('serie')),
            'tournament': reference(row.get('tournament')),
            'opponents': [reference(o.get('opponent')) for o in opponents if isinstance(o, dict)],
            'results': row.get('results'), 'winner_id': row.get('winner_id'),
            'forfeit': row.get('forfeit'),
        }
        match.result_link = {**(match.result_link or {}), '_pandascore': evidence}

    async def apply(self, match, row):
        """Validate participant IDs on every receipt, including confirmed links."""
        link = match.result_link or {}
        try:
            participants = [o['opponent']['id'] for o in row['opponents'] if o['type'] == 'Team']
            expected = [link[str(match.team_a_id)], link[str(match.team_b_id)]]
            if len(participants) != 2 or set(participants) != set(expected) or len(set(expected)) != 2:
                raise ValueError('Участники изменились; требуется ручная проверка.')
            if row.get('forfeit') or row.get('draw') or row.get('status') == 'canceled' or row.get('winner_type', 'Team') != 'Team':
                raise ValueError('Отмена, ничья или технический результат; требуется ручная проверка.')
            if row.get('status') != 'finished':
                match.result_check_status = 'pending'
                return
            if row.get('number_of_games') != {'bo1': 1, 'bo3': 3, 'bo5': 5}.get(match.format):
                raise ValueError('Формат PandaScore отличается от нашего формата.')
            scores = row['results']
            if len(scores) != 2 or {s['team_id'] for s in scores} != set(expected):
                raise ValueError('Неполный или противоречивый счёт.')
            score = {s['team_id']: s['score'] for s in scores}
            a, b = score[expected[0]], score[expected[1]]
            winner_ext = row.get('winner_id')
            if (row.get('winner') or {}).get('id', winner_ext) != winner_ext or winner_ext not in expected:
                raise ValueError('Противоречивый победитель.')
            winner = match.team_a_id if winner_ext == expected[0] else match.team_b_id
            valid_score(match, a, b, winner)
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as error:
            self.review(match, str(error) if isinstance(error, ValueError) else 'Неполные данные PandaScore.', row)
            return
        before = state(match)
        same = (match.team_a_maps_won, match.team_b_maps_won, match.winner_team_id) == (a, b, winner)
        if match.result_manual:
            if not same:
                self.review(match, 'Результат отличается от ручного исправления.', row)
            else:
                match.result_check_status = 'manual'
            return
        if match.status == 'completed' or match.winner_team_id is not None:
            if not same:
                self.review(match, 'Изменение уже записанного результата; требуется подтверждение.', row)
                return
        match.status = 'completed'
        match.team_a_maps_won, match.team_b_maps_won, match.winner_team_id = a, b, winner
        match.result_source = 'pandascore'
        match.result_received_at = datetime.now(UTC)
        match.result_check_status = 'confirmed'
        match.result_proposal = None
        if state(match) != before:
            self.audit(match, before, 'pandascore', 'Подтверждён завершённый матч.')
            await self.finalize(match, before)
        await self.update_history(match)

    async def finalize(self, match, before):
        from cs2eye.services.match_service import MatchService
        from cs2eye.services.tournament_prediction_service import invalidate_tournament_predictions
        await self.session.flush()
        service = MatchService(self.session)
        await service._propagate_winner(match, before['winner_team_id'])
        await service._propagate_loser(match, before['winner_team_id'])
        await invalidate_tournament_predictions(self.session, match.tournament_id)

    async def update_history(self, match):
        snapshot = await self.session.scalar(select(PredictionHistorySnapshot).where(PredictionHistorySnapshot.match_id == match.id))
        if snapshot and {snapshot.team_a_id, snapshot.team_b_id} == {match.team_a_id, match.team_b_id}:
            snapshot.actual_winner_id = match.winner_team_id

    async def run(self, match_id=None):
        async with self.locked():
            now = datetime.now(UTC)
            if match_id is not None:
                matches = [await self.get(match_id)]
            else:
                matches = list((await self.session.scalars(select(Match).where(
                    or_(Match.starts_at <= now, (Match.starts_at.is_(None)) & (Match.match_date < now.date())),
                    Match.status != 'completed', Match.winner_team_id.is_(None),
                    or_(Match.result_checked_at.is_(None), Match.result_checked_at <= now - timedelta(seconds=settings.result_sync_interval_seconds)),
                ).order_by(Match.result_checked_at.asc().nullsfirst(), Match.match_date).limit(100).with_for_update())).all())
            quota = await self.quota()
            client = self.client_factory(quota, lambda: self.reserve(quota))
            cache = {}
            checked = 0
            linked_ids = sorted({m.result_external_id for m in matches if m.result_external_id})
            try:
                for match in matches:
                    if client.calls >= settings.result_sync_max_requests:
                        break  # leave unprocessed matches due; avoid starving old fixtures
                    checked += 1
                    match.result_checked_at = now
                    match.result_error = None
                    if not settings.pandascore_api_token.get_secret_value():
                        match.result_check_status = 'disabled'
                        match.result_error = 'На сервере не настроен PANDASCORE_API_TOKEN.'
                        continue
                    try:
                        if match.result_external_id:
                            key = ('ids', tuple(linked_ids))
                            params = {'filter[id]': ','.join(str(external_id) for external_id in linked_ids)}
                        else:
                            day = match.match_date
                            key = ('day', day)
                            begin = datetime.combine(day, time.min, UTC) - timedelta(hours=6)
                            end = begin + timedelta(hours=36)
                            params = {'range[begin_at]': f'{begin.isoformat()},{end.isoformat()}'}
                        # A manual check before kickoff can establish the link on the free upcoming list.
                        kind = 'upcoming' if match.starts_at and utc(match.starts_at) > now and match.status != 'completed' else 'past'
                        key = (kind, key)
                        if key not in cache:
                            cache[key] = await (client.upcoming(**params) if kind == 'upcoming' else client.past(**params))
                        rows = cache[key]
                        if match.result_external_id:
                            candidates = [r for r in rows if r.get('id') == match.result_external_id]
                        else:
                            candidates = await self.candidates(match, rows)
                        if len(candidates) != 1:
                            if len(candidates) > 1:
                                self.review(match, 'Неоднозначная привязка; выберите PandaScore ID вручную.',
                                            {'candidates': candidates})
                            match.result_check_status = 'needs_review' if len(candidates) > 1 else 'not_found'
                            match.result_error = ('Неоднозначная привязка; выберите PandaScore ID вручную.' if candidates else
                                                  'Матч не найден в завершённых: он ещё идёт, отсутствует в покрытии или требует ручной привязки.')
                            continue
                        row = candidates[0]
                        if not match.result_external_id:
                            duplicate = await self.session.scalar(select(Match.id).where(Match.result_external_id == row['id'], Match.id != match.id))
                            if duplicate:
                                self.review(match, 'PandaScore ID уже связан с другим матчем.', row)
                                continue
                            before = state(match)
                            match.result_external_id = row['id']
                            match.result_link = await self.mapping(match, row)
                            self.audit(match, before, 'pandascore', 'Автоматическая привязка по событию, командам и времени.')
                        self.remember_provider_match(match, row)
                        await self.apply(match, row)
                    except PandaScoreError as error:
                        match.result_check_status = 'error'
                        match.result_error = str(error)
            finally:
                await client.close()
            return {'checked': checked}

    async def bind(self, match_id, external_id, team_a_external_id, team_b_external_id, actor, reason):
        async with self.locked():
            match = await self.get(match_id)
            if team_a_external_id == team_b_external_id or not match.team_a_id or not match.team_b_id:
                raise ValueError('Укажите двух разных участников.')
            duplicate = await self.session.scalar(select(Match.id).where(Match.result_external_id == external_id, Match.id != match_id))
            if duplicate:
                raise ValueError('PandaScore ID уже связан с другим матчем.')
            before = state(match)
            match.result_external_id = external_id
            match.result_link = {str(match.team_a_id): team_a_external_id, str(match.team_b_id): team_b_external_id}
            match.result_check_status = 'linked'
            match.result_error = None
            self.audit(match, before, actor, reason)

    async def correct(self, match_id, a, b, winner, actor, reason):
        async with self.locked():
            match = await self.get(match_id)
            valid_score(match, a, b, winner)
            before = state(match)
            match.team_a_maps_won, match.team_b_maps_won, match.winner_team_id = a, b, winner
            match.status = 'completed'
            match.result_source = 'manual'
            match.result_manual = True
            match.result_received_at = datetime.now(UTC)
            match.result_check_status = 'manual'
            match.result_error = None
            match.result_proposal = None
            self.audit(match, before, actor, reason)
            await self.finalize(match, before)
            await self.update_history(match)


async def result_sync_loop():
    from cs2eye.db.session import AsyncSessionLocal
    import logging
    while True:
        if settings.pandascore_api_token.get_secret_value():
            try:
                async with AsyncSessionLocal() as session:
                    await MatchResultSyncService(session).run()
            except Exception:
                # Do not print exception/request objects; credentials must stay private.
                logging.getLogger(__name__).error('Result synchronization failed; next scheduled run will retry.')
        await asyncio.sleep(settings.result_sync_interval_seconds)


def result_metadata(match):
    return {
        'source': match.result_source, 'external_id': match.result_external_id,
        'received_at': match.result_received_at.isoformat() if match.result_received_at else None,
        'checked_at': match.result_checked_at.isoformat() if match.result_checked_at else None,
        'status': match.result_check_status, 'error': match.result_error,
        'manual': match.result_manual,
        'link': {key: value for key, value in (match.result_link or {}).items() if key != '_pandascore'} or None,
        'provider_match': (match.result_link or {}).get('_pandascore'),
        'provider_api_url': f'https://api.pandascore.co/csgo/matches/past?filter[id]={match.result_external_id}' if match.result_external_id else None,
        'check_interval_seconds': settings.result_sync_interval_seconds,
        'next_check_at': (utc(match.result_checked_at) + timedelta(seconds=settings.result_sync_interval_seconds)).isoformat()
            if match.result_checked_at and match.status != 'completed' and match.winner_team_id is None else None,
        'proposal': match.result_proposal,
    }
