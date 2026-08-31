import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.team import Team


TEAM_NAME_ALIASES = {
    "navi": "natus vincere",
    "natus vincer": "natus vincere",
    "team vitality": "vitality",
    "mongolz": "the mongolz",
    "100t": "100 thieves",
    "aurora gaming": "aurora",
    "pain gaming": "pain",
    "team spirit": "spirit",
    "team falcons": "falcons",
    "betboom team": "betboom",
    "bb team": "betboom",
    "ninjas in pyjamas estar": "nip",
    "ninjas in pyjamas": "nip",
    "9z globant": "9z",
    "mibr los": "mibr",
    "team liquid": "liquid",
    "lynn vision gaming": "lynn vision",
    "pvision": "parivision",
    "dendele": "dendele cs",
    "sharks": "dendele cs",
}


def normalize_team_name(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    normalized = unicodedata.normalize("NFKD", value.strip().casefold())
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    normalized_name = re.sub(r"[^a-z0-9]+", " ", ascii_value).strip() or None
    return TEAM_NAME_ALIASES.get(normalized_name, normalized_name)


def team_name_aliases(value: str | None) -> set[str]:
    normalized = normalize_team_name(value)
    aliases = {normalized} if normalized else set()
    words = normalized.split() if normalized else []
    if normalized and normalized.endswith("cs2") and normalized != "cs2":
        compact_base = normalized[:-3].strip()
        if compact_base:
            aliases.add(compact_base)
    while words and words[-1] in {"clan", "esports", "cs2"}:
        words.pop()
        if words:
            aliases.add(" ".join(words))
    return aliases


@dataclass(frozen=True)
class ResolvedDemoTeam:
    team_id: int | None
    raw_name: str | None
    normalized_name: str | None
    resolution_status: str


async def resolve_demo_team(
    session: AsyncSession, raw_name: str | None, teams: list[Team] | None = None,
) -> ResolvedDemoTeam:
    normalized = normalize_team_name(raw_name)
    if normalized is None:
        return ResolvedDemoTeam(None, raw_name, None, "missing")
    candidates = teams
    if candidates is None:
        candidates = list((await session.execute(select(Team))).scalars().all())
    aliases = team_name_aliases(raw_name)
    matches = [team for team in candidates if aliases.intersection(team_name_aliases(team.name))]
    if len(matches) == 1:
        return ResolvedDemoTeam(matches[0].id, raw_name, normalized, "matched")
    return ResolvedDemoTeam(None, raw_name, normalized, "ambiguous" if matches else "not_found")


async def resolve_demo_teams(
    session: AsyncSession, names: list[str | None],
) -> list[ResolvedDemoTeam]:
    teams = list((await session.execute(select(Team))).scalars().all())
    return [await resolve_demo_team(session, name, teams) for name in names]
