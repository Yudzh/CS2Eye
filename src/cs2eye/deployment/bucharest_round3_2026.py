"""Official October 26 Swiss round-three pairings, applied to existing slots.

Source (times converted from CET to UTC):
https://www.hltv.org/news/45807/spirit-to-meet-furia-on-day-3-in-bucharest
"""
from datetime import UTC, date, datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from cs2eye.deployment.bucharest_2026 import NAME
from cs2eye.models.match import Match, Tournament
from cs2eye.models.team import Team

# record, slot within record, team A, team B, kickoff hour UTC
PAIRINGS = (
    ('2-0', 1, 'Vitality', 'FUT', 11),
    ('2-0', 2, 'BetBoom', 'Natus Vincere', 17),
    ('1-1', 1, 'Nemiga', 'Aurora', 8),
    ('1-1', 2, 'The MongolZ', 'MOUZ', 8),
    ('1-1', 3, 'Spirit', 'FURIA', 14),
    ('1-1', 4, 'Liquid', 'Legacy', 14),
    ('0-2', 1, '9z', 'TYLOO', 11),
    ('0-2', 2, 'G2', 'DENDELE', 17),
)


def apply(session: Session) -> int:
    if session.get_bind().dialect.name == 'postgresql':
        session.execute(text('SELECT pg_advisory_xact_lock(2026, 8050)'))
    tournaments = session.scalars(select(Tournament).where(
        Tournament.name == NAME, Tournament.year == 2026)).all()
    if len(tournaments) != 1:
        raise ValueError('Bucharest round 3 requires exactly one seeded tournament')
    tournament = tournaments[0]
    names = {name for _, _, a, b, _ in PAIRINGS for name in (a, b)}
    teams = session.scalars(select(Team).where(Team.name.in_(names))).all()
    by_name = {team.name: team.id for team in teams}
    if len(teams) != len(names) or set(by_name) != names:
        raise ValueError('Bucharest round 3 requires all 16 uniquely named teams')
    rows = session.scalars(select(Match).where(
        Match.tournament_id == tournament.id, Match.round_number == 3,
        Match.stage == 'swiss')).all()
    by_label = {row.round_label: row for row in rows}
    expected = {f'Swiss round 3 · {record} · {slot}' for record, slot, *_ in PAIRINGS}
    if len(rows) != 8 or set(by_label) != expected:
        raise ValueError('Bucharest round 3 requires exactly eight original Swiss slots')

    # Validate the entire update before mutating any slot. Never repurpose a match
    # with different participants: demos, outcomes and forecasts reference its ID.
    changes = []
    for record, slot, a, b, hour in PAIRINGS:
        row = by_label[f'Swiss round 3 · {record} · {slot}']
        pair = (by_name[a], by_name[b])
        current = (row.team_a_id, row.team_b_id)
        if current not in ((None, None), pair):
            raise ValueError(f'Bucharest round 3 participant conflict in match {row.id}')
        if current == (None, None) and (
            row.status != 'scheduled' or row.winner_team_id is not None
            or row.team_a_maps_won or row.team_b_maps_won
        ):
            raise ValueError(f'Bucharest round 3 slot {row.id} already has recorded play')
        kickoff = datetime(2026, 10, 26, hour, tzinfo=UTC)
        # SQLite returns naive UTC datetimes; production PostgreSQL preserves TZ.
        existing = row.starts_at
        if existing is not None and existing.tzinfo is None:
            existing = existing.replace(tzinfo=UTC)
        if existing is not None and existing != kickoff:
            raise ValueError(f'Bucharest round 3 kickoff conflict in match {row.id}')
        if row.match_date != date(2026, 10, 26):
            raise ValueError(f'Bucharest round 3 date conflict in match {row.id}')
        changes.append((row, pair, kickoff))
    for row, pair, kickoff in changes:
        row.team_a_id, row.team_b_id = pair
        row.starts_at = kickoff
    session.flush()
    return tournament.id
