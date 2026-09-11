from __future__ import annotations
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from cs2eye.models.match import Tournament, TournamentRosterOverride
from cs2eye.models.team import Team
from cs2eye.services.effective_roster_service import EffectiveRosterService

@dataclass
class LineupResult:
    availability: str
    player_ids: list[int] = field(default_factory=list)
    confidence: str = "unavailable"
    source_reference: str | None = None

class LineupSourceAdapter(Protocol):
    async def get_tournament_lineup(self, tournament: Tournament, team: Team) -> LineupResult: ...
    async def get_match_lineup(self, match, team: Team) -> LineupResult: ...

class Bo3LineupSourceAdapter:
    """Current BO3 integration exposes team roster, not event/series lineups."""
    async def get_tournament_lineup(self, tournament, team): return LineupResult("unavailable")
    async def get_match_lineup(self, match, team): return LineupResult("unavailable")

class TournamentLineupMonitor:
    def __init__(self, session: AsyncSession, adapter: LineupSourceAdapter | None = None):
        self.session=session; self.adapter=adapter or Bo3LineupSourceAdapter()
    async def check(self, tournament_id: int, team_id: int, match_id: int | None = None) -> dict:
        tournament=await self.session.get(Tournament,tournament_id);team=await self.session.get(Team,team_id)
        if not tournament or not team: raise ValueError("Tournament or team not found")
        result=await self.adapter.get_tournament_lineup(tournament,team)
        if result.availability != "available": return {"status":"unavailable","source":"BO3","created":0}
        baseline=await EffectiveRosterService(self.session).get_effective_roster(team_id,tournament_id,as_of=tournament.start_date)
        permanent={x["id"] for x in baseline["permanent_roster"]}; detected=set(result.player_ids)
        outgoing=sorted(permanent-detected);incoming=sorted(detected-permanent)
        if len(outgoing)!=len(incoming): return {"status":"partial","source":"BO3","created":0,"warning":"Lineup difference cannot be paired safely"}
        created=0
        for out_id,in_id in zip(outgoing,incoming):
            manual=await self.session.scalar(select(TournamentRosterOverride.id).where(TournamentRosterOverride.tournament_id==tournament_id,TournamentRosterOverride.team_id==team_id,TournamentRosterOverride.player_out_id==out_id,TournamentRosterOverride.status=="MANUAL",TournamentRosterOverride.is_active.is_(True)))
            if manual: continue
            existing=await self.session.scalar(select(TournamentRosterOverride).where(TournamentRosterOverride.tournament_id==tournament_id,TournamentRosterOverride.team_id==team_id,TournamentRosterOverride.player_out_id==out_id,TournamentRosterOverride.source_type=="AUTO"))
            status="CONFIRMED" if result.confidence=="confirmed" else "DETECTED"
            if existing: existing.player_in_id=in_id;existing.status=status;existing.is_active=True;existing.source_reference=result.source_reference;existing.detected_at=datetime.now(UTC)
            else:
                existing=TournamentRosterOverride(tournament_id=tournament_id,team_id=team_id,player_out_id=out_id,player_in_id=in_id,status=status,source_type="AUTO",source_reference=result.source_reference,valid_from=tournament.start_date,valid_until=tournament.end_date,detected_at=datetime.now(UTC))
                self.session.add(existing);created+=1
            await self.session.flush()
            await EffectiveRosterService(self.session).sync_analyst_factor(existing)
        await self.session.flush();return {"status":"available","source":"BO3","created":created,"detected":len(outgoing)}
