"""Map-only observations; Team Strength is read solely for the diagnostic delta."""
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from math import isfinite, sqrt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.analytics.map_strength_v3_config import (
    MODEL_VERSION, CALCULATION_REVISION, COMPONENT_WEIGHTS, EXECUTION_WEIGHTS,
    SIDE_WEIGHTS, ECONOMY_WEIGHTS, ECONOMY_MIN_SAMPLE, ROSTER_WEIGHTS,
    UNKNOWN_ROSTER_WEIGHT, OLD_HISTORY_CAP, HISTORY_DAYS, LOW_SAMPLE_THRESHOLD, STATUS_THRESHOLDS, RANK_GROUPS,
)
from cs2eye.analytics.performance_v3_config import PROFILE_SAMPLE_TARGETS
from cs2eye.models.demo import (DemoMapResult, DemoTeamRoster, DemoRound, DemoKill,
                               DemoPlayerStat, DemoParseRun, DemoTeamSideStat, DemoDamageEvent)
from cs2eye.models.demo_file import DemoFile
from cs2eye.models.match import MapPoolEntry, Match
from cs2eye.models.team import Team, TeamRoster, TeamRosterMember, TeamRankingSnapshot, MapStrengthV3Snapshot
from cs2eye.services.effective_roster_service import EffectiveRosterService
from cs2eye.services.opponent_adjusted_results_service import adjusted_map_quality
from cs2eye.services.performance_profile_service import PerformanceProfileService, _raw_profile, _combat, _utility, rank_group_v3
from cs2eye.services.performance_normalization_service import PerformanceNormalizationService
from cs2eye.services.team_strength_v3_service import TeamStrengthV3Service, _json_safe


def clamp(value, low=0., high=100.):
    return max(low, min(high, value))


def compose(metrics, weights):
    """Only unavailable inputs change effective weights; confidence never does."""
    coverage = sum(w for k, w in weights.items() if metrics[k]["score"] is not None)
    total = sum(weights.values())
    effective = {k: w / coverage if metrics[k]["score"] is not None and coverage else 0. for k, w in weights.items()}
    score = sum(metrics[k]["score"] * effective[k] for k in weights if effective[k]) if coverage else None
    reliability = sum(metrics[k].get("reliability", 0.) * w for k, w in weights.items()) / total if total else 0.
    return {"score": None if score is None else round(score, 2), "reliability": round(reliability, 2),
            "coverage": round(coverage / total, 4) if total else 0.,
            "metrics": {k: {**metrics[k], "weight": w, "effective_weight": effective[k],
                             "available": metrics[k]["score"] is not None} for k, w in weights.items()}}


def rate_metric(wins, attempts, target=40., minimum=0.):
    available = attempts > 0 and attempts >= minimum
    return {"score": round(clamp(100 * wins / attempts), 2) if available else None,
            "reliability": round(100 * min(1., attempts / target), 2) if available else 0.,
            "sample_size": round(attempts, 3), "wins": round(wins, 3),
            "raw_rate": round(100 * wins / attempts, 4) if attempts else None,
            "unavailable_reason": None if available else "NOT_ENOUGH_DATA"}


def map_delta(score, team_score):
    return None if score is None or team_score is None else round(score - team_score, 2)


def map_status(score, delta):
    if score is None: return "NOT_ENOUGH_DATA"
    if delta is None: return "BASELINE_UNAVAILABLE"
    if delta >= STATUS_THRESHOLDS["VERY_STRONG"]: return "VERY_STRONG"
    if delta >= STATUS_THRESHOLDS["STRONG"]: return "STRONG"
    if delta <= STATUS_THRESHOLDS["VERY_WEAK"]: return "VERY_WEAK"
    if delta <= STATUS_THRESHOLDS["WEAK"]: return "WEAK"
    return "NEUTRAL"


def cap_old_history(events):
    """Keep distant/unknown lineups from overwhelming 3+/5 observations."""
    relevant = sum(e["weight"] for e in events if e["overlap"] is not None and e["overlap"] >= 3)
    old = sum(e["weight"] for e in events if e["overlap"] is None or e["overlap"] < 3)
    scale = min(1., OLD_HISTORY_CAP * relevant / old) if relevant and old else 1.
    return [{**e, "roster_applicability": e["weight"], "weight": e["weight"] * (
        scale if e["overlap"] is None or e["overlap"] < 3 else 1.)} for e in events]


