from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.analytics.he_kill import is_he_grenade_weapon
from cs2eye.analytics.he_kill_config import (
    CONFIDENCE_HIGH_MIN_COMBINED_MAPS,
    CONFIDENCE_HIGH_MIN_MAPS_PER_TEAM,
    CONFIDENCE_MIN_COMBINED_MAPS,
    GLOBAL_BASELINE_PRIOR_MAPS,
    GLOBAL_BASELINE_RATE,
    HE_KILL_MODEL_VERSION,
    HE_KILL_WINDOW_DAYS,
    MAP_BASELINE_PRIOR_MAPS,
    TEAM_MAP_PRIOR_MAPS,
)
from cs2eye.models.demo import DemoKill, DemoMapResult
from cs2eye.models.demo_file import DemoFile
from cs2eye.models.match import MapPoolEntry
from cs2eye.services.calculated_veto_service import DEFAULT_ACTIVE_POOL


@dataclass(frozen=True)
class TeamMapHEStats:
    maps_played: int = 0
    maps_with_he_kill: int = 0
    he_kills: int = 0

    @property
    def he_kills_per_map(self) -> float:
        return self.he_kills / self.maps_played if self.maps_played else 0.0

    @property
    def map_he_kill_rate(self) -> float:
        return self.maps_with_he_kill / self.maps_played if self.maps_played else 0.0


def _normalize_map(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().lower()
    return value.removeprefix("de_") or None


class HEKillByMapService:
    """Hierarchical deterministic estimate of at least one HE kill per map."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def calculate(
        self,
        team_a_id: int,
        team_b_id: int,
        *,
        as_of: date | datetime,
        exclude_match_id: int | None = None,
    ) -> list[dict]:
        cutoff = as_of.date() if isinstance(as_of, datetime) else as_of
        pool = await self._map_pool(cutoff)
        stats = await self._stats(cutoff, exclude_match_id)

        global_maps = sum(item.maps_played for item in stats.values())
        global_successes = sum(item.maps_with_he_kill for item in stats.values())
        global_rate = (
            global_successes + GLOBAL_BASELINE_RATE * GLOBAL_BASELINE_PRIOR_MAPS
        ) / (global_maps + GLOBAL_BASELINE_PRIOR_MAPS)

        rows = []
        for map_name in pool:
            map_rows = [item for (team_id, name), item in stats.items() if name == map_name]
            map_maps = sum(item.maps_played for item in map_rows)
            map_successes = sum(item.maps_with_he_kill for item in map_rows)
            map_rate = (
                map_successes + global_rate * MAP_BASELINE_PRIOR_MAPS
            ) / (map_maps + MAP_BASELINE_PRIOR_MAPS)

            a = stats.get((team_a_id, map_name), TeamMapHEStats())
            b = stats.get((team_b_id, map_name), TeamMapHEStats())
            rate_a = self._team_rate(a, map_rate)
            rate_b = self._team_rate(b, map_rate)
            probability = 1.0 - (1.0 - rate_a) * (1.0 - rate_b)
            rows.append({
                "map": map_name,
                "probability": round(max(0.0, min(1.0, probability)), 6),
                "confidence": self._confidence(a.maps_played, b.maps_played),
                "team_a_sample": a.maps_played,
                "team_b_sample": b.maps_played,
            })
        return sorted(rows, key=lambda item: (-item["probability"], item["map"]))

    async def _map_pool(self, as_of: date) -> list[str]:
        names = list((await self.session.scalars(
            select(MapPoolEntry.map_name).where(
                or_(MapPoolEntry.active_from.is_(None), MapPoolEntry.active_from <= as_of),
                or_(MapPoolEntry.active_to.is_(None), MapPoolEntry.active_to >= as_of),
            )
        )).all())
        normalized = sorted({name for value in names if (name := _normalize_map(value))})
        if len(normalized) == 7:
            return normalized
        active = list((await self.session.scalars(
            select(MapPoolEntry.map_name).where(MapPoolEntry.is_active.is_(True))
        )).all())
        active_normalized = sorted({name for value in active if (name := _normalize_map(value))})
        # A partial pool is more dangerous than the repository's known active pool.
        return active_normalized if len(active_normalized) == 7 else sorted(DEFAULT_ACTIVE_POOL)

    async def _stats(
        self, cutoff: date, exclude_match_id: int | None,
    ) -> dict[tuple[int, str], TeamMapHEStats]:
        filters = [
            DemoFile.match_date >= cutoff - timedelta(days=HE_KILL_WINDOW_DAYS),
            DemoFile.match_date < cutoff,
        ]
        if exclude_match_id is not None:
            filters.append(or_(DemoFile.match_id.is_(None), DemoFile.match_id != exclude_match_id))
        maps = (await self.session.execute(
            select(DemoFile.id, DemoMapResult.map_name, DemoMapResult.team_a_id, DemoMapResult.team_b_id)
            .join(DemoMapResult, DemoMapResult.demo_file_id == DemoFile.id)
            .where(*filters)
        )).all()
        demo_ids = [row.id for row in maps]
        kills_by_demo_team: dict[tuple[int, int], int] = defaultdict(int)
        if demo_ids:
            kills = list((await self.session.scalars(
                select(DemoKill).where(DemoKill.demo_file_id.in_(demo_ids))
            )).all())
            for kill in kills:
                if not self._valid_he_kill(kill):
                    continue
                kills_by_demo_team[(kill.demo_file_id, kill.attacker_team_id)] += 1

        mutable: dict[tuple[int, str], list[int]] = defaultdict(lambda: [0, 0, 0])
        for row in maps:
            map_name = _normalize_map(row.map_name)
            if map_name is None:
                continue
            for team_id in (row.team_a_id, row.team_b_id):
                if team_id is None:
                    continue
                he_kills = kills_by_demo_team.get((row.id, team_id), 0)
                values = mutable[(team_id, map_name)]
                values[0] += 1
                values[1] += int(he_kills > 0)
                values[2] += he_kills
        return {key: TeamMapHEStats(*values) for key, values in mutable.items()}

    @staticmethod
    def _valid_he_kill(kill: DemoKill) -> bool:
        if kill.is_teamkill or kill.is_suicide or not is_he_grenade_weapon(kill.weapon):
            return False
        if kill.attacker_team_id is not None and kill.victim_team_id is not None:
            return kill.attacker_team_id != kill.victim_team_id
        return bool(
            kill.attacker_team_name and kill.victim_team_name
            and kill.attacker_team_name.strip().casefold() != kill.victim_team_name.strip().casefold()
        )

    @staticmethod
    def _team_rate(stats: TeamMapHEStats, map_rate: float) -> float:
        return (
            stats.maps_with_he_kill + map_rate * TEAM_MAP_PRIOR_MAPS
        ) / (stats.maps_played + TEAM_MAP_PRIOR_MAPS)

    @staticmethod
    def _confidence(team_a_sample: int, team_b_sample: int) -> str:
        minimum = min(team_a_sample, team_b_sample)
        combined = team_a_sample + team_b_sample
        if minimum == 0 or combined < CONFIDENCE_MIN_COMBINED_MAPS:
            return "low"
        if (
            minimum >= CONFIDENCE_HIGH_MIN_MAPS_PER_TEAM
            and combined >= CONFIDENCE_HIGH_MIN_COMBINED_MAPS
        ):
            return "high"
        return "medium"


__all__ = ["HEKillByMapService", "TeamMapHEStats", "HE_KILL_MODEL_VERSION"]
