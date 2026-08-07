from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.team import Player


PLAYER_NICKNAME_ALIASES = {
    "naf-fly": "naf",
    "slaxz-": "slaxz",
    "v$m": "vsm",
}


def normalize_nickname(value: str) -> str:
    normalized = value.strip().casefold()
    return PLAYER_NICKNAME_ALIASES.get(normalized, normalized)


async def link_demo_player(
    session: AsyncSession, steam_id: str | None, nickname: str,
) -> Player | None:
    if steam_id:
        player = (
            await session.execute(select(Player).where(Player.steam_id == steam_id))
        ).scalar_one_or_none()
        if player is not None:
            return player
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
