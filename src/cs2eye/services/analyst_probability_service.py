"""Explicit, separately reported corrections after the ML calculation."""
from datetime import UTC, date, datetime
from sqlalchemy import or_, select
from cs2eye.models.match import Match
from cs2eye.models.team import AnalystFactor, Team
from cs2eye.services.analyst_context_service import factor_status


async def analyst_probability_adjustment(session, a, b, probability, *, series_id=None, as_of=None, team_ids=None):
    if probability is None:
        return probability, None
    match = await session.get(Match, series_id) if series_id else None
    environment = match.environment if match else None
    cutoff = as_of or date.today()
    moment = datetime.combine(cutoff, datetime.min.time(), UTC) if cutoff < date.today() else datetime.now(UTC)
    rows = list((await session.scalars(select(AnalystFactor).where(
        AnalystFactor.team_id.in_([a,b] if team_ids is None else [team for team in [a,b] if team in team_ids]), AnalystFactor.is_active.is_(True),
        AnalystFactor.probability_bonus_pp > 0,
        or_(AnalystFactor.match_id.is_(None), AnalystFactor.match_id == series_id),
        AnalystFactor.map_name.is_(None),
    ).order_by(AnalystFactor.id))).all())
    factors = []
    for row in rows:
        created = row.created_at.replace(tzinfo=UTC) if row.created_at.tzinfo is None else row.created_at
        if created > moment or factor_status(row, moment) != "active":
            continue
        if row.environment != "any" and row.environment != environment:
            continue
        sign = 1 if row.factor_type == "positive" else -1
        impact = row.probability_bonus_pp * sign * (1 if row.team_id == a else -1)
        factors.append({"id": row.id, "team_id": row.team_id, "text": row.text,
                        "impact_team_a_pp": impact, "match_id": row.match_id})
    if not factors:
        return probability, None
    adjusted = max(.01, min(.99, probability + sum(row['impact_team_a_pp'] for row in factors)/100))
    return adjusted, {"base_team_a_probability": probability,
                      "adjusted_team_a_probability": adjusted,
                      "impact_team_a_pp": (adjusted-probability)*100, "factors": factors}
