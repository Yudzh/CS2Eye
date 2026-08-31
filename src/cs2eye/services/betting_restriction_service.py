from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.team import Team


NAVI_BO3_ID = 787
NAVI_BO3_SLUGS = frozenset({"natus-vincere"})
NAVI_RULE = "navi_no_match_winner_bets"
GROUP_STAGE_RULE = "group_stage_no_match_winner_bets"
NAVI_MESSAGE = (
    "НЕ СТАВИТЬ НА NAVI И НЕ СТАВИТЬ ПРОТИВ NAVI.\n\n"
    "Для матчей NAVI рассматривать только сторонние рынки, не зависящие "
    "напрямую от победителя матча, например тоталы."
)
GROUP_STAGE_MESSAGE = (
    "НЕ СТАВИТЬ НА ПОБЕДИТЕЛЯ МАТЧА.\n\n"
    "Рассматривать только сторонние рынки:\n"
    "тоталы, HE kill, пистолетки и другие ставки, не зависящие напрямую "
    "от победителя матча."
)


def betting_restrictions_for_teams(
    teams: Iterable[Team], *, is_playoff: bool | None = None,
) -> dict:
    navi_restricted = any(
        team.bo3_id == NAVI_BO3_ID
        or (team.bo3_slug or "").strip().lower() in NAVI_BO3_SLUGS
        for team in teams
    )
    restrictions = []
    if navi_restricted:
        restrictions.append({"rule": NAVI_RULE, "message": NAVI_MESSAGE})
    if is_playoff is False:
        restrictions.append({"rule": GROUP_STAGE_RULE, "message": GROUP_STAGE_MESSAGE})
    if not restrictions:
        return {"restricted": False, "rule": None, "message": None, "restrictions": []}
    return {"restricted": True, **restrictions[0], "restrictions": restrictions}


async def resolve_betting_restrictions(
    session: AsyncSession, team_ids: Iterable[int], *, is_playoff: bool | None = None,
) -> dict:
    ids = {int(team_id) for team_id in team_ids}
    teams = list((await session.scalars(select(Team).where(Team.id.in_(ids)))).all())
    return betting_restrictions_for_teams(teams, is_playoff=is_playoff)


__all__ = [
    "GROUP_STAGE_MESSAGE", "GROUP_STAGE_RULE",
    "NAVI_BO3_ID", "NAVI_BO3_SLUGS", "NAVI_MESSAGE", "NAVI_RULE",
    "betting_restrictions_for_teams", "resolve_betting_restrictions",
]