def result_summary(events):
    selected = [e for e in events if e["weight"] > 0]
    weight = sum(e["weight"] for e in selected)
    score = sum(e["score"] * e["weight"] for e in selected) / weight if weight else None
    ranking = sum(e["weight"] for e in selected if e["opponent_rank"] is not None) / weight if weight else 0.
    return {"score": None if score is None else round(score, 2), "maps": len(selected),
            "wins": sum(e["won"] for e in selected), "losses": sum(not e["won"] for e in selected),
            "round_differential": sum(e["round_diff"] for e in selected),
            "rounds": sum(e["rounds"] for e in selected), "effective_maps": round(weight, 3),
            "ranking_coverage": ranking, "reliability": round(100 * min(1., weight / 12) * (.5 + .5 * ranking), 2)}


def weighted_json(value, weight):
    return {k: weighted_json(v, weight) if isinstance(v, dict) else float(v) * weight
            if isinstance(v, (int, float)) else v for k, v in value.items()}


def sanity_check(value):
    errors = []
    def walk(item, path=""):
        if isinstance(item, dict):
            for key, val in item.items():
                if isinstance(val, (float, int)) and not isinstance(val, bool):
                    if not isfinite(val): errors.append(f"{path}.{key}: non-finite")
                    if key in {"score", "reliability"} and not 0 <= val <= 100: errors.append(f"{path}.{key}: out of range")
                walk(val, f"{path}.{key}")
        elif isinstance(item, list):
            for child in item: walk(child, path)
    walk(value)
    if value["sample"]["selected_maps"] == 0 and value["score"] is not None: errors.append("empty sample has score")
    if value["sample"]["selected_maps"] <= 1 and value["reliability"] >= 100: errors.append("small sample has full reliability")
    for side in ("ct", "t"):
        if not value["sides"][side]["rounds"] and value["sides"][side]["score"] is not None: errors.append("side fallback")
    cutoff = date.fromisoformat(value["as_of"]) if isinstance(value["as_of"],str) else value["as_of"]
    for observation in value.get("observations",[]):
        day = observation["date"]
        day = date.fromisoformat(day) if isinstance(day,str) else day
        if day >= cutoff: errors.append("future observation")
        ranking_day = observation.get("ranking_date")
        ranking_day = date.fromisoformat(ranking_day) if isinstance(ranking_day,str) else ranking_day
        if ranking_day and ranking_day > day: errors.append("future ranking")
        if observation["overlap"] != 5 and observation.get("roster_applicability",observation["weight"]) >= 1:
            errors.append("old roster has full applicability")
    if not all(value.get("invariants",{}).values()): errors.append("dependency invariant failed")
    if errors: raise ValueError("Map V3 sanity: " + "; ".join(errors))
    return errors


