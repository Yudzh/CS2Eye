"""Official October 25 Swiss round-two pairings, applied to existing slots.

Source (times converted from CET to UTC):
https://bo3.gg/news/navi-to-face-furia-vitality-to-play-the-mongolz-in-the-second-round-of-the-pgl-masters-bucharest-2026-group-stage
"""
from datetime import UTC, date, datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from cs2eye.deployment.bucharest_2026 import NAME
from cs2eye.models.match import Match, Tournament
from cs2eye.models.team import Team

# record, slot within record, team A, team B, kickoff hour UTC
PAIRINGS = (
    ('1-0', 1, 'FUT', 'Liquid', 8),
    ('1-0', 2, 'Vitality', 'The MongolZ', 11),
    ('1-0', 3, 'BetBoom', 'Nemiga', 11),
    ('1-0', 4, 'FURIA', 'Natus Vincere', 17),
    ('0-1', 1, 'Spirit', 'TYLOO', 8),
    ('0-1', 2, 'G2', 'Aurora', 14),
    ('0-1', 3, 'MOUZ', '9z', 14),
    ('0-1', 4, 'Legacy', 'DENDELE', 17),
)


def apply(session: Session) -> int:
    if session.get_bind().dialect.name == 'postgresql':
        session.execute(text('SELECT pg_advisory_xact_lock(2026, 8050)'))
    tournaments = session.scalars(select(Tournament).where(
        Tournament.name == NAME, Tournament.year == 2026)).all()
    if len(tournaments) != 1:
        raise ValueError('Bucharest round 2 requires exactly one seeded tournament')
    tournament = tournaments[0]
    names = {name for _, _, a, b, _ in PAIRINGS for name in (a, b)}
    teams = session.scalars(select(Team).where(Team.name.in_(names))).all()
    by_name = {team.name: team.id for team in teams}
    if len(teams) != len(names) or set(by_name) != names:
        raise ValueError('Bucharest round 2 requires all 16 uniquely named teams')
    rows = session.scalars(select(Match).where(
        Match.tournament_id == tournament.id, Match.round_number == 2,
        Match.stage == 'swiss')).all()
    by_label = {row.round_label: row for row in rows}
    expected = {f'Swiss round 2 · {record} · {slot}' for record, slot, *_ in PAIRINGS}
    if len(rows) != 8 or set(by_label) != expected:
        raise ValueError('Bucharest round 2 requires exactly eight original Swiss slots')

    # Validate the entire update before mutating any slot. Never repurpose a match
    # with different participants: demos, outcomes and forecasts reference its ID.
    changes = []
    for record, slot, a, b, hour in PAIRINGS:
        row = by_label[f'Swiss round 2 · {record} · {slot}']
        pair = (by_name[a], by_name[b])
        current = (row.team_a_id, row.team_b_id)
        if current not in ((None, None), pair):
            raise ValueError(f'Bucharest round 2 participant conflict in match {row.id}')
        if current == (None, None) and (
            row.status != 'scheduled' or row.winner_team_id is not None
            or row.team_a_maps_won or row.team_b_maps_won
        ):
            raise ValueError(f'Bucharest round 2 slot {row.id} already has recorded play')
        kickoff = datetime(2026, 10, 25, hour, tzinfo=UTC)
        # SQLite returns naive UTC datetimes; production PostgreSQL preserves TZ.
        existing = row.starts_at
        if existing is not None and existing.tzinfo is None:
            existing = existing.replace(tzinfo=UTC)
        if existing is not None and existing != kickoff:
            raise ValueError(f'Bucharest round 2 kickoff conflict in match {row.id}')
        if row.match_date != date(2026, 10, 25):
            raise ValueError(f'Bucharest round 2 date conflict in match {row.id}')
        changes.append((row, pair, kickoff))
    for row, pair, kickoff in changes:
        row.team_a_id, row.team_b_id = pair
        row.starts_at = kickoff
    session.flush()
    return tournament.id
