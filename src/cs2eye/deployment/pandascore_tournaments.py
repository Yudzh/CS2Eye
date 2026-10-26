"""Transactional PandaScore event import, shared by releases and the admin API."""
from datetime import UTC, datetime
import re

from sqlalchemy import select
from cs2eye.models.match import Match, Tournament, TournamentTeam
from cs2eye.models.team import Team
from cs2eye.services.match_result_sync_service import MatchResultSyncService, normalized, valid_score


def stamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')) if value else None


def event_name(series):
    full = series.get('full_name') or f"{series['name']} {series['year']}"
    league = series['league']['name']
    return full if normalized(full).startswith(normalized(league)) else f'{league} {full}'


def team_key(value):
    key = normalized(value)
    return {'teamfalcons':'falcons', 'teamliquid':'liquid', 'teamspirit':'spirit',
            'teamvitality':'vitality', 'auroragaming':'aurora'}.get(key, key)


def apply(session, bundle):
    """No commits or network here: rollback the entire import on conflicts."""
    series, stages = bundle['series'], bundle['stages']
    sid = series['id']
    if not stages or not any(s['matches'] for s in stages):
        raise ValueError('PandaScore ещё не опубликовал матчи этого события.')
    name = event_name(series)
    tournaments = session.scalars(select(Tournament).with_for_update()).all()
    candidates = [t for t in tournaments if (t.pandascore_data or {}).get('serie_id') == sid or
                  (t.year == series['year'] and normalized(t.name) == normalized(name))]
    if len(candidates) > 1:
        raise ValueError('Несколько локальных турниров соответствуют событию PandaScore.')
    tournament = candidates[0] if candidates else Tournament(name=name, year=series['year'])
    session.add(tournament)
    tournament.pandascore_data = {**(tournament.pandascore_data or {}), 'serie_id': sid,
        'stage_ids': [s['id'] for s in stages], 'source': 'pandascore', 'synced_at': datetime.now(UTC).isoformat()}
    dates = [stamp(v).date() for s in stages for v in [s.get('begin_at'), s.get('end_at')] if v]
    dates += [stamp(v).date() for v in [series.get('begin_at'), series.get('end_at')] if v]
    if dates:
        tournament.start_date, tournament.end_date = min(dates), max(dates)
    tournament.environment = 'lan' if all(s.get('type') == 'offline' for s in stages) else 'unknown'
    tournament.tier = (stages[0].get('tier') or 'unknown').upper()
    tournament.structure_type = 'groups_playoff' if len(stages) > 1 else 'unknown'
    session.flush()
    teams = list(session.scalars(select(Team).with_for_update()).all())
    existing = list(session.scalars(select(Match).where(Match.tournament_id == tournament.id).with_for_update()).all())
    participants = set(session.scalars(select(TournamentTeam.team_id).where(TournamentTeam.tournament_id == tournament.id)).all())
    team_map, imported = {}, {}
    warnings = []
    for stage in stages:
        for row in stage['matches']:
            for opponent in row.get('opponents', []):
                p = opponent['opponent']
                if p['id'] in team_map:
                    continue
                found = [t for t in teams if t.pandascore_id == p['id']]
                if not found:
                    keys = {team_key(p.get(k)) for k in ['name', 'acronym', 'slug']} - {''}
                    found = [t for t in teams if team_key(t.name) in keys or team_key(t.bo3_slug) in keys]
                if len(found) > 1 or (found and found[0].pandascore_id not in (None, p['id'])):
                    raise ValueError(f"Неоднозначная команда {p['name']}; сначала свяжите её с PandaScore.")
                team = found[0] if found else Team(name=p['name'], is_analytics_active=False)
                session.add(team)
                if not found:
                    teams.append(team)
                team.pandascore_id, team.pandascore_slug = p['id'], p.get('slug')
                team.pandascore_data = p
                team.pandascore_synced_at = datetime.now(UTC)
                if not team.logo_url and (p.get('image_url') or '').startswith('https://'):
                    team.logo_url = p['image_url']
                session.flush()
                team_map[p['id']] = team.id
                if team.id not in participants:
                    session.add(TournamentTeam(tournament_id=tournament.id, team_id=team.id))
                    participants.add(team.id)
        for row in stage['matches']:
            when = stamp(row.get('scheduled_at') or row.get('begin_at') or stage.get('begin_at'))
            if when is None:
                raise ValueError(f"У матча PandaScore #{row['id']} не указана дата.")
            pair = [team_map[o['opponent']['id']] for o in row.get('opponents', [])]
            if len(pair) not in (0, 2) or len(set(pair)) != len(pair):
                raise ValueError('PandaScore вернул неполных участников матча.')
            match = session.scalar(select(Match).where(Match.result_external_id == row['id']))
            if match and match.tournament_id != tournament.id:
                raise ValueError('Матч PandaScore уже принадлежит другому турниру.')
            if match is None and pair:
                matches = [m for m in existing if {m.team_a_id, m.team_b_id} == set(pair) and m.match_date == when.date() and m.result_external_id in (None, row['id'])]
                if len(matches) > 1:
                    raise ValueError('Несколько локальных матчей соответствуют матчу PandaScore.')
                match = matches[0] if matches else None
            if row.get('status') not in {'not_started','running','finished'}:
                raise ValueError('Отменённый или неизвестный статус PandaScore требует ручной проверки.')
            fresh = match is None
            if fresh:
                match = Match(tournament_id=tournament.id, match_date=when.date(), status='scheduled',
                              team_a_id=pair[0] if pair else None, team_b_id=pair[1] if pair else None)
                session.add(match)
            if pair and {match.team_a_id, match.team_b_id} != set(pair):
                if match.team_a_id or match.team_b_id:
                    raise ValueError('Участники сохранённого матча отличаются от PandaScore.')
                match.team_a_id, match.team_b_id = pair
            match.result_external_id = row['id']
            link = {str(local): external for external, local in team_map.items() if local in pair}
            match.result_link = {**(match.result_link or {}), **link}
            MatchResultSyncService(session).remember_provider_match(match, {
                **row, 'league':series['league'], 'serie':series,
                'tournament':{'id':stage['id'], 'name':stage['name']}})
            match.result_checked_at = datetime.now(UTC)
            if match.status != 'completed':
                match.starts_at, match.match_date = when, when.date()
                match.format = {1:'bo1', 3:'bo3', 5:'bo5'}.get(row.get('number_of_games'), 'unknown')
            label = row.get('name', '')
            playoff = 'playoff' in stage['name'].lower()
            if fresh:
                match.round_label = label.split(':')[0][:160]
                match.group_name = stage['name'] if not playoff else None
                match.is_playoff = playoff
                match.stage = next((v for k,v in [('quarterfinal','quarterfinal'),('semifinal','semifinal'),('grand final','final')] if k in label.lower()), 'group' if not playoff else 'unknown')
                match.bracket_section = 'lower' if 'lower' in label.lower() else 'upper' if 'upper' in label.lower() else 'main' if playoff else 'group'
                digits = re.findall(r'\d+', label.split(':')[0])
                match.bracket_position = int(digits[-1]) if digits else 1
                round_match = re.search(r'round\s+(\d+)', label, re.I)
                match.round_number = int(round_match[1]) if round_match else {'quarterfinal':1,'semifinal':2,'final':3}.get(match.stage, 1)
                match.environment = tournament.environment
                match.resolution_status = 'resolved'
            if row.get('status') == 'finished' and pair:
                scores = {s['team_id']:s['score'] for s in row.get('results', [])}
                inverse = {local:ext for ext,local in team_map.items()}
                a, b = scores.get(inverse[match.team_a_id]), scores.get(inverse[match.team_b_id])
                winner = team_map.get(row.get('winner_id'))
                if row.get('forfeit') or row.get('draw'):
                    raise ValueError('Технический результат требует ручной проверки.')
                valid_score(match, a, b, winner)
                if match.status == 'completed' or match.result_manual:
                    if (match.team_a_maps_won, match.team_b_maps_won, match.winner_team_id) != (a,b,winner):
                        raise ValueError('PandaScore противоречит сохранённому результату.')
                else:
                    match.team_a_maps_won, match.team_b_maps_won, match.winner_team_id = a,b,winner
                    match.status, match.result_source = 'completed', 'pandascore'
                    match.result_received_at = datetime.now(UTC)
                match.result_check_status = 'confirmed'
            elif row.get('status') == 'running' and match.status != 'completed':
                match.status = 'in_progress'
            session.flush()
            imported[row['id']] = match
        if not stage.get('has_bracket') or not any(m.get('previous_matches') for m in stage['brackets']):
            warnings.append(f"{stage['name']}: PandaScore пока не передал связи сетки; импортированы опубликованные матчи.")
    previous_by_id = {row['id']:row.get('previous_matches', []) for stage in stages for row in stage['brackets']}
    depths = {}
    def depth(external_id, visiting):
        if external_id in depths:
            return depths[external_id]
        if external_id in visiting:
            raise ValueError('PandaScore передал циклическую сетку.')
        target = imported.get(external_id)
        parents = [p['match_id'] for p in previous_by_id.get(external_id, [])
                   if p['match_id'] in imported and target is not None
                   and imported[p['match_id']].bracket_section == target.bracket_section]
        value = 1 + max((depth(p, visiting | {external_id}) for p in parents), default=0)
        depths[external_id] = value
        return value
    for external_id, match in imported.items():
        if previous_by_id.get(external_id):
            match.round_number = depth(external_id, set())
    for stage in stages:
        for row in stage['brackets']:
            for index, previous in enumerate(row.get('previous_matches', [])):
                source, target = imported.get(previous['match_id']), imported.get(row['id'])
                if source is None or target is None or index > 1 or previous['type'] not in ('winner','loser'):
                    raise ValueError('Неполные или некорректные связи сетки PandaScore.')
                prefix = 'loser_next_match' if previous['type'] == 'loser' else 'next_match'
                prior = getattr(source, prefix + '_id')
                if prior not in (None, target.id):
                    raise ValueError('Связь PandaScore противоречит сохранённой сетке.')
                team_id = source.winner_team_id
                if previous['type'] == 'loser' and source.winner_team_id:
                    team_id = next(iter({source.team_a_id, source.team_b_id} - {None, source.winner_team_id}), None)
                slot = 'team_a' if index == 0 else 'team_b'
                if team_id in (target.team_a_id, target.team_b_id) and team_id is not None:
                    slot = 'team_a' if target.team_a_id == team_id else 'team_b'
                if team_id is not None:
                    current = getattr(target, slot + '_id')
                    if current not in (None, team_id):
                        raise ValueError('Участник следующего раунда противоречит результату PandaScore.')
                    setattr(target, slot + '_id', team_id)
                setattr(source, prefix + '_id', target.id)
                setattr(source, prefix + '_slot', slot)
    session.flush()
    return {'id':tournament.id, 'name':tournament.name, 'teams':len(participants), 'matches':len(imported), 'warnings':warnings}
