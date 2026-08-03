from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256
import json

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.demo import DemoMapResult, DemoPlayerStat, DemoTeamRoster
from cs2eye.models.team import Player, Team, TeamParticipantMembership, TeamRoster, TeamRosterMember


def build_roster_fingerprint(player_ids: list[int]) -> str:
    """Return the order-independent identity of exactly five linked players."""
    unique = set(player_ids)
    if len(player_ids) != 5 or len(unique) != 5 or any(not isinstance(i, int) or i <= 0 for i in player_ids):
        raise ValueError("A complete roster requires exactly five unique positive player IDs.")
    canonical = ":".join(str(player_id) for player_id in sorted(unique))
    return sha256(canonical.encode("ascii")).hexdigest()


def _diagnostic_fingerprint(team_id: int, player_ids: list[int], status: str) -> str:
    canonical = f"{status}:{team_id}:" + ":".join(map(str, sorted(set(player_ids))))
    return sha256(canonical.encode("ascii")).hexdigest()


@dataclass
class DemoRosterResolution:
    demo_file_id: int
    links_created: int = 0
    links_updated: int = 0
    rosters_created: int = 0
    warnings: list[str] = field(default_factory=list)


async def get_or_create_roster(
    session: AsyncSession, team_id: int, players: list[Player], *, source: str,
    status: str | None = None,
) -> tuple[TeamRoster, bool]:
    unique = {player.id: player for player in players}
    resolved = list(unique.values())
    resolution_status = status or (
        "complete" if len(resolved) == 5 else "partial" if len(resolved) < 5 else "needs_review"
    )
    fingerprint = (
        build_roster_fingerprint(list(unique)) if resolution_status == "complete"
        else _diagnostic_fingerprint(team_id, list(unique), resolution_status)
    )
    roster = (await session.execute(select(TeamRoster).where(
        TeamRoster.team_id == team_id, TeamRoster.fingerprint == fingerprint,
    ))).scalar_one_or_none()
    if roster is not None:
        return roster, False
    roster = TeamRoster(
        team_id=team_id, fingerprint=fingerprint, source=source,
        resolution_status=resolution_status, is_current=False,
    )
    session.add(roster)
    await session.flush()
    session.add_all([
        TeamRosterMember(
            roster_id=roster.id, player_id=player.id,
            player_name_snapshot=player.nickname,
            player_external_id=player.steam_id or str(player.bo3_id),
        ) for player in resolved
    ])
    return roster, True


async def set_current_roster(
    session: AsyncSession, team_id: int, players: list[Player], *, source: str = "manual",
    active_from: date | None = None, active_from_source: str = "unknown",
) -> TeamRoster:
    if len({player.id for player in players}) != 5:
        raise ValueError("Current roster requires exactly five unique linked players.")
    team = await session.get(Team, team_id)
    if team is None:
        raise ValueError("Team not found.")
    roster, _ = await get_or_create_roster(session, team_id, players, source=source)
    if roster.resolution_status != "complete":
        raise ValueError("Only a complete roster can be current.")
    previous = (await session.execute(select(TeamRoster).where(
        TeamRoster.team_id == team_id, TeamRoster.is_current.is_(True), TeamRoster.id != roster.id,
    ))).scalars().all()
    for old in previous:
        old.is_current = False
        if old.active_to is None and active_from is not None:
            old.active_to = active_from
    roster.is_current = True
    roster.active_from = roster.active_from or active_from
    if roster.active_from == active_from and active_from is not None:
        roster.active_from_source = active_from_source
    team.current_roster_id = roster.id
    roles = dict((await session.execute(select(
        TeamParticipantMembership.player_id, TeamParticipantMembership.role,
    ).where(
        TeamParticipantMembership.team_id == team_id,
        TeamParticipantMembership.player_id.in_([player.id for player in players]),
        TeamParticipantMembership.is_active.is_(True),
    ))).all())
    members = (await session.execute(select(TeamRosterMember).where(
        TeamRosterMember.roster_id == roster.id,
    ))).scalars().all()
    for member in members:
        member.role_snapshot = roles.get(member.player_id)
    return roster


async def resolve_demo_rosters(
    session: AsyncSession, demo_file_id: int, *, replace_existing: bool = False,
) -> DemoRosterResolution:
    output = DemoRosterResolution(demo_file_id)
    result = (await session.execute(select(DemoMapResult).where(
        DemoMapResult.demo_file_id == demo_file_id,
    ))).scalar_one_or_none()
    if result is None:
        output.warnings.append("requires_demo_reparse")
        return output
    if replace_existing:
        await session.execute(delete(DemoTeamRoster).where(DemoTeamRoster.demo_file_id == demo_file_id))
    stats = list((await session.execute(select(DemoPlayerStat).where(
        DemoPlayerStat.demo_file_id == demo_file_id,
    ))).scalars())
    for team_id, team_name in ((result.team_a_id, result.team_a_name), (result.team_b_id, result.team_b_name)):
        if team_id is None:
            output.warnings.append("missing_team_id")
            continue
        team_stats = [item for item in stats if item.demo_team_id == team_id]
        player_ids = {item.player_id for item in team_stats if item.player_id is not None}
        unresolved = [item for item in team_stats if item.player_id is None]
        count = len(player_ids)
        status = "complete" if count == 5 and not unresolved else "partial" if count < 5 else "needs_review"
        issues = []
        if count < 5: issues.append("roster_less_than_five_players")
        if count > 5: issues.append("roster_more_than_five_players")
        if unresolved: issues.append("unresolved_roster_player")
        players = list((await session.execute(select(Player).where(Player.id.in_(player_ids)))).scalars()) if player_ids else []
        roster = None
        if players:
            roster, created = await get_or_create_roster(session, team_id, players, source="demo", status=status)
            output.rosters_created += int(created)
        link = (await session.execute(select(DemoTeamRoster).where(
            DemoTeamRoster.demo_file_id == demo_file_id, DemoTeamRoster.team_id == team_id,
        ))).scalar_one_or_none()
        if link is None:
            link = DemoTeamRoster(demo_file_id=demo_file_id, demo_map_result_id=result.id, team_id=team_id,
                                  team_name_snapshot=team_name or f"Team {team_id}", resolution_status=status)
            session.add(link); output.links_created += 1
        else:
            output.links_updated += 1
        link.roster_id = roster.id if roster else None
        link.resolution_status = status
        link.issues = json.dumps(issues) if issues else None
        output.warnings.extend(issues)
    await session.flush()
    return output


async def rebuild_roster_links(
    session: AsyncSession, *, demo_file_id: int | None = None, team_id: int | None = None,
    replace_existing: bool = False,
) -> list[DemoRosterResolution]:
    query = select(DemoMapResult.demo_file_id)
    if demo_file_id is not None:
        query = query.where(DemoMapResult.demo_file_id == demo_file_id)
    if team_id is not None:
        query = query.where((DemoMapResult.team_a_id == team_id) | (DemoMapResult.team_b_id == team_id))
    ids = list((await session.execute(query)).scalars())
    return [await resolve_demo_rosters(session, item, replace_existing=replace_existing) for item in ids]
