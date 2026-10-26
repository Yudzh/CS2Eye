from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.analytics.temporary_replacement_config import stand_in_penalty
from cs2eye.services.team_roster_service import get_or_create_roster
from cs2eye.models.demo import DemoTeamRoster
from cs2eye.models.demo_file import DemoFile
from cs2eye.models.match import Match, Tournament, TournamentRosterOverride, TournamentRosterCheck, TournamentTeam
from cs2eye.models.team import AnalystFactor, Player, Team, TeamRoster, TeamRosterMember


PRIORITY = {"MANUAL": 3, "CONFIRMED": 2, "DETECTED": 1, "REJECTED": 0}


def roster_applicability(current: set[int], historical: set[int]) -> float:
    if not current or not historical:
        return 0.0
    shared = len(current & historical)
    return {5: 1.0, 4: 0.8, 3: 0.6}.get(shared, 0.2 if shared == 2 else 0.0)


async def resolve_roster(session: AsyncSession, team: Team, as_of: date, *, historical: bool) -> TeamRoster | None:
    """Point-in-time roster resolution, shared by TeamStrengthV3Service and EffectiveRosterService.

    `historical=False` (as_of is today or a not-yet-played future date) trusts team.current_roster_id
    directly. `historical=True` reconstructs the roster as it stood strictly before `as_of` from demo
    evidence (falling back to date-windowed TeamRoster rows), because team.current_roster_id is a mutable
    "whoever is current roster TODAY" pointer with no memory of past lineups -- using it for a past as_of
    leaks the team's present-day roster into a prediction about the past. See docs/
    win_probability_backtest_log.md for the Vitality/jL case this was found from.
    """
    if not historical and team.current_roster_id:
        current = await session.get(TeamRoster, team.current_roster_id)
        return current if current and current.resolution_status == "complete" else None
    roster_id = await session.scalar(select(DemoTeamRoster.roster_id).join(
        DemoFile, DemoFile.id == DemoTeamRoster.demo_file_id).where(
            DemoTeamRoster.team_id == team.id, DemoTeamRoster.resolution_status == "complete",
            DemoTeamRoster.roster_id.is_not(None), DemoFile.match_date < as_of).order_by(
                DemoFile.match_date.desc(), DemoFile.id.desc()).limit(1))
    if roster_id: return await session.get(TeamRoster, roster_id)
    return await session.scalar(select(TeamRoster).where(TeamRoster.team_id == team.id, TeamRoster.source != "tournament",
        (TeamRoster.active_from.is_(None) | (TeamRoster.active_from < as_of)),
        (TeamRoster.active_to.is_(None) | (TeamRoster.active_to >= as_of))).order_by(TeamRoster.active_from.desc()).limit(1))


