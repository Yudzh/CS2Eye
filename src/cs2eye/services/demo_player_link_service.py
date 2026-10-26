from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.team import Player


PLAYER_NICKNAME_ALIASES = {
    "naf-fly": "naf",
    "slaxz-": "slaxz",
    "v$m": "vsm",
}

# Explicitly approved additional accounts, keyed by their canonical Steam ID.
# Keep the original account on Player and the actual account in demo records.
PLAYER_STEAM_ID_ALIASES = {
    "76561198712713132": "76561198194325317",  # dumau, October 2026
}


def normalize_nickname(value: str) -> str:
    normalized = value.strip().casefold()
    return PLAYER_NICKNAME_ALIASES.get(normalized, normalized)


async def link_demo_player(
    session: AsyncSession, steam_id: str | None, nickname: str,
) -> Player | None:
    if steam_id:
        canonical_id = PLAYER_STEAM_ID_ALIASES.get(steam_id, steam_id)
        if canonical_id != steam_id:
            owner = await session.scalar(select(Player.id).where(Player.steam_id == steam_id))
            if owner is not None:
                raise ValueError(f"Additional Steam account {steam_id} already has a primary owner")
        player = (
            await session.execute(select(Player).where(Player.steam_id == canonical_id))
        ).scalar_one_or_none()
        if player is not None:
            return player
        if canonical_id != steam_id:
            return None
    normalized = normalize_nickname(nickname)
    matches = [
        player for player in (await session.execute(select(Player))).scalars().all()
        if normalize_nickname(player.nickname) == normalized
    ]
    if len(matches) != 1:
        return None
    player = matches[0]
    if steam_id and player.steam_id is None:
        player.steam_id = steam_id
    elif steam_id and player.steam_id != steam_id:
        return None
    return player
