"""Supply the out-of-top-40 ranking needed for the 9z–TYLOO forecast.

Verified on 2026-10-26 against BO3's /team_rankings endpoint, scope=cs2,
worldwide page 2 (30 entries per page), team_id=757. The response identifies
this as BO3's internal ranking, not an official Valve publication:
ranking_date=2026-10-26, rank=44, score=1150.3537, rank_diff=0.
Normal top-40 imports omit this tournament participant. Do not activate it in
the top-30 analytics list or manufacture a historical ranking import run.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from cs2eye.models.team import Team

RANKING_DATE = date(2026, 10, 26)


def apply(session: Session) -> int:
    team = session.scalar(select(Team).where(Team.bo3_id == 757).with_for_update())
    if team is None:
        raise ValueError("Bucharest TYLOO ranking requires the imported BO3 team 757")
    # Replaying this release must preserve later ranking updates.
    if team.ranking_date is not None and team.ranking_date >= RANKING_DATE:
        if team.current_rank is not None and team.current_rank > 0:
            return team.id
        if team.ranking_date > RANKING_DATE:
            raise ValueError("TYLOO has a newer ranking date but no usable rank; refresh its ranking")
    team.current_rank = 44
    team.current_points = Decimal("1150.3537")
    team.rank_change = 0
    team.ranking_date = RANKING_DATE
    session.flush()
    return team.id
