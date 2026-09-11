from __future__ import annotations

from collections import defaultdict
from datetime import date
from math import sqrt
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.analytics.combat.core import CombatKill, calculate_combat
from cs2eye.models.demo import DemoDamageEvent, DemoKill, DemoMapResult, DemoParseRun, DemoPlayerStat, DemoRound, DemoTeamRoster
from cs2eye.models.demo_file import DemoFile
from cs2eye.services.performance_normalization_service import PerformanceNormalizationService
from cs2eye.analytics.performance_v3_config import (
    CLUTCH_DIFFICULTY_WEIGHTS, PERFORMANCE_PROFILE_MODEL_VERSION as MODEL_VERSION,
    PROFILE_SAMPLE_TARGETS, PROFILE_WEIGHTS,
)

SCOPES = ("overall", "ct", "t")
PROFILE_KEYS = ("firepower", "entrying", "trading", "opening", "clutching", "sniping", "utility")
AWP_WEAPONS = {"awp", "weapon_awp"}


def rank_group_v3(rank: int | None) -> str:
    if rank is None: return "unknown"
    if rank <= 10: return "top_1_10"
    if rank <= 20: return "top_11_20"
    if rank <= 30: return "top_21_30"
    return "others"


def _num(value: Any) -> float | None:
    try: return None if value is None else float(value)
    except (TypeError, ValueError): return None


def _ratio(num: float, den: float) -> float | None:
    return num / den if den else None


def _sum_json(items: list[dict], key: str) -> float:
    return sum(_num(item.get(key)) or 0.0 for item in items)


def _utility(items: list[dict], scope: str) -> dict[str, float | None]:
    selected = [item if scope == "overall" else item.get(scope, {}) for item in items]
    rounds = _sum_json(selected, "rounds_played")
    flashes = _sum_json(selected, "flash_thrown")
    enemy_duration = _sum_json(selected, "enemy_flash_duration") if scope == "overall" else 0
    return {
        "rounds": rounds,
        "flash_assists_per_round": _ratio(_sum_json(selected, "flash_assists"), rounds),
        "enemies_flashed_per_flash": _ratio(_sum_json(selected, "enemies_flashed"), flashes),
        "enemy_flash_seconds_per_flash": _ratio(enemy_duration, flashes) if scope == "overall" else None,
        "utility_damage_per_round": _ratio(_sum_json(selected, "utility_damage"), rounds),
        "teammates_flashed_per_flash": _ratio(_sum_json(selected, "teammates_flashed"), flashes),
    }


def _combat(items: list[dict], scope: str) -> dict[str, float | None]:
    if scope == "overall":
        opening_kills = _sum_json(items, "opening_kills"); opening_deaths = _sum_json(items, "opening_deaths")
    else:
        opening_kills = _sum_json(items, f"{scope}_opening_kills"); opening_deaths = _sum_json(items, f"{scope}_opening_deaths")
    attempts = opening_kills + opening_deaths
    result = {"available": bool(items), "opening_kills": opening_kills, "opening_deaths": opening_deaths, "opening_attempts": attempts}
    if scope == "overall":
        for key in ("trade_kills", "trade_opportunities", "deaths_traded", "deaths_not_traded", "clutch_opportunities", "clutch_wins"):
            result[key] = _sum_json(items, key)
        for size in range(1, 6):
            result[f"clutch_1v{size}_attempts"] = _sum_json(items, f"clutch_1v{size}_attempts")
            result[f"clutch_1v{size}_wins"] = _sum_json(items, f"clutch_1v{size}_wins")
    else:
        for key in ("trade_kills", "trade_opportunities", "deaths_traded", "deaths_not_traded", "clutch_opportunities", "clutch_wins"):
            result[key] = _sum_json(items, f"{scope}_{key}")
        for size in range(1, 6):
            result[f"clutch_1v{size}_attempts"] = _sum_json(items, f"{scope}_clutch_1v{size}_attempts")
            result[f"clutch_1v{size}_wins"] = _sum_json(items, f"{scope}_clutch_1v{size}_wins")
    return result


