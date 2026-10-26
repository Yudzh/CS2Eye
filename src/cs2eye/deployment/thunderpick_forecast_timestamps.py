"""Repair kickoff metadata and the timestamp of an authentic archived forecast.

October 15 times (UTC): https://bo3.gg/tournaments/thunderpick-world-championship-2026/results
The packaged AI report is immutable evidence of the original October 14 pick.
No forecast is computed, and no probability, model version or outcome is changed.
"""
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from cs2eye.models.match import Match, Tournament
from cs2eye.models.prediction import PredictionHistorySnapshot
from cs2eye.models.team import Team

NAME = 'Thunderpick World Championship 2026'
ARTIFACT = '234573bf4b896ac6ad40cc4ee4c928bad5122ee8f6f6443ae7a1f6572c6b5d3a.json'
# BO3 IDs survive PandaScore profile renames. Values verified on production.
TEAM_BO3_IDS = {'Aurora':3598, 'Ninjas in Pyjamas':785, '9z':324, 'Falcons':2713,
                'PARIVISION':8171, 'BetBoom':7498, 'Legacy':8118, 'FURIA':648}
KICKOFFS = (
    ('Aurora', 'Ninjas in Pyjamas', '08:30'),
    ('9z', 'Falcons', '11:30'),
    ('PARIVISION', 'BetBoom', '15:10'),
    ('Legacy', 'FURIA', '18:50'),
)


def utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def apply(session):
    tournament = session.scalar(select(Tournament).where(Tournament.name == NAME, Tournament.year == 2026))
    if tournament is None:
        # The optional tournament may not be installed on a fresh database.
        return {'kickoffs': 0, 'archived_timestamp': 0}
    teams = list(session.scalars(select(Team)))
    def team_named(name):
        rows = [t for t in teams if t.bo3_id == TEAM_BO3_IDS[name]]
        if len(rows) != 1:
            raise ValueError(f'Thunderpick timestamp repair requires unique BO3 team {TEAM_BO3_IDS[name]} ({name})')
        return rows[0]
    def fixture(a, b, day):
        ids = {a.id, b.id}
        rows = list(session.scalars(select(Match).where(Match.tournament_id == tournament.id,
            Match.match_date == day, Match.team_a_id.in_(ids), Match.team_b_id.in_(ids))))
        rows = [m for m in rows if {m.team_a_id, m.team_b_id} == ids]
        if len(rows) != 1:
            raise ValueError(f'Thunderpick timestamp repair requires unique fixture {a.name} / {b.name}')
        return rows[0]
    pending = []
    for a, b, clock in KICKOFFS:
        match = fixture(team_named(a), team_named(b), date(2026, 10, 15))
        if match.starts_at is None:
            pending.append((match, datetime.fromisoformat(f'2026-10-15T{clock}:00+00:00')))
    artifact = json.loads((Path(__file__).parent / 'ai_report_artifacts' / ARTIFACT).read_text())
    # Stable BO3 identities, never the local IDs embedded in a report context.
    def artifact_team(side):
        rows = [t for t in teams if t.bo3_id == artifact[side]['bo3_id']]
        if len(rows) != 1:
            raise ValueError(f'Thunderpick archived forecast requires {side} stable identity')
        return rows[0]
    match = fixture(artifact_team('team_a'), artifact_team('team_b'), date(2026, 10, 14))
    snapshot = session.scalar(select(PredictionHistorySnapshot).where(PredictionHistorySnapshot.match_id == match.id))
    if (snapshot is None or snapshot.source != 'pre_match' or
        {snapshot.team_a_id, snapshot.team_b_id} != {match.team_a_id, match.team_b_id}):
        raise ValueError('Thunderpick archived forecast prerequisite is missing; restore original values first')
    context = artifact['run']['context_snapshot']
    prediction = context['prediction']
    original_created = datetime.fromisoformat(artifact['run']['created_at'])
    original_as_of = datetime.fromisoformat(context['as_of'].replace('Z', '+00:00'))
    evidence_a = artifact_team('team_a').id
    a = Decimal(str(prediction['team_a_probability']))
    b = Decimal(str(prediction['team_b_probability']))
    if snapshot.team_a_id != evidence_a:
        a, b = b, a
    if (snapshot.ml_model_version != prediction['model_version'] or
        snapshot.ml_a_probability is None or snapshot.ml_b_probability is None or
        abs(snapshot.ml_a_probability - a) > Decimal('0.00000001') or
        abs(snapshot.ml_b_probability - b) > Decimal('0.00000001') or
        match.starts_at is None or original_created >= utc(match.starts_at) or
        original_as_of >= utc(match.starts_at) or utc(snapshot.as_of) != original_as_of):
        raise ValueError('Thunderpick archived forecast disagrees with original AI report')
    recovered = utc(snapshot.created_at) != original_created
    if recovered and not (snapshot.matchup_factors or {}).get('recovery', {}).get('original_values_recovered'):
        raise ValueError('Thunderpick archived timestamp repair requires original recovery provenance')
    # All prerequisites checked before writes. Repeating this repair is a no-op.
    for row, timestamp in pending:
        row.starts_at = timestamp
    if recovered:
        previous = utc(snapshot.created_at).isoformat()
        snapshot.created_at = original_created
        factors = dict(snapshot.matchup_factors or {})
        factors['recovery'] = {**factors['recovery'], 'restored_snapshot_created_at': previous,
            'original_timestamp_artifact': ARTIFACT}
        snapshot.matchup_factors = factors
    session.flush()
    return {'kickoffs': len(pending), 'archived_timestamp': int(recovered)}