class EffectiveRosterService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _context(self, team_id: int, tournament_id: int | None, match_id: int | None):
        match = await self.session.get(Match, match_id) if match_id is not None else None
        if match is not None:
            if team_id not in {match.team_a_id, match.team_b_id}:
                raise ValueError("Team does not participate in match")
            if tournament_id is not None and match.tournament_id != tournament_id:
                raise ValueError("Match belongs to another tournament")
            tournament_id = match.tournament_id
        tournament = await self.session.get(Tournament, tournament_id) if tournament_id is not None else None
        return tournament_id, tournament, match

    async def get_effective_roster(self, team_id: int, tournament_id: int | None,
                                   match_id: int | None = None, as_of: date | datetime | None = None, *,
                                   permanent_player_ids: list[int] | None = None,
                                   known_before: date | None = None) -> dict[str, Any]:
        team = await self.session.get(Team, team_id)
        if team is None:
            raise ValueError("Team not found")
        tournament_id, tournament, match = await self._context(team_id, tournament_id, match_id)
        point = as_of.date() if isinstance(as_of, datetime) else as_of
        point = point or (match.match_date if match else date.today())
        if permanent_player_ids is not None:
            permanent_ids = list(permanent_player_ids)
        else:
            roster = await resolve_roster(self.session, team, point, historical=point < date.today())
            members = list((await self.session.scalars(select(TeamRosterMember).where(
                TeamRosterMember.roster_id == roster.id,
                TeamRosterMember.player_id.is_not(None)))).all()) if roster else []
            permanent_ids = [int(x.player_id) for x in members if x.player_id is not None]
        overrides: list[TournamentRosterOverride] = []
        if tournament_id is not None:
            rows = list((await self.session.scalars(select(TournamentRosterOverride).where(
                TournamentRosterOverride.tournament_id == tournament_id,
                TournamentRosterOverride.team_id == team_id,
                TournamentRosterOverride.is_active.is_(True),
                TournamentRosterOverride.status != "REJECTED"))).all())
            for row in rows:
                start = row.valid_from or (tournament.start_date if tournament else None)
                end = row.valid_until or (tournament.end_date if tournament else None)
                known = row.source_published_at or row.detected_at or row.created_at
                if known_before is not None and (known is None or known.date() >= known_before):
                    continue
                if start and point < start or end and point > end:
                    continue
                if as_of is not None and known is not None and known.date() > point:
                    continue
                overrides.append(row)
        capture = await self.session.scalar(select(TournamentRosterCheck).where(
            TournamentRosterCheck.tournament_id == tournament_id,
            TournamentRosterCheck.team_id == team_id)) if tournament_id is not None else None
        snapshot_active = bool(capture and capture.roster_ids
            and (not tournament.start_date or point >= tournament.start_date)
            and (not tournament.end_date or point <= tournament.end_date)
            and (not capture.checked_at or capture.checked_at.date() <= point)
            and (known_before is None or (capture.checked_at is not None and capture.checked_at.date() < known_before)))
        manual = any(x.status == "MANUAL" for x in overrides)
        if snapshot_active:
            permanent_ids = list(capture.baseline_ids)
        # Resolve each outgoing slot independently; this supports multiple replacements.
        selected: dict[int, TournamentRosterOverride] = {}
        warnings: list[str] = []
        for row in sorted(overrides, key=lambda x: (PRIORITY[x.status], x.updated_at or x.created_at, x.id), reverse=True):
            previous = selected.get(row.player_out_id)
            if previous is None:
                selected[row.player_out_id] = row
            elif previous.status == "MANUAL" and row.status != "MANUAL":
                warnings.append("AUTO lineup conflicts with manual override and was ignored.")
        applied = list(selected.values())
        effective_ids = list(capture.roster_ids) if snapshot_active and not manual else list(permanent_ids)
        valid_applied: list[TournamentRosterOverride] = []
        for row in applied:
            if row.player_out_id in effective_ids and row.player_in_id not in effective_ids:
                effective_ids[effective_ids.index(row.player_out_id)] = row.player_in_id
                valid_applied.append(row)
            elif snapshot_active and not manual and row.player_in_id in effective_ids and row.player_out_id not in effective_ids:
                valid_applied.append(row)
            else:
                warnings.append(f"Override {row.id} is inconsistent with permanent/effective roster and was ignored.")
        if snapshot_active and manual and set(capture.roster_ids) != set(effective_ids):
            warnings.append("Состав источника расходится с ручной заменой; ручной состав сохранён.")
        players = list((await self.session.scalars(select(Player).where(Player.id.in_(set(permanent_ids + effective_ids + ((capture.roster_ids or []) + capture.baseline_ids if capture else [])))))).all())
        by_id = {x.id: x for x in players}
        serialize = lambda pid: {"id": pid, "nickname": by_id[pid].nickname} if pid in by_id else {"id": pid, "nickname": str(pid)}
        replacements = [{"id": x.id, "player_out": serialize(x.player_out_id), "player_in": serialize(x.player_in_id),
                         "status": x.status, "source_type": x.source_type,
                         "source_reference": x.source_reference} for x in valid_applied]
        temporary = [x for x in valid_applied if x.status in {"MANUAL", "CONFIRMED"}]
        statuses = [x.status for x in valid_applied]
        if "DETECTED" in statuses:
            warnings.append("Обнаружено изменение состава, временный статус не подтверждён.")
        source = "MANUAL" if "MANUAL" in statuses else "AUTO" if statuses else ("PANDASCORE_TOURNAMENT_ROSTER" if "api.pandascore.co/" in capture.source else "BO3_TEAM_ROSTER") if snapshot_active else "PERMANENT"
        return {"team_id": team_id, "tournament_id": tournament_id,
                "permanent_roster": [serialize(x) for x in permanent_ids],
                "effective_roster": [serialize(x) for x in effective_ids],
                "players": [serialize(x) for x in effective_ids], "roster_source": source,
                "override_status": max(statuses, key=lambda x: PRIORITY[x]) if statuses else None,
                "replacements": replacements, "has_temporary_replacement": bool(temporary),
                "stand_in_penalty": stand_in_penalty(len(temporary)),
                "reliability": "confirmed" if statuses and all(x in {"MANUAL", "CONFIRMED"} for x in statuses) else "detected" if statuses or snapshot_active else "permanent",
                "warnings": list(dict.fromkeys(warnings)),
                "roster_check": {"status": capture.status, "baseline": [serialize(x) for x in capture.baseline_ids],
                    "roster": [serialize(x) for x in (capture.roster_ids or [])],
                    "added": [serialize(x) for x in (capture.added_ids or [])],
                    "missing": [serialize(x) for x in (capture.missing_ids or [])],
                    "checked_at": capture.checked_at, "source": capture.source, "error": capture.error,
                    "source_label": ("Ожидаемый состав турнира PandaScore; не подтверждённая пятёрка конкретного матча" if "api.pandascore.co/" in capture.source else "Командный Roster BO3.gg; не подтверждённая заявка организатора")} if capture else None,
                "analytical_factors": [{"type": "TEMPORARY_REPLACEMENT", "sign": "NEGATIVE", "scope": "TOURNAMENT",
                    "player_in": x["player_in"], "player_out": x["player_out"],
                    "text": f"Временная замена: {x['player_in']['nickname']} играет вместо {x['player_out']['nickname']}. Состав имеет ограниченную сыгранность."} for x in replacements if x["status"] in {"MANUAL", "CONFIRMED"}]}

    async def create_manual(self, tournament_id: int, team_id: int, player_out_id: int,
                            player_in_id: int, **values) -> TournamentRosterOverride:
        tournament = await self.session.get(Tournament, tournament_id)
        if tournament is None or await self.session.scalar(select(TournamentTeam.id).where(
                TournamentTeam.tournament_id == tournament_id, TournamentTeam.team_id == team_id)) is None:
            raise ValueError("Team is not a tournament participant")
        effective = await self.get_effective_roster(team_id, tournament_id, as_of=tournament.start_date)
        if player_out_id not in {x["id"] for x in effective["permanent_roster"]}:
            raise ValueError("player_out must belong to permanent roster")
        if player_in_id == player_out_id:
            raise ValueError("player_in and player_out must differ")
        if player_in_id in {x["id"] for x in effective["effective_roster"]}:
            raise ValueError("player_in is already in effective roster")
        existing = await self.session.scalar(select(TournamentRosterOverride).where(
            TournamentRosterOverride.tournament_id == tournament_id,
            TournamentRosterOverride.team_id == team_id,
            TournamentRosterOverride.player_out_id == player_out_id,
            TournamentRosterOverride.status == "MANUAL", TournamentRosterOverride.is_active.is_(True)))
        if existing:
            raise ValueError("Permanent player already has an active manual replacement")
        row = TournamentRosterOverride(tournament_id=tournament_id, team_id=team_id,
            player_out_id=player_out_id, player_in_id=player_in_id, status="MANUAL", source_type="MANUAL",
            valid_from=values.get("valid_from") or tournament.start_date,
            valid_until=values.get("valid_until") or tournament.end_date,
            notes=values.get("notes"), created_by=values.get("created_by"))
        self.session.add(row)
        await self.session.flush()
        await self.sync_analyst_factor(row)
        ids = [x["id"] for x in effective["effective_roster"]]
        if player_out_id not in ids:
            ids = [x["id"] for x in effective["permanent_roster"]]
        ids[ids.index(player_out_id)] = player_in_id
        players = list((await self.session.scalars(select(Player).where(Player.id.in_(ids)))).all())
        if len(players) == 5:
            await get_or_create_roster(self.session, team_id, players, source="tournament")
        return row

    async def sync_analyst_factor(self, row: TournamentRosterOverride) -> AnalystFactor:
        """Create/update the real analyst factor represented by a roster override."""
        tournament = await self.session.get(Tournament, row.tournament_id)
        players = list((await self.session.scalars(select(Player).where(
            Player.id.in_({row.player_out_id, row.player_in_id})
        ))).all())
        names = {player.id: player.nickname for player in players}
        text = (
            f"Временная замена на {tournament.name}: "
            f"{names.get(row.player_in_id, row.player_in_id)} играет вместо "
            f"{names.get(row.player_out_id, row.player_out_id)}. "
            "Ограниченная сыгранность состава."
        )
        factor = await self.session.get(AnalystFactor, row.analyst_factor_id) if row.analyst_factor_id else None
        if factor is None:
            factor = AnalystFactor(team_id=row.team_id, factor_type="negative", category="roster",
                environment=tournament.environment if tournament.environment in {"lan", "online"} else "any",
                text=text, players=players)
            self.session.add(factor)
            await self.session.flush()
            row.analyst_factor_id = factor.id
        factor.text = text
        factor.is_active = row.is_active and row.status != "REJECTED"
        start = row.valid_from or tournament.start_date
        end = row.valid_until or tournament.end_date
        factor.valid_from = datetime.combine(start, time.min, UTC) if start else None
        # The upper bound is exclusive; time.max keeps the factor active for the whole final day.
        factor.valid_until = datetime.combine(end, time.max, UTC) if end else None
        factor.players = players
        await self.session.flush()
        return factor
