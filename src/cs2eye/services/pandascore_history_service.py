"""Fixtures series evidence, kept separate from demo map/roster analytics."""
from datetime import UTC, datetime, timedelta

from cs2eye.models.team import Team
from cs2eye.integrations.pandascore.client import PandaScoreError
from cs2eye.services.pandascore_roster_service import PandaScoreRosterService


def normalize_history(rows, team_id, start, end):
    matches = {}
    try:
        for row in rows:
            if row.get('status') != 'finished' or row.get('forfeit') or row.get('draw'):
                continue
            begin = datetime.fromisoformat(row['begin_at'].replace('Z', '+00:00'))
            if not start <= begin < end:
                continue
            opponents = [x['opponent'] for x in row['opponents'] if x.get('type') == 'Team']
            ids = [x['id'] for x in opponents]
            if len(ids) != 2 or len(set(ids)) != 2 or team_id not in ids:
                raise ValueError('Invalid opponents')
            scores = {x['team_id']: x['score'] for x in row['results']}
            winner = (row.get('winner') or {}).get('id')
            if winner not in ids or any(type(scores.get(i)) is not int or scores[i] < 0 for i in ids):
                raise ValueError('Invalid score')
            loser = next(i for i in ids if i != winner)
            if scores[winner] <= scores[loser]:
                raise ValueError('Inconsistent winner')
            match_id = row['id']
            if type(match_id) is not int or match_id <= 0:
                raise ValueError('Invalid match ID')
            matches[match_id] = {
                'id': match_id, 'begin_at': begin.isoformat(),
                'end_at': datetime.fromisoformat(row['end_at'].replace('Z', '+00:00')).isoformat() if row.get('end_at') else None,
                'teams': [{'id': x['id'], 'name': x['name'], 'score': scores[x['id']]} for x in opponents],
                'winner_id': winner, 'format': row.get('number_of_games'),
                'tournament': ' · '.join(str(x) for x in [(row.get('league') or {}).get('name'),
                    (row.get('serie') or {}).get('full_name') or (row.get('serie') or {}).get('name'),
                    (row.get('tournament') or {}).get('name')] if x),
            }
    except (KeyError, TypeError, ValueError, AttributeError):
        raise PandaScoreError('PandaScore: неполная или противоречивая история матчей.') from None
    return sorted(matches.values(), key=lambda x: (x['begin_at'], x['id']), reverse=True)


class PandaScoreHistoryService(PandaScoreRosterService):
    async def history(self, team_id, opponent_id=None, refresh=False, as_of=None):
        team = await self.session.get(Team, team_id)
        if team is None:
            raise LookupError('Команда не найдена.')
        if team.pandascore_id is None:
            raise ValueError('Сначала привяжите команду к PandaScore.')
        opponent = None
        if opponent_id is not None:
            if opponent_id == team_id:
                raise ValueError('Выберите две разные команды.')
            opponent = await self.session.get(Team, opponent_id)
            if opponent is None:
                raise LookupError('Соперник не найден.')
            if opponent.pandascore_id is None:
                raise ValueError('Сначала привяжите соперника к PandaScore.')
        if as_of is not None and as_of.tzinfo is None:
            raise ValueError('Укажите часовой пояс для as_of.')
        now = datetime.now(UTC)
        cache = team.pandascore_history_data
        warning = None
        stale = not cache or datetime.fromisoformat(cache['synced_at']) < now - timedelta(hours=6)
        if refresh or stale:
            start = now - timedelta(days=365)
            try:
                rows = await self.fetch(lambda c: c.list_items(f'/teams/{team.pandascore_id}/matches', '-begin_at',
                    **{'filter[status]': 'finished', 'range[begin_at]': f'{start.isoformat()},{now.isoformat()}'}))
                items = normalize_history(rows, team.pandascore_id, start, now)
                cache = {'synced_at': now.isoformat(), 'from': start.isoformat(), 'to': now.isoformat(),
                         'matches': items}
                team.pandascore_history_data = cache
                await self.session.flush()
            except PandaScoreError as error:
                if not cache or refresh:
                    raise
                warning = str(error)
        point = min(as_of, now) if as_of else now
        items = [x for x in cache['matches'] if datetime.fromisoformat(x['begin_at']) < point
                 and (as_of is None or datetime.fromisoformat(x.get('end_at') or cache['synced_at']) < point)]
        if opponent:
            items = [x for x in items if opponent.pandascore_id in [t['id'] for t in x['teams']]]
        wins = sum(x['winner_id'] == team.pandascore_id for x in items)
        return {'source': 'pandascore', 'team_id': team.id, 'provider_team_id': team.pandascore_id,
                'opponent_id': opponent_id, 'synced_at': cache['synced_at'], 'from': cache['from'],
                'to': min(datetime.fromisoformat(cache['to']), point).isoformat(), 'warning': warning,
                'series_played': len(items), 'wins': wins, 'losses': len(items) - wins, 'matches': items}
