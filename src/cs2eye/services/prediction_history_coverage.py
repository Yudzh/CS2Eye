"""Explain the minimum historical-map requirement without running a prediction."""
from datetime import UTC, datetime
from sqlalchemy import func, select
from cs2eye.analytics.win_probability_config import MIN_HISTORICAL_MAPS_PER_TEAM
from cs2eye.models.demo import DemoMapResult
from cs2eye.models.demo_file import DemoFile
from cs2eye.models.match import Match


async def historical_map_coverage(session, match):
    cutoff = min(match.match_date, datetime.now(UTC).date())
    counts = {}
    for team_id in (match.team_a.id, match.team_b.id):
        if team_id is None:
            counts[team_id] = 0
            continue
        counts[team_id] = await session.scalar(select(func.count()).select_from(DemoFile).join(
            DemoMapResult, DemoMapResult.demo_file_id == DemoFile.id,
        ).join(Match, Match.id == DemoFile.match_id).where(
            Match.status == "completed", Match.match_date < cutoff,
            DemoMapResult.round_data_status == "complete",
            DemoMapResult.map_name.is_not(None),
            DemoMapResult.team_a_id.is_not(None), DemoMapResult.team_b_id.is_not(None),
            DemoMapResult.team_a_score.is_not(None), DemoMapResult.team_b_score.is_not(None),
            (DemoMapResult.team_a_id == team_id) | (DemoMapResult.team_b_id == team_id),
        )) or 0
    return {"as_of": cutoff, "required_maps": MIN_HISTORICAL_MAPS_PER_TEAM,
            "teams": [{"team_id": team.id, "name": team.name, "available_maps": counts[team.id]}
                      for team in (match.team_a, match.team_b)]}
