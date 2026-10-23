from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.core.config import settings
from cs2eye.integrations.bo3.client import Bo3Client
from cs2eye.models.match import Tournament, TournamentRosterCheck, TournamentRosterOverride, TournamentTeam
from cs2eye.models.team import Player, Team
from cs2eye.services.effective_roster_service import EffectiveRosterService
from cs2eye.services.team_roster_service import build_roster_fingerprint, get_or_create_roster


@dataclass
class LineupResult:
    availability: str
    player_ids: list[int] = field(default_factory=list)
    confidence: str = "unavailable"
    source_reference: str | None = None


def select_roster_players(detail):
    # Match the integration's established active membership rules; never truncate.
    return [p for p in detail.players if p.is_coach is False and not p.is_substitute
            and p.status == 1 and p.team_id == detail.id and p.id > 0]


class Bo3LineupSourceAdapter:
    def __init__(self, session):
        self.session = session

    async def get_tournament_lineup(self, tournament, team):
        async with Bo3Client() as client:
            detail = await client.fetch_team(team.bo3_id, team.bo3_slug)
        selected = select_roster_players(detail)
        if len(selected) != 5 or len({p.id for p in selected}) != 5:
            return LineupResult("partial")
        ids = []
        for item in selected:
            player = await self.session.scalar(select(Player).where(Player.bo3_id == item.id))
            if player is None:
                player = Player(bo3_id=item.id, bo3_slug=item.slug, nickname=item.nickname,
                                is_analytics_active=False)
                self.session.add(player)
                await self.session.flush()
            ids.append(player.id)
        return LineupResult("available", ids, "team_roster",
                            f"{settings.bo3_site_base_url}/api/v1/teams/{team.bo3_slug}")


class TournamentLineupMonitor:
    def __init__(self, session: AsyncSession, adapter=None):
        self.session = session
        self.adapter = adapter or Bo3LineupSourceAdapter(session)

    async def check(self, tournament_id: int, team_id: int, match_id: int | None = None) -> dict:
        # Event lock serializes automatic/manual requests, including first-row creation.
        tournament = await self.session.scalar(select(Tournament).where(
            Tournament.id == tournament_id).with_for_update())
        team = await self.session.get(Team, team_id)
        participant = await self.session.scalar(select(TournamentTeam.id).where(
            TournamentTeam.tournament_id == tournament_id, TournamentTeam.team_id == team_id))
        if not tournament or not team or participant is None:
            raise ValueError("Team is not a tournament participant")
        if tournament.start_date and datetime.now(UTC).date() < tournament.start_date:
            return {"status": "not_due", "source": "BO3 team Roster", "created": 0}
        row = await self.session.scalar(select(TournamentRosterCheck).where(
            TournamentRosterCheck.tournament_id == tournament_id, TournamentRosterCheck.team_id == team_id))
        if row and row.roster_ids:
            return {"status": row.status, "source": row.source, "created": 0}
        if row is None:
            baseline = await EffectiveRosterService(self.session).get_effective_roster(team_id, None)
            row = TournamentRosterCheck(tournament_id=tournament_id, team_id=team_id,
                baseline_ids=[p["id"] for p in baseline["permanent_roster"]], status="pending",
                source=f"{settings.bo3_site_base_url}/api/v1/teams/{team.bo3_slug}")
            self.session.add(row)
            await self.session.flush()
        row.checked_at = datetime.now(UTC)
        try:
            # A failed response must not leave partially imported players behind.
            async with self.session.begin_nested():
                result = await self.adapter.get_tournament_lineup(tournament, team)
                if result.availability != "available":
                    raise ValueError("BO3 team Roster is incomplete or unavailable")
                build_roster_fingerprint(result.player_ids)
                if len((await self.session.scalars(select(Player.id).where(
                        Player.id.in_(result.player_ids)))).all()) != 5:
                    raise ValueError("Unresolved BO3 players")
                players = list((await self.session.scalars(select(Player).where(Player.id.in_(result.player_ids)))).all())
                await get_or_create_roster(self.session, team_id, players, source="tournament")
                await self.session.flush()
        except Exception as exc:
            row.status = "partial" if isinstance(exc, ValueError) else "error"
            row.error = str(exc)
            await self.session.flush()
            return {"status": row.status, "source": row.source, "created": 0}
        row.roster_ids = sorted(result.player_ids)
        row.added_ids = sorted(set(row.roster_ids) - set(row.baseline_ids))
        row.missing_ids = sorted(set(row.baseline_ids) - set(row.roster_ids))
        row.source = result.source_reference or row.source
        manual = list((await self.session.scalars(select(TournamentRosterOverride).where(
            TournamentRosterOverride.tournament_id == tournament_id,
            TournamentRosterOverride.team_id == team_id, TournamentRosterOverride.status == "MANUAL",
            TournamentRosterOverride.is_active.is_(True)).order_by(TournamentRosterOverride.id))).all())
        manual_ids = list(row.baseline_ids)
        for override in manual:
            if override.player_out_id in manual_ids and override.player_in_id not in manual_ids:
                manual_ids[manual_ids.index(override.player_out_id)] = override.player_in_id
        conflict = bool(manual and set(manual_ids) != set(row.roster_ids))
        row.status = "conflict" if conflict else "changed" if row.added_ids or row.missing_ids else "unchanged"
        row.error = None
        from cs2eye.services.tournament_prediction_service import invalidate_tournament_predictions
        await invalidate_tournament_predictions(self.session, tournament_id)
        await self.session.flush()
        return {"status": row.status, "source": row.source, "created": 0 if manual else 1,
                "added_ids": row.added_ids, "missing_ids": row.missing_ids}

    async def check_due(self, today: date | None = None):
        today = today or datetime.now(UTC).date()
        participants = (await self.session.execute(select(TournamentTeam.tournament_id, TournamentTeam.team_id)
            .join(Tournament, Tournament.id == TournamentTeam.tournament_id)
            .where(Tournament.start_date <= today,
                   (Tournament.end_date >= today) | (Tournament.end_date.is_(None) & (Tournament.start_date == today)))
            .order_by(TournamentTeam.tournament_id, TournamentTeam.team_id))).all()
        for tournament_id, team_id in participants:
            await self.check(tournament_id, team_id)
            await self.session.commit()
