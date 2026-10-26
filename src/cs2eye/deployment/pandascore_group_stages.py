"""Repair imported group rounds mistaken for playoff quarter/semi finals."""
from sqlalchemy import select
from cs2eye.models.match import Match


def apply(session):
    matches = session.scalars(select(Match).where(
        Match.result_external_id.is_not(None), Match.is_playoff.is_(False),
        Match.group_name.is_not(None),
        Match.stage.in_(['quarterfinal', 'semifinal', 'final']),
    ).with_for_update()).all()
    count = 0
    for match in matches:
        evidence = (match.result_link or {}).get('_pandascore') or {}
        stage = evidence.get('tournament') or {}
        # Restrict the repair to the provider stage recorded during import.
        if stage.get('name') != match.group_name:
            continue
        match.stage = 'group'
        count += 1
    session.flush()
    return count