def _raw_profile(*, rounds: float, kills: float, deaths: float, damage: float, awp_kills: float,
                 combat: dict, utility: dict, scope: str, maps: int) -> dict:
    kpr = _ratio(kills, rounds); adr = _ratio(damage, rounds); survival = _ratio(max(0., rounds - deaths), rounds)
    attempts = combat.get("opening_attempts", 0.) or 0.; opening_kills = combat.get("opening_kills", 0.) or 0.
    combat_available = combat.get("available", bool(combat))
    opening_success = _ratio(opening_kills, attempts) if combat_available else None
    opening_attempt_rate = _ratio(attempts, rounds) if combat_available else None
    values: dict[str, dict] = {
        "firepower": {"metrics": {"kills_per_round": kpr, "adr": adr, "survival_rate": survival}, "weights": PROFILE_WEIGHTS["firepower"], "sample": int(rounds)},
        "opening": {"metrics": {"opening_success": opening_success, "opening_attempts_per_round": opening_attempt_rate}, "weights": PROFILE_WEIGHTS["opening"], "sample": int(attempts)},
        "sniping": {"metrics": {"awp_kills_per_round": _ratio(awp_kills, rounds), "awp_kill_share": _ratio(awp_kills, kills)}, "weights": PROFILE_WEIGHTS["sniping"], "sample": int(kills)},
        "utility": {"metrics": {k: utility.get(k) for k in ("flash_assists_per_round", "enemies_flashed_per_flash", "enemy_flash_seconds_per_flash", "utility_damage_per_round", "teammates_flashed_per_flash")}, "weights": PROFILE_WEIGHTS["utility"], "inverse": {"teammates_flashed_per_flash"}, "sample": int(utility.get("rounds") or 0)},
    }
    if scope == "t":
        values["entrying"] = {"metrics": {"t_opening_attempts_per_round": opening_attempt_rate, "t_opening_success": opening_success}, "weights": PROFILE_WEIGHTS["entrying"], "sample": int(attempts), "limitation": "V3 uses reliable T-side opening contacts; no synthetic post-contact entry event."}
    elif scope == "overall":
        values["entrying"] = {"metrics": {}, "weights": {}, "sample": 0, "unavailable_reason": "Entrying V3 is T-side only."}
    else:
        values["entrying"] = {"metrics": {}, "weights": {}, "sample": 0, "unavailable_reason": "Entrying is not applicable to CT side."}
    if scope in SCOPES:
        trade_opps = combat.get("trade_opportunities", 0.) or 0.; deaths = (combat.get("deaths_traded", 0.) or 0.) + (combat.get("deaths_not_traded", 0.) or 0.)
        values["trading"] = {"metrics": {"trade_success_rate": _ratio(combat.get("trade_kills", 0.) or 0., trade_opps) if combat_available else None, "death_trade_rate": _ratio(combat.get("deaths_traded", 0.) or 0., deaths) if combat_available else None}, "weights": PROFILE_WEIGHTS["trading"], "sample": int(trade_opps), "unavailable_reason": None if combat_available else "combat_data unavailable"}
        weighted_attempts = weighted_wins = 0.
        for size, weight in CLUTCH_DIFFICULTY_WEIGHTS.items():
            weighted_attempts += (combat.get(f"clutch_1v{size}_attempts", 0.) or 0.) * weight
            weighted_wins += (combat.get(f"clutch_1v{size}_wins", 0.) or 0.) * weight
        clutch_opportunities = combat.get("clutch_opportunities", 0.) or 0.
        values["clutching"] = {"metrics": {"difficulty_weighted_clutch_rate": _ratio(weighted_wins, clutch_opportunities) if combat_available else None}, "weights": PROFILE_WEIGHTS["clutching"], "sample": int(clutch_opportunities), "unavailable_reason": None if combat_available else "combat_data unavailable", "situations": {f"1v{x}": {"attempts": int(combat.get(f"clutch_1v{x}_attempts", 0.) or 0), "wins": int(combat.get(f"clutch_1v{x}_wins", 0.) or 0)} for x in range(1, 6)}}
    for value in values.values(): value["maps"] = maps
    return values


