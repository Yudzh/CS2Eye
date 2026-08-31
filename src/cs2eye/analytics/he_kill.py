from __future__ import annotations


HE_GRENADE_WEAPONS = frozenset({"he", "hegrenade", "he_grenade"})


def normalize_kill_weapon(value: object) -> str | None:
    """Normalize DemoKill.weapon values without changing demo parsing."""
    if value is None:
        return None
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    while normalized.startswith("weapon_"):
        normalized = normalized.removeprefix("weapon_")
    return normalized or None


def is_he_grenade_weapon(value: object) -> bool:
    return normalize_kill_weapon(value) in HE_GRENADE_WEAPONS
