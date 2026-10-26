"""Only genuine snapshots captured before kickoff count toward accuracy."""
from datetime import UTC, datetime, time


def eligibility(snapshot, match):
    if snapshot.source != 'pre_match':
        return False, 'retrospective'
    if {snapshot.team_a_id, snapshot.team_b_id} != {match.team_a_id, match.team_b_id}:
        return False, 'participants_changed'
    start = match.starts_at or datetime.combine(match.match_date, time.min, UTC)
    def utc(value):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    if utc(snapshot.created_at) >= utc(start) or utc(snapshot.as_of) >= utc(start):
        return False, 'captured_after_start'
    return True, None
