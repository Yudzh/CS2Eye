from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from cs2eye.models.team import AnalystFactor, AnalystFactorPlayer, Player, Team, TeamParticipantMembership


def utc_now() -> datetime:
    return datetime.now(UTC)


def factor_status(factor: AnalystFactor, as_of: datetime | None = None) -> str:
    moment = as_of or utc_now()
    def aware(value: datetime | None) -> datetime | None:
        return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value
    if not factor.is_active:
        return "inactive"
    if aware(factor.valid_from) and moment < aware(factor.valid_from):
        return "scheduled"
    if aware(factor.valid_until) and moment >= aware(factor.valid_until):
        return "expired"
    return "active"


class AnalystContextService:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _active_conditions(self, as_of: datetime):
        return (
            AnalystFactor.is_active.is_(True),
            AnalystFactor.created_at <= as_of,
            or_(AnalystFactor.valid_from.is_(None), AnalystFactor.valid_from <= as_of),
            or_(AnalystFactor.valid_until.is_(None), as_of < AnalystFactor.valid_until),
        )

    async def list(self, *, team_id: int | None = None, player_id: int | None = None,
                   coach_id: int | None = None, map_name: str | None = None,
                   environment: str | None = None, factor_type: str | None = None,
                   category: str | None = None, is_active: bool | None = None,
                   as_of: datetime | None = None, active_at: bool = False) -> list[AnalystFactor]:
        query = select(AnalystFactor).options(selectinload(AnalystFactor.players), selectinload(AnalystFactor.coach))
        if team_id is not None: query = query.where(AnalystFactor.team_id == team_id)
        if player_id is not None: query = query.join(AnalystFactorPlayer).where(AnalystFactorPlayer.player_id == player_id)
        if coach_id is not None: query = query.where(AnalystFactor.coach_id == coach_id)
        if map_name is not None: query = query.where(AnalystFactor.map_name == (map_name.lower() or None))
        if environment is not None: query = query.where(AnalystFactor.environment == environment)
        if factor_type is not None: query = query.where(AnalystFactor.factor_type == factor_type)
        if category is not None: query = query.where(AnalystFactor.category == category)
        if is_active is not None: query = query.where(AnalystFactor.is_active == is_active)
        if active_at:
            query = query.where(*self._active_conditions(as_of or utc_now()))
        return list((await self.session.scalars(query.order_by(AnalystFactor.created_at.desc(), AnalystFactor.id.desc()))).unique())

    async def relevant(self, team_id: int, *, maps: list[str] | None = None,
                       environment: str | None = None, as_of: datetime | None = None) -> tuple[list[AnalystFactor], list[AnalystFactor]]:
        all_active = await self.list(team_id=team_id, as_of=as_of, active_at=True)
        roster_ids = set((await self.session.scalars(select(TeamParticipantMembership.player_id).where(
            TeamParticipantMembership.team_id == team_id, TeamParticipantMembership.is_active.is_(True),
        ))).all())
        map_set = {item.lower() for item in maps or []}
        def score(factor: AnalystFactor) -> tuple[int, datetime]:
            points = 0
            if factor.map_name and factor.map_name in map_set: points += 32
            elif factor.map_name is None: points += 4
            if environment and factor.environment == environment: points += 16
            elif factor.environment == "any": points += 3
            if any(player.id in roster_ids for player in factor.players): points += 8
            if factor.coach_id in roster_ids: points += 6
            if not factor.players and factor.coach_id is None: points += 2
            return points, factor.created_at
        return sorted(all_active, key=score, reverse=True), all_active

    async def structured(self, team_id: int, *, as_of: datetime | None = None,
                         maps: list[str] | None = None, environment: str | None = None) -> dict:
        team = await self.session.get(Team, team_id)
        if team is None: raise LookupError("Команда не найдена.")
        relevant, _ = await self.relevant(team_id, maps=maps, environment=environment, as_of=as_of)
        result = {"team": team.name, "positive": [], "negative": []}
        for factor in relevant:
            result[factor.factor_type].append({"category": factor.category, "map": factor.map_name,
                "environment": factor.environment, "players": [p.nickname for p in factor.players],
                "coach": factor.coach.nickname if factor.coach else None, "text": factor.text})
        return result
