"""Repair stored demo links for explicitly approved additional Steam accounts.

Do not reparse demos or change their recorded identities, outcomes or forecasts.
The Alembic migration repairs references; release preparation refreshes derived
ratings and roster aggregates before the API and bot are restarted.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from cs2eye.models.demo import (
    DemoDamageEvent, DemoKill, DemoPlayerStat, DemoRoundSwingEvent, DemoUtilityEvent,
)
from cs2eye.models.team import Player
from cs2eye.services.demo_player_link_service import PLAYER_STEAM_ID_ALIASES


def apply(session: Session) -> tuple[set[int], set[int]]:
    demo_ids, player_ids = set(), set()
    for alias, canonical in PLAYER_STEAM_ID_ALIASES.items():
        rows = list(session.scalars(select(DemoPlayerStat).where(DemoPlayerStat.steam_id == alias)))
        player = session.scalar(select(Player).where(Player.steam_id == canonical))
        owner = session.scalar(select(Player).where(Player.steam_id == alias))
        if owner is not None:
            raise ValueError(f"Additional Steam account {alias} already has a primary owner")
        if player is None:
            if rows:
                raise ValueError(f"Additional Steam account {alias} requires primary account {canonical}")
            continue
        for row in rows:
            if row.player_id not in (None, player.id):
                raise ValueError(f"Conflicting player link for Steam account {alias} in demo {row.demo_file_id}")
            duplicate = session.scalar(select(DemoPlayerStat.id).where(
                DemoPlayerStat.demo_file_id == row.demo_file_id,
                DemoPlayerStat.player_id == player.id, DemoPlayerStat.id != row.id,
            ))
            if duplicate is not None:
                raise ValueError(f"Both Steam accounts occur in demo {row.demo_file_id}")
            row.player_id = player.id
            # Event identity keys are parser-generated; use the stored key rather
            # than guessing its format from a Steam ID.
            for model, roles in (
                (DemoKill, ("attacker", "victim", "assister")),
                (DemoDamageEvent, ("attacker", "victim")),
                (DemoUtilityEvent, ("player", "target")),
                (DemoRoundSwingEvent, ("credited",)),
            ):
                for role in roles:
                    prefix = "" if role == "player" else f"{role}_"
                    id_attr = getattr(model, f"{prefix}player_id")
                    key_attr = getattr(model, f"{role}_identity_key")
                    events = session.scalars(select(model).where(
                        model.demo_file_id == row.demo_file_id, key_attr == row.identity_key,
                    ))
                    for event in events:
                        if getattr(event, id_attr.key) not in (None, player.id):
                            raise ValueError(f"Conflicting event player in demo {row.demo_file_id}")
                        setattr(event, id_attr.key, player.id)
            demo_ids.add(row.demo_file_id)
            player_ids.add(player.id)
    session.flush()
    return demo_ids, player_ids


async def prepare(factory):
    from cs2eye.services.player_internal_rating_service import recalculate_player_internal_ratings
    from cs2eye.services.team_map_aggregate_service import recalculate_demo_affected_aggregates
    from cs2eye.services.team_roster_service import resolve_demo_rosters

    async with factory() as session:
        async with session.begin():
            demo_ids, player_ids = await session.run_sync(apply)
            for demo_id in sorted(demo_ids):
                await resolve_demo_rosters(session, demo_id, replace_existing=True)
                await recalculate_demo_affected_aggregates(session, demo_id)
            for player_id in sorted(player_ids):
                await recalculate_player_internal_ratings(session, player_id, commit=False)
    return {"demos": sorted(demo_ids), "players": sorted(player_ids)}