class MapStrengthV3Service:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.profiles = PerformanceProfileService(session)
        self._context_cache = {}
        self._data_cache = {}
        self._baseline_cache = {}

    async def _context(self, team, cutoff, historical, tournament_id, match_id, exclude_match_id):
        key = (team.id, cutoff, historical, tournament_id, match_id, exclude_match_id)
        if key in self._context_cache: return self._context_cache[key]
        roster = None
        if not historical and team.current_roster_id:
            roster = await self.session.get(TeamRoster, team.current_roster_id)
        if roster is None:
            q = select(DemoTeamRoster.roster_id).join(DemoFile, DemoFile.id == DemoTeamRoster.demo_file_id).where(
                DemoTeamRoster.team_id == team.id, DemoTeamRoster.resolution_status == "complete",
                DemoTeamRoster.roster_id.is_not(None), DemoFile.match_date < cutoff)
            if exclude_match_id is not None: q = q.where((DemoFile.match_id != exclude_match_id) | DemoFile.match_id.is_(None))
            rid = await self.session.scalar(q.order_by(DemoFile.match_date.desc(), DemoFile.id.desc()).limit(1))
            if rid: roster = await self.session.get(TeamRoster, rid)
        if roster is None:
            roster = await self.session.scalar(select(TeamRoster).where(
                TeamRoster.team_id == team.id, TeamRoster.resolution_status == "complete",
                TeamRoster.active_from < cutoff,
                TeamRoster.active_to.is_(None) | (TeamRoster.active_to >= cutoff)
            ).order_by(TeamRoster.active_from.desc()).limit(1))
        permanent = list((await self.session.scalars(select(TeamRosterMember.player_id).where(
            TeamRosterMember.roster_id == roster.id, TeamRosterMember.player_id.is_not(None)))).all()) if roster else []
        effective = await EffectiveRosterService(self.session).get_effective_roster(
            team.id, tournament_id, match_id, cutoff, permanent_player_ids=permanent,
            known_before=cutoff if historical else None)
        result = {"roster_id": roster.id if roster else None, "permanent_player_ids": sorted(permanent),
                  "effective_player_ids": sorted(x["id"] for x in effective["players"]),
                  "tournament_id": effective["tournament_id"], "match_id": match_id,
                  "source": effective["roster_source"], "replacements": effective["replacements"],
                  "warnings": effective["warnings"]}
        self._context_cache[key] = result
        return result

    async def _load(self, team_id, cutoff, context, exclude_match_id, exclude_demo_id):
        key = (team_id, cutoff, tuple(context["effective_player_ids"]), exclude_match_id, exclude_demo_id)
        if key in self._data_cache: return self._data_cache[key]
        q = select(DemoFile, DemoMapResult, DemoTeamRoster, DemoTeamSideStat).join(
            DemoMapResult, DemoMapResult.demo_file_id == DemoFile.id).outerjoin(
            DemoTeamRoster, (DemoTeamRoster.demo_file_id == DemoFile.id) & (DemoTeamRoster.team_id == team_id)).outerjoin(
            DemoTeamSideStat, (DemoTeamSideStat.demo_file_id == DemoFile.id) & (DemoTeamSideStat.team_id == team_id)).where(
            DemoFile.match_date < cutoff, DemoFile.match_date >= cutoff - timedelta(days=HISTORY_DAYS),
            (DemoMapResult.team_a_id == team_id) | (DemoMapResult.team_b_id == team_id),
            DemoMapResult.team_a_score.is_not(None), DemoMapResult.team_b_score.is_not(None))
        if exclude_match_id is not None: q = q.where((DemoFile.match_id != exclude_match_id) | DemoFile.match_id.is_(None))
        if exclude_demo_id is not None: q = q.where(DemoFile.id != exclude_demo_id)
        rows = (await self.session.execute(q)).all()
        ids = [d.id for d, _, _, _ in rows]
        players = list((await self.session.scalars(select(DemoPlayerStat).join(
            DemoParseRun, DemoParseRun.id == DemoPlayerStat.parse_run_id).where(
            DemoPlayerStat.demo_file_id.in_(ids), DemoPlayerStat.demo_team_id == team_id,
            DemoParseRun.status == "success"))).all()) if ids else []
        by_demo = defaultdict(list)
        for p in players: by_demo[p.demo_file_id].append(p)
        roster_ids = {link.roster_id for _, _, link, _ in rows if link and link.roster_id}
        members = defaultdict(set)
        if roster_ids:
            for rid, pid in (await self.session.execute(select(TeamRosterMember.roster_id, TeamRosterMember.player_id).where(
                    TeamRosterMember.roster_id.in_(roster_ids), TeamRosterMember.player_id.is_not(None)))).all(): members[rid].add(pid)
        opponents = {r.team_b_id if r.team_a_id == team_id else r.team_a_id for _, r, _, _ in rows}
        rankings = defaultdict(list)
        if opponents:
            for r in (await self.session.scalars(select(TeamRankingSnapshot).where(
                    TeamRankingSnapshot.team_id.in_({x for x in opponents if x}), TeamRankingSnapshot.ranking_date < cutoff
            ).order_by(TeamRankingSnapshot.ranking_date))).all(): rankings[r.team_id].append(r)
        events = []
        current = set(context["effective_player_ids"])
        for demo, result, link, side in rows:
            actual = {p.player_id for p in by_demo[demo.id] if p.player_id}
            if len(actual) != 5 and link and link.resolution_status == "complete": actual = members[link.roster_id]
            overlap = len(current & actual) if len(current) == 5 and len(actual) == 5 else None
            weight = ROSTER_WEIGHTS[overlap] if overlap is not None else UNKNOWN_ROSTER_WEIGHT
            own_a = result.team_a_id == team_id
            own = result.team_a_score if own_a else result.team_b_score
            other = result.team_b_score if own_a else result.team_a_score
            opp = result.team_b_id if own_a else result.team_a_id
            eligible = [r for r in rankings[opp] if r.ranking_date <= demo.match_date]
            rank = eligible[-1].rank if eligible else None
            events.append({"demo_id": demo.id, "match_id": demo.match_id, "date": demo.match_date,
                           "map": result.map_name, "won": own > other, "round_diff": own-other, "rounds": own+other,
                           "opponent_id": opp, "opponent_rank": rank,
                           "ranking_date": eligible[-1].ranking_date if eligible else None,
                           "group": rank_group_v3(rank), "overlap": overlap, "weight": weight,
                           "historical_player_ids": sorted(actual), "own_a": own_a,
                           "bomb_available": result.bomb_data_status == "complete",
                           "combat_available": result.combat_data_status == "complete",
                           "side_stat": side, "players": by_demo[demo.id],
                           **adjusted_map_quality(won=own>other, round_diff=own-other, opponent_rank=rank)})
        rounds = list((await self.session.scalars(select(DemoRound).where(
            DemoRound.demo_file_id.in_(ids), DemoRound.is_complete.is_(True),
            DemoRound.is_warmup.is_(False), DemoRound.is_restart.is_(False)
        ).order_by(DemoRound.demo_file_id, DemoRound.round_number))).all()) if ids else []
        kills = list((await self.session.scalars(select(DemoKill).where(DemoKill.demo_file_id.in_(ids)).order_by(
            DemoKill.demo_file_id, DemoKill.tick, DemoKill.id))).all()) if ids else []
        damages = list((await self.session.scalars(select(DemoDamageEvent).where(
            DemoDamageEvent.demo_file_id.in_(ids), DemoDamageEvent.attacker_player_id.in_({p.player_id for p in players if p.player_id})
        ))).all()) if ids else []
        value = (events, rounds, kills, damages)
        self._data_cache[key] = value
        return value

    def _round_metrics(self, team_id, events, rounds, kills):
        index = {e["demo_id"]: e for e in events if e["weight"] > 0}
        first = {}
        for k in kills:
            if k.demo_file_id in index and not k.is_teamkill and not k.is_suicide and k.attacker_team_id and k.victim_team_id and k.attacker_team_id != k.victim_team_id:
                first.setdefault(k.round_id, k)
        totals = {s: defaultdict(lambda: [0., 0.]) for s in ("ct", "t")}
        previous = {}
        for r in rounds:
            e = index.get(r.demo_file_id)
            if not e: continue
            side = (r.team_a_side if e["own_a"] else r.team_b_side).lower()
            if side not in totals or r.winner_team_id is None: continue
            w = e["weight"]; won = r.winner_team_id == team_id
            def add(key, success):
                totals[side][key][0] += w * bool(success)
                totals[side][key][1] += w
            add("round_winrate", won)
            if r.is_pistol_round: add("pistol_winrate", won)
            if (r.team_a_economy if e["own_a"] else r.team_b_economy) == "eco" and not r.is_pistol_round: add("eco", won)
            opening = first.get(r.id) if e["combat_available"] else None
            if opening and team_id in {opening.attacker_team_id, opening.victim_team_id}:
                advantage = opening.attacker_team_id == team_id
                add("opening", advantage)
                add("conversion" if advantage else "recovery", won)
            own_eco = r.team_a_economy if e["own_a"] else r.team_b_economy
            opp_eco = r.team_b_economy if e["own_a"] else r.team_a_economy
            if not r.is_pistol_round and own_eco in {"full_buy", "force_buy"}: add(own_eco, won)
            if not r.is_pistol_round and own_eco == "full_buy" and opp_eco == "eco": add("anti_eco", won)
            prev = previous.get(r.demo_file_id)
            if prev and prev.is_pistol_round and prev.winner_team_id == team_id and r.round_number == prev.round_number + 1: add("pistol_conversion", won)
            if prev and prev.is_pistol_round and prev.winner_team_id != team_id and r.round_number == prev.round_number + 1: add("second_round_recovery", won)
            previous[r.demo_file_id] = r
            if e["bomb_available"]:
                if side == "t": add("plant_rate", r.bomb_planted)
                if r.bomb_planted: add("postplant" if side == "t" else "retake", won)
        # Genuine side aggregates may be present even when raw rounds are absent.
        for side in ("ct", "t"):
            represented = {r.demo_file_id for r in rounds if r.demo_file_id in index}
            for e in index.values():
                stat = e["side_stat"]
                if stat and e["demo_id"] not in represented:
                    totals[side]["round_winrate"][0] += getattr(stat, f"{side}_rounds_won") * e["weight"]
                    totals[side]["round_winrate"][1] += getattr(stat, f"{side}_rounds_played") * e["weight"]
        return totals

    async def _profile(self, team_id, map_name, cutoff, events, totals, exclude_match_id, kills, damages):
        # Normalize weighted map observations against map-specific historical teams.
        population = (await self.profiles._dataset(cutoff, cutoff-timedelta(days=HISTORY_DAYS), map_name, exclude_match_id))["team"] if events else {}
        players = [(p, e["weight"]) for e in events if e["weight"] > 0 for p in e["players"]]
        utility_items = [weighted_json(p.utility_data, w) for p, w in players if p.utility_data]
        combat_items = [weighted_json(p.combat_data, w) for p, w in players if p.combat_data]
        effective_maps = sum(e["weight"] for e in events if e["weight"] > 0)
        scopes = {}
        weights = {e["demo_id"]: e["weight"] for e in events}
        side_events = {s: defaultdict(float) for s in ("ct", "t")}
        for k in kills:
            w = weights.get(k.demo_file_id, 0.)
            if not w or k.is_teamkill or k.is_suicide: continue
            side = (k.attacker_side or "").lower()
            if k.attacker_team_id == team_id and side in side_events:
                side_events[side]["kills"] += w
                if (k.weapon or "").lower() in {"awp", "weapon_awp"}: side_events[side]["awp"] += w
            side = (k.victim_side or "").lower()
            if k.victim_team_id == team_id and side in side_events: side_events[side]["deaths"] += w
        player_keys = {(p.demo_file_id,p.player_id) for p,w in players}
        for d in damages:
            if (d.demo_file_id,d.attacker_player_id) not in player_keys: continue
            side = (d.attacker_side or "").lower()
            if side in side_events: side_events[side]["damage"] += weights.get(d.demo_file_id, 0.)*d.health_damage
        for scope in ("overall", "ct", "t"):
            utility = _utility(utility_items, scope)
            utility["rounds"] = (utility.get("rounds") or 0) / 5
            for key in ("flash_assists_per_round", "utility_damage_per_round"):
                if utility.get(key) is not None: utility[key] *= 5
            combat = _combat(combat_items, scope)
            rounds = sum(totals[s]["round_winrate"][1] for s in ("ct", "t")) if scope == "overall" else totals[scope]["round_winrate"][1]
            ev = side_events.get(scope, {})
            raw = _raw_profile(rounds=rounds if scope == "overall" else rounds*5,
                kills=sum(p.kills*w for p,w in players) if scope == "overall" else ev.get("kills",0),
                deaths=sum(p.deaths*w for p,w in players) if scope == "overall" else ev.get("deaths",0),
                damage=sum(p.total_damage*w for p,w in players) if scope == "overall" else ev.get("damage",0),
                awp_kills=sum(v["awp"] for v in side_events.values()) if scope == "overall" else ev.get("awp",0),
                combat=combat, utility=utility, scope=scope, maps=len(events))
            if not any(k.demo_file_id in weights for k in kills):
                raw["sniping"] = {"metrics": {}, "weights": {}, "sample": 0}
                if scope != "overall": raw["firepower"] = {"metrics": {}, "weights": {}, "sample": 0}
            if scope != "overall" and not any(d.demo_file_id in weights for d in damages):
                raw["firepower"]["metrics"]["adr"] = None
            if scope == "overall":
                tcombat = _combat(combat_items, "t")
                attempts = tcombat.get("opening_attempts", 0)
                trounds = totals["t"]["round_winrate"][1]
                from cs2eye.analytics.performance_v3_config import PROFILE_WEIGHTS
                raw["entrying"] = {"metrics": {
                    "t_opening_attempts_per_round": attempts/trounds if trounds else None,
                    "t_opening_success": tcombat.get("opening_kills",0)/attempts if attempts else None},
                    "weights": PROFILE_WEIGHTS["entrying"], "sample": attempts}
            # Team openings are per team-round, not per player-slot round.
            if rounds:
                raw["opening"]["metrics"]["opening_attempts_per_round"] = combat.get("opening_attempts",0)/rounds if combat_items else None
                if scope == "t": raw["entrying"]["metrics"]["t_opening_attempts_per_round"] = combat.get("opening_attempts",0)/rounds if combat_items else None
            for name in ("opening", "entrying"):
                if not raw[name].get("sample", 0):
                    raw[name]["metrics"] = {k: None for k in raw[name].get("metrics", {})}
            values = {}
            for name, metric in raw.items():
                factors = []
                for key, weight in metric.get("weights", {}).items():
                    raw_value = metric.get("metrics", {}).get(key)
                    peers = [p[scope][name]["metrics"].get(key) for p in population.values() if p.get(scope, {}).get(name)]
                    if scope in {"ct", "t"} and key in {"opening_attempts_per_round", "t_opening_attempts_per_round"}:
                        peers = [x*5 if x is not None else None for x in peers]
                    peers = [x for x in peers if x is not None]
                    normalized = PerformanceNormalizationService.score(raw_value, peers, inverse=key in metric.get("inverse", set())) if len(peers) >= 2 else None
                    factors.append({"key": key, "raw_value": raw_value, "normalized_score": normalized, "weight": weight,
                                    "available": normalized is not None})
                total = sum(f["weight"] for f in factors if f["available"])
                for f in factors: f["effective_weight"] = f["weight"]/total if f["available"] and total else 0.
                score = sum(f["normalized_score"]*f["effective_weight"] for f in factors if f["available"]) if total else None
                sample = metric.get("sample",0)
                reliability = 100*sqrt(min(1.,sample/PROFILE_SAMPLE_TARGETS[name])*min(1.,effective_maps/20))*total
                values[name] = {"score": round(score,2) if score is not None else None, "reliability": round(reliability,2),
                                "sample_size": round(sample,3), "breakdown": factors,
                                "unavailable_reason": None if score is not None else "NOT_ENOUGH_DATA", "model_version": "performance_profile.v3"}
            scopes[scope] = values
        return {"model_version": "performance_profile.v3", "normalization_version": PerformanceNormalizationService.VERSION,
                "map_name": map_name, "scopes": scopes, "overall": scopes["overall"], "ct": scopes["ct"], "t": scopes["t"]}

    async def calculate(self, team_id: int, map_name: str, as_of: date | None = None, *,
                        exclude_match_id=None, exclude_demo_id=None, tournament_id=None, match_id=None, force=False):
        team = await self.session.get(Team, team_id)
        if team is None: raise ValueError("Team not found")
        cutoff = as_of or date.today()
        if match_id is not None:
            match = await self.session.get(Match, match_id)
            if match is None: raise ValueError("Match not found")
            cutoff = as_of or match.match_date
            exclude_match_id = exclude_match_id or match_id
        if exclude_demo_id is not None:
            demo = await self.session.get(DemoFile, exclude_demo_id)
            if demo: exclude_match_id = exclude_match_id or demo.match_id
        context = await self._context(team, cutoff, as_of is not None or match_id is not None, tournament_id, match_id, exclude_match_id)
        all_events, rounds, kills, damages = await self._load(team_id, cutoff, context, exclude_match_id, exclude_demo_id)
        events = cap_old_history([e for e in all_events if e["map"] == map_name])
        selected = [e for e in events if e["weight"] > 0]
        totals = self._round_metrics(team_id, events, rounds, kills)
        profile = await self._profile(team_id, map_name, cutoff, selected, totals, exclude_match_id, kills, damages)
        sides = {}
        for side in ("ct", "t"):
            t = totals[side]
            economy = compose({k: rate_metric(*t[k], target=40, minimum=ECONOMY_MIN_SAMPLE[k]) for k in ECONOMY_WEIGHTS}, ECONOMY_WEIGHTS)
            economy["diagnostics"] = {k: rate_metric(*t[k]) for k in ("pistol_winrate", "eco", "second_round_recovery")}
            conv = compose({k: rate_metric(*t[k]) for k in ("conversion", "recovery")}, {"conversion": .5, "recovery": .5})
            metrics = {"round_winrate": rate_metric(*t["round_winrate"], target=150), "opening": rate_metric(*t["opening"]),
                       "economy": economy, "conversion_recovery": conv,
                       "postplant": {**rate_metric(*t["postplant"]), "plant_opportunities": t["plant_rate"][1], "plants": t["plant_rate"][0]}, "retake": rate_metric(*t["retake"])}
            sides[side] = {**compose(metrics, SIDE_WEIGHTS[side]), "rounds": round(t["round_winrate"][1],3)}
        side_performance = compose(sides, {"ct": .5, "t": .5})
        overall_economy = compose({k: rate_metric(*(sum(totals[s][k][i] for s in ("ct", "t")) for i in (0,1)),
            minimum=ECONOMY_MIN_SAMPLE[k]) for k in ECONOMY_WEIGHTS}, ECONOMY_WEIGHTS)
        execution_metrics = {k: profile["overall"][k] for k in ("trading", "utility", "opening", "entrying")}
        postplant = {**rate_metric(*totals["t"]["postplant"]), "plant_opportunities": totals["t"]["plant_rate"][1],
                     "plants": totals["t"]["plant_rate"][0], "plant_rate": rate_metric(*totals["t"]["plant_rate"])["score"]}
        execution_metrics.update(economy=overall_economy, postplant=postplant, retake=rate_metric(*totals["ct"]["retake"]))
        execution = compose(execution_metrics, EXECUTION_WEIGHTS)
        results = result_summary(events)
        components = {"results_quality": results, "side_performance": side_performance, "map_execution": execution}
        combined = compose(components, COMPONENT_WEIGHTS)
        score = combined["score"] if selected else None
        # Baseline is computed after the independent score and cannot feed its inputs.
        baseline_key = (team_id, cutoff, exclude_match_id, as_of is not None or match_id is not None)
        if baseline_key not in self._baseline_cache:
            # The existing service validates its calculation revision. A raw Team JSON
            # cache can be stale, so it must not be used directly as the baseline.
            # Isolate any on-demand Team V3 writes: Maps recalculate commits only Maps.
            async with AsyncSession(bind=self.session.bind, expire_on_commit=False) as baseline_session:
                baseline = await TeamStrengthV3Service(baseline_session).calculate(
                    team_id, cutoff if as_of is not None or match_id is not None else None,
                    exclude_match_id=exclude_match_id)
            self._baseline_cache[baseline_key] = baseline.get("score")
        team_score = self._baseline_cache[baseline_key]
        delta = map_delta(score, team_score)
        weight = sum(e["weight"] for e in selected)
        exact = sum(e["overlap"] == 5 for e in events)
        effective_rounds = sum(e["rounds"]*e["weight"] for e in selected)
        factors = {"maps": min(1., weight/12), "rounds": min(1., effective_rounds/300),
                   "exact_roster_coverage": exact/len(events) if events else 0.,
                   "ranking_coverage": results["ranking_coverage"],
                   "ct_sample": min(1., sides["ct"]["rounds"]/150), "t_sample": min(1., sides["t"]["rounds"]/150),
                   "execution_coverage": execution["coverage"], "economy_sample": overall_economy["reliability"]/100,
                   "postplant_sample": execution_metrics["postplant"]["reliability"]/100,
                   "retake_sample": execution_metrics["retake"]["reliability"]/100}
        reliability = 100*sqrt(factors["maps"]*factors["rounds"])*(.25+.75*factors["exact_roster_coverage"])*(.5+.5*factors["ranking_coverage"])*(
            .5+.25*factors["ct_sample"]+.25*factors["t_sample"])*(.4+.6*factors["execution_coverage"])*(
            .55+.15*factors["economy_sample"]+.15*factors["postplant_sample"]+.15*factors["retake_sample"])
        pool_entries = list((await self.session.scalars(select(MapPoolEntry).where(MapPoolEntry.map_name == map_name))).all())
        active = any((p.active_from is None or p.active_from <= cutoff) and (p.active_to is None or p.active_to >= cutoff)
                     and (p.is_active if p.active_from is None and p.active_to is None else (as_of is not None or p.is_active)) for p in pool_entries)
        value = {"map": map_name, "map_id": pool_entries[0].id if pool_entries else None, "is_active_pool": active,
                 "score": score, "map_score": score,
                 "reliability": round(reliability,2) if score is not None else 0., "team_strength_v3": team_score,
                 "delta_vs_team": delta, "map_delta_vs_team_strength": delta, "delta": delta, "map_delta": delta,
                 "status": map_status(score,delta), "flags": ["LOW_SAMPLE"] if reliability < LOW_SAMPLE_THRESHOLD else [],
                 "model_version": MODEL_VERSION, "calculation_revision": CALCULATION_REVISION, "as_of": cutoff,
                 "roster_context": context, "components": combined["metrics"], "sides": sides,
                 "performance_profile": profile, "results_breakdown": {"overall": results, "groups": {g: result_summary([e for e in events if e["group"]==g]) for g in RANK_GROUPS}},
                 "sample": {"maps": len(events), "selected_maps": len(selected), "rounds": sum(e["rounds"] for e in selected),
                     "effective_maps": round(weight,3), "effective_rounds": round(effective_rounds,3),
                     "exact_roster_maps": exact, "four_of_five_maps": sum(e["overlap"]==4 for e in events),
                     "three_of_five_maps": sum(e["overlap"]==3 for e in events),
                     "older_roster_maps": sum(e["overlap"] is not None and e["overlap"]<3 for e in events),
                     "unknown_roster_maps": sum(e["overlap"] is None for e in events)},
                 "reliability_breakdown": factors,
                 "limitations": {"economy_reset_recovery": "UNAVAILABLE: no validated reset events",
                     "entrying": "Real T-side opening contacts only", "normalization": "Map-specific historical team percentiles; fewer than two peers is unavailable"},
                 "observations": [{k:v for k,v in e.items() if k not in {"players", "side_stat"}} for e in events],
                 "invariants": {"independent_map_baseline": True, "team_strength_delta_only": True,
                     "form_excluded": True, "veto_excluded": True, "h2h_excluded": True,
                     "future_opponent_excluded": True, "no_shrink_to_50": True, "stand_in_penalty_excluded": True}}
        sanity_check(value)
        # On-demand requests never reuse stale legacy-v3 snapshots. Explicit recalculate persists.
        if force and as_of is None and tournament_id is None and match_id is None and exclude_match_id is None and exclude_demo_id is None:
            snap = await self.session.scalar(select(MapStrengthV3Snapshot).where(MapStrengthV3Snapshot.team_id==team_id,
                MapStrengthV3Snapshot.map_name==map_name, MapStrengthV3Snapshot.as_of==cutoff, MapStrengthV3Snapshot.model_version==MODEL_VERSION))
            if snap is None:
                snap = MapStrengthV3Snapshot(team_id=team_id,map_name=map_name,as_of=cutoff,model_version=MODEL_VERSION)
                self.session.add(snap)
            snap.map_score=score; snap.map_delta=delta; snap.reliability=value["reliability"]
            snap.ct_score=sides["ct"]["score"]; snap.t_score=sides["t"]["score"]
            snap.ct_delta=None; snap.t_delta=None; snap.breakdown=_json_safe(value); snap.calculated_at=datetime.now(UTC)
        return value

    async def pool(self, team_id: int, as_of: date | None = None, **kwargs):
        team = await self.session.get(Team,team_id)
        if team is None: raise ValueError("Team not found")
        cutoff=as_of or date.today()
        if kwargs.get("match_id") is not None and as_of is None:
            match = await self.session.get(Match, kwargs["match_id"])
            if match is None: raise ValueError("Match not found")
            cutoff = match.match_date
        names=set((await self.session.scalars(select(MapPoolEntry.map_name).where(
            MapPoolEntry.active_from.is_(None) | (MapPoolEntry.active_from <= cutoff)))).all())
        names.update((await self.session.scalars(select(DemoMapResult.map_name).join(DemoFile,DemoFile.id==DemoMapResult.demo_file_id).where(
            DemoFile.match_date<cutoff,(DemoMapResult.team_a_id==team_id)|(DemoMapResult.team_b_id==team_id)))) .all())
        maps=[await self.calculate(team_id,n,as_of,**kwargs) for n in sorted(n for n in names if n)]
        return {"team_id":team_id,"as_of":maps[0]["as_of"] if maps else cutoff,"model_version":MODEL_VERSION,"maps":maps}