class PerformanceProfileService:
    def __init__(self, session: AsyncSession): self.session = session; self._cache: dict[tuple[date | None, date | None, str | None, int | None], dict] = {}

    async def _dataset(self, as_of: date | None, since: date | None = None, map_name: str | None = None,
                       exclude_match_id: int | None = None) -> dict:
        cache_key = (as_of, since, map_name, exclude_match_id)
        if cache_key in self._cache: return self._cache[cache_key]
        query = select(DemoPlayerStat, DemoFile.match_date).join(DemoParseRun, DemoParseRun.id == DemoPlayerStat.parse_run_id).join(DemoFile, DemoFile.id == DemoPlayerStat.demo_file_id).where(DemoParseRun.status == "success", DemoPlayerStat.player_id.is_not(None))
        query = query.where(DemoFile.match_date < (as_of or date.today()))
        if since is not None: query = query.where(DemoFile.match_date >= since)
        if exclude_match_id is not None:
            query = query.where((DemoFile.match_id.is_(None)) | (DemoFile.match_id != exclude_match_id))
        if map_name is not None:
            query = query.join(DemoMapResult, DemoMapResult.demo_file_id == DemoFile.id).where(DemoMapResult.map_name == map_name)
        rows = [row for row, _ in (await self.session.execute(query)).all()]
        demo_ids = {row.demo_file_id for row in rows}; player_ids = {row.player_id for row in rows}; team_ids = {row.demo_team_id for row in rows if row.demo_team_id}
        kill_q = select(DemoKill).where(DemoKill.demo_file_id.in_(demo_ids)) if demo_ids else select(DemoKill).where(False)
        damage_q = select(DemoDamageEvent).where(DemoDamageEvent.demo_file_id.in_(demo_ids)) if demo_ids else select(DemoDamageEvent).where(False)
        kills = list((await self.session.scalars(kill_q)).all()); damages = list((await self.session.scalars(damage_q)).all())
        round_q = select(DemoRound).where(DemoRound.demo_file_id.in_(demo_ids), DemoRound.is_complete.is_(True)) if demo_ids else select(DemoRound).where(False)
        rounds = list((await self.session.scalars(round_q)).all())
        by_player = defaultdict(list); by_team = defaultdict(list); map_team_by_player = {}
        for row in rows:
            by_player[row.player_id].append(row)
            if row.demo_team_id: by_team[row.demo_team_id].append(row); map_team_by_player[(row.demo_file_id, row.player_id)] = row.demo_team_id
        roster_links = list((await self.session.scalars(select(DemoTeamRoster).where(
            DemoTeamRoster.demo_file_id.in_(demo_ids), DemoTeamRoster.resolution_status == "complete",
            DemoTeamRoster.roster_id.is_not(None)))).all()) if demo_ids else []
        roster_by_demo_team = {(x.demo_file_id, x.team_id): x.roster_id for x in roster_links}
        by_team_roster = defaultdict(list)
        for row in rows:
            roster_id = roster_by_demo_team.get((row.demo_file_id, row.demo_team_id))
            if roster_id: by_team_roster[roster_id].append(row)
        # Re-run the existing deterministic combat derivation over persisted
        # kills. This adds the CT/T counters without parsing a demo again.
        kills_by_demo = defaultdict(list); rounds_by_demo = defaultdict(list); stats_by_demo = defaultdict(list)
        for kill in kills: kills_by_demo[kill.demo_file_id].append(kill)
        for round_row in rounds: rounds_by_demo[round_row.demo_file_id].append(round_row)
        for row in rows: stats_by_demo[row.demo_file_id].append(row)
        derived_combat: dict[tuple[int, int], dict] = {}
        for demo_id, stat_rows in stats_by_demo.items():
            rosters = defaultdict(set); identity_to_player = {}
            for row in stat_rows:
                if row.demo_team_name and row.identity_key: rosters[row.demo_team_name].add(row.identity_key)
                if row.player_id: identity_to_player[row.identity_key] = row.player_id
            combat_events = [CombatKill(
                next((r.round_number for r in rounds_by_demo[demo_id] if r.id == kill.round_id), 0),
                kill.tick, kill.attacker_identity_key, kill.victim_identity_key,
                kill.attacker_team_name, kill.victim_team_name, kill.attacker_side, kill.victim_side,
                kill.weapon, kill.is_headshot, kill.assister_identity_key, kill.is_teamkill, kill.is_suicide,
            ) for kill in kills_by_demo[demo_id]]
            winners = {r.round_number: r.winner_team_name for r in rounds_by_demo[demo_id] if r.winner_team_name}
            _, player_combat, _, _ = calculate_combat(combat_events, dict(rosters), winners)
            for identity, payload in player_combat.items():
                if identity in identity_to_player: derived_combat[(demo_id, identity_to_player[identity])] = payload
        event = defaultdict(lambda: defaultdict(float))
        for kill in kills:
            if kill.is_teamkill or kill.is_suicide: continue
            side = (kill.attacker_side or "").lower()
            for kind, entity in (("player", kill.attacker_player_id), ("team", kill.attacker_team_id)):
                if entity:
                    event[(kind, entity, side)]["kills"] += 1
                    if (kill.weapon or "").lower() in AWP_WEAPONS: event[(kind, entity, side)]["awp_kills"] += 1
            victim_side = (kill.victim_side or "").lower()
            for kind, entity in (("player", kill.victim_player_id), ("team", kill.victim_team_id)):
                if entity: event[(kind, entity, victim_side)]["deaths"] += 1
        for damage in damages:
            side = (damage.attacker_side or "").lower(); pid = damage.attacker_player_id
            if pid:
                event[("player", pid, side)]["damage"] += damage.health_damage
                tid = map_team_by_player.get((damage.demo_file_id, pid))
                if tid: event[("team", tid, side)]["damage"] += damage.health_damage

        def build(kind: str, entity: int, entity_rows: list[DemoPlayerStat], event_entity: int | None = None) -> dict:
            utility_items = [r.utility_data for r in entity_rows if r.utility_data]
            combat_items = [derived_combat.get((r.demo_file_id, r.player_id), r.combat_data) for r in entity_rows if derived_combat.get((r.demo_file_id, r.player_id), r.combat_data)]
            maps = len({r.demo_file_id for r in entity_rows})
            result = {}
            for scope in SCOPES:
                utility = _utility(utility_items, scope); combat = _combat(combat_items, scope)
                if kind == "team":
                    # Team execution is derived from team-event totals per team-round,
                    # not an average of five Player Performance Profile scores.
                    utility["rounds"] = (utility.get("rounds") or 0) / 5
                    for metric in ("flash_assists_per_round", "utility_damage_per_round"):
                        if utility.get(metric) is not None:
                            utility[metric] *= 5
                if scope == "overall":
                    rounds = sum(r.rounds_played for r in entity_rows) if kind == "player" else sum(max(x.rounds_played for x in entity_rows if x.demo_file_id == demo) for demo in {x.demo_file_id for x in entity_rows})
                    kills_count = sum(r.kills for r in entity_rows); deaths_count = sum(r.deaths for r in entity_rows); damage_count = sum(r.total_damage for r in entity_rows)
                    awp = sum(event[(kind, event_entity or entity, side)]["awp_kills"] for side in ("ct", "t"))
                else:
                    rounds = utility.get("rounds") or 0
                    ev = event[(kind, event_entity or entity, scope)]; kills_count = ev["kills"]; deaths_count = ev["deaths"]; damage_count = ev["damage"]; awp = ev["awp_kills"]
                    if kind == "team" and rounds: # team event rates are per team-round/player-slot where appropriate
                        fire_rounds = rounds * 5
                    else: fire_rounds = rounds
                    rounds = fire_rounds
                result[scope] = _raw_profile(rounds=rounds, kills=kills_count, deaths=deaths_count, damage=damage_count, awp_kills=awp, combat=combat, utility=utility, scope=scope, maps=maps)
            # Both Sides Entrying intentionally describes the T-side entry role.
            t_combat = _combat(combat_items, "t"); t_rounds = _utility(utility_items, "t").get("rounds") or 0
            if kind == "team": t_rounds = t_rounds / 5 if t_rounds else 0
            t_attempts = t_combat.get("opening_attempts", 0.) or 0.; t_kills = t_combat.get("opening_kills", 0.) or 0.
            result["overall"]["entrying"] = {"metrics": {"t_opening_attempts_per_round": _ratio(t_attempts, t_rounds), "t_opening_success": _ratio(t_kills, t_attempts)}, "weights": PROFILE_WEIGHTS["entrying"], "sample": int(t_attempts), "maps": maps, "limitation": "V3 uses reliable T-side opening contacts; no synthetic post-contact entry event."}
            return result

        player_raw = {pid: build("player", pid, value) for pid, value in by_player.items()}
        team_raw = {tid: build("team", tid, value) for tid, value in by_team.items()}
        team_roster_raw = {rid: build("team", rid, value, value[0].demo_team_id) for rid, value in by_team_roster.items()}
        dataset = {"player": player_raw, "team": team_raw, "team_roster": team_roster_raw}; self._cache[cache_key] = dataset; return dataset

    async def calculate(self, *, player_id: int | None = None, team_id: int | None = None,
                        roster_id: int | None = None, as_of: date | None = None,
                        since: date | None = None, map_name: str | None = None,
                        exclude_match_id: int | None = None) -> dict:
        kind, entity = (("player", player_id) if player_id is not None else
                        ("team_roster", roster_id) if roster_id is not None else ("team", team_id))
        dataset = await self._dataset(as_of, since, map_name, exclude_match_id); raw_all = dataset[kind]; raw = raw_all.get(entity, {scope: {} for scope in SCOPES})
        scopes = {}
        for scope in SCOPES:
            profiles = {}
            for profile in PROFILE_KEYS:
                value = raw.get(scope, {}).get(profile, {"metrics": {}, "weights": {}, "sample": 0})
                factors = []
                for metric, weight in value.get("weights", {}).items():
                    metric_value = value.get("metrics", {}).get(metric)
                    population = [p[scope][profile]["metrics"].get(metric) for p in raw_all.values() if p.get(scope, {}).get(profile)]
                    population = [float(x) for x in population if x is not None]
                    normalized = PerformanceNormalizationService.score(metric_value, population, inverse=metric in value.get("inverse", set()))
                    factors.append({"key": metric, "raw_value": None if metric_value is None else round(metric_value, 6), "normalized_score": normalized, "weight": weight, "available": normalized is not None})
                total = sum(x["weight"] for x in factors if x["available"])
                for factor in factors: factor["effective_weight"] = round(factor["weight"] / total, 4) if factor["available"] and total else 0.
                score = sum(x["normalized_score"] * x["effective_weight"] for x in factors if x["available"]) if total else None
                sample = int(value.get("sample", 0)); maps = int(value.get("maps", 0)); coverage = sum(x["available"] for x in factors) / len(factors) if factors else 0
                reliability = round(100 * sqrt(min(1., sample / PROFILE_SAMPLE_TARGETS[profile]) * min(1., maps / 20)) * coverage, 1) if maps else 0.
                profiles[profile] = {"score": None if score is None else round(score, 2), "reliability": reliability, "sample_size": sample, "breakdown": factors, "unavailable_reason": value.get("unavailable_reason"), "limitation": value.get("limitation"), "situations": value.get("situations"), "model_version": MODEL_VERSION}
            scopes[scope] = profiles
        return {"model_version": MODEL_VERSION, "normalization_version": PerformanceNormalizationService.VERSION, "as_of": as_of, "since": since, "map_name": map_name, "entity_type": "team" if kind == "team_roster" else kind, "entity_id": team_id or entity, "roster_id": roster_id, "overall": scopes["overall"], "ct": scopes["ct"], "t": scopes["t"], "scopes": scopes}

    async def player(self, player_id: int, as_of: date | None = None, exclude_match_id: int | None = None) -> dict: return await self.calculate(player_id=player_id, as_of=as_of, exclude_match_id=exclude_match_id)
    async def team(self, team_id: int, as_of: date | None = None) -> dict: return await self.calculate(team_id=team_id, as_of=as_of)
    async def team_roster(self, team_id: int, roster_id: int, as_of: date | None = None,
                          exclude_match_id: int | None = None) -> dict:
        return await self.calculate(team_id=team_id, roster_id=roster_id, as_of=as_of,
                                    exclude_match_id=exclude_match_id)
    async def player_window(self, player_id: int, since: date, as_of: date) -> dict: return await self.calculate(player_id=player_id, since=since, as_of=as_of)
    async def team_window(self, team_id: int, since: date, as_of: date, roster_id: int | None = None) -> dict: return await self.calculate(team_id=team_id, roster_id=roster_id, since=since, as_of=as_of)
    async def team_map(self, team_id: int, map_name: str, as_of: date | None = None,
                       roster_id: int | None = None, exclude_match_id: int | None = None) -> dict:
        return await self.calculate(team_id=team_id, roster_id=roster_id, as_of=as_of,
                                    map_name=map_name, exclude_match_id=exclude_match_id)
