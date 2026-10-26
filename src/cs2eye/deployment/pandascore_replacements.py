"""Compare accepted main and PandaScore event rosters; shared by migration and runtime."""
from datetime import UTC, datetime, time, timedelta
from sqlalchemy import select, update

from cs2eye.models.match import Tournament, TournamentRosterCheck, TournamentRosterOverride
from cs2eye.models.team import Team, Player, TeamRoster, TeamRosterMember, AnalystFactor
from cs2eye.models.prediction import TournamentPredictionRun, TournamentMatchPrediction

POLICY = 'pandascore_roster_comparison_v1'


def reconcile(session, tournament_id, team_id, now=None):
    now = now or datetime.now(UTC)
    today = now.date()
    tournament = session.scalar(select(Tournament).where(Tournament.id == tournament_id).with_for_update())
    capture = session.scalar(select(TournamentRosterCheck).where(
        TournamentRosterCheck.tournament_id == tournament_id, TournamentRosterCheck.team_id == team_id))
    team = session.get(Team, team_id)
    if not tournament or not capture or not team or 'api.pandascore.co/' not in capture.source:
        return {'created':0, 'closed':0, 'classification':'unavailable'}
    if tournament.end_date and today > tournament.end_date:
        return {'created':0, 'closed':0, 'classification':'expired'}
    if tournament.end_date is None:
        raise ValueError('Для автоматических временных замен нужна дата окончания турнира.')
    main = session.get(TeamRoster, team.current_roster_id) if team.current_roster_id else None
    main_ids = set(session.scalars(select(TeamRosterMember.player_id).where(
        TeamRosterMember.roster_id == main.id)).all()) if main and main.resolution_status == 'complete' else set()
    event_ids = set(capture.roster_ids or [])
    if len(main_ids) != 5 or len(event_ids) != 5 or None in main_ids:
        return {'created':0, 'closed':0, 'classification':'unavailable'}
    start = max(today, tournament.start_date or today)
    manual = session.scalar(select(TournamentRosterOverride.id).where(
        TournamentRosterOverride.tournament_id == tournament_id, TournamentRosterOverride.team_id == team_id,
        TournamentRosterOverride.is_active.is_(True), TournamentRosterOverride.status == 'MANUAL',
        (TournamentRosterOverride.valid_from.is_(None) | (TournamentRosterOverride.valid_from <= start)),
        (TournamentRosterOverride.valid_until.is_(None) | (TournamentRosterOverride.valid_until >= start))))
    # Stable pairing represents set differences; never assign a bench or coaching role.
    desired = set(zip(sorted(main_ids - event_ids), sorted(event_ids - main_ids))) if not manual else set()
    rejected = set(session.execute(select(TournamentRosterOverride.player_out_id,TournamentRosterOverride.player_in_id).where(
        TournamentRosterOverride.tournament_id == tournament_id, TournamentRosterOverride.team_id == team_id,
        TournamentRosterOverride.source_type == 'AUTO', TournamentRosterOverride.notes == POLICY,
        TournamentRosterOverride.status == 'REJECTED')).all())
    desired -= rejected
    existing = list(session.scalars(select(TournamentRosterOverride).where(
        TournamentRosterOverride.tournament_id == tournament_id, TournamentRosterOverride.team_id == team_id,
        TournamentRosterOverride.source_type == 'AUTO', TournamentRosterOverride.notes == POLICY,
        TournamentRosterOverride.is_active.is_(True),
        (TournamentRosterOverride.valid_until.is_(None) | (TournamentRosterOverride.valid_until >= start)))).all())
    report = {'created':0, 'closed':0,
              'classification':'manual' if manual else 'temporary' if desired else 'permanent'}
    kept = set()
    for row in existing:
        pair = (row.player_out_id, row.player_in_id)
        if pair in desired and pair not in kept:
            kept.add(pair)
            continue
        # Retain earlier date ranges for historical analysis; close today's obsolete observation.
        if row.valid_from and row.valid_from < today:
            row.valid_until = today - timedelta(days=1)
        else:
            row.is_active = False
        factor = session.get(AnalystFactor, row.analyst_factor_id) if row.analyst_factor_id else None
        if factor:
            factor.is_active = row.is_active
            if row.valid_until:
                factor.valid_until = datetime.combine(row.valid_until, time.max, UTC)
        report['closed'] += 1
    for outgoing, incoming in sorted(desired - kept):
        players = list(session.scalars(select(Player).where(Player.id.in_([outgoing,incoming]))).all())
        if len(players) != 2:
            raise ValueError('Автоматическая замена ссылается на отсутствующего игрока.')
        names = {p.id:p.nickname for p in players}
        factor = AnalystFactor(team_id=team_id, factor_type='negative', category='roster',
            environment=tournament.environment if tournament.environment in {'lan','online'} else 'any',
            text=f"Временная замена на {tournament.name}: {names[incoming]} играет вместо {names[outgoing]}. Турнирный состав отличается от основной пятёрки.",
            players=players, is_active=True,
            valid_from=datetime.combine(start,time.min,UTC),
            valid_until=datetime.combine(tournament.end_date,time.max,UTC))
        session.add(factor)
        session.flush()
        session.add(TournamentRosterOverride(tournament_id=tournament_id,team_id=team_id,
            player_out_id=outgoing,player_in_id=incoming,status='CONFIRMED',source_type='AUTO',
            source_reference=capture.source,notes=POLICY,is_active=True,
            valid_from=start,valid_until=tournament.end_date,detected_at=now,source_published_at=now,
            analyst_factor_id=factor.id))
        report['created'] += 1
    if report['created'] or report['closed']:
        session.execute(update(TournamentPredictionRun).where(TournamentPredictionRun.tournament_id==tournament_id,
            TournamentPredictionRun.outdated.is_(False)).values(outdated=True))
        session.execute(update(TournamentMatchPrediction).where(TournamentMatchPrediction.tournament_id==tournament_id,
            TournamentMatchPrediction.invalidated_at.is_(None)).values(invalidated_at=now))
    session.flush()
    return report


def apply(session, now=None):
    now = now or datetime.now(UTC)
    captures = list(session.execute(select(TournamentRosterCheck.tournament_id,TournamentRosterCheck.team_id)
        .join(Tournament,Tournament.id==TournamentRosterCheck.tournament_id)
        .where(TournamentRosterCheck.source.like('https://api.pandascore.co/%'),
               (Tournament.end_date.is_(None) | (Tournament.end_date>=now.date())))
        .order_by(TournamentRosterCheck.tournament_id,TournamentRosterCheck.team_id)).all())
    return [reconcile(session,tournament_id,team_id,now) for tournament_id,team_id in captures]
