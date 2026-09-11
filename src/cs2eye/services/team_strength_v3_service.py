from __future__ import annotations

from datetime import UTC, date, datetime
from math import sqrt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.analytics.team_strength_v3_config import (
    CALCULATION_REVISION, COMPONENT_WEIGHTS, EXECUTION_WEIGHTS, MODEL_VERSION, RELIABILITY_TARGETS,
    RELIABILITY_WEIGHTS, ROSTER_WEIGHTS,
)
from cs2eye.models.demo import DemoTeamRoster
from cs2eye.models.demo_file import DemoFile
from cs2eye.models.team import Player, Team, TeamRoster, TeamRosterMember, TeamStrengthV3Snapshot
from cs2eye.services.opponent_adjusted_results_service import OpponentAdjustedResultsService
from cs2eye.services.performance_profile_service import PerformanceProfileService
from cs2eye.services.player_strength_v3_service import PlayerStrengthV3Service
from cs2eye.services.effective_roster_service import EffectiveRosterService


def _json_safe(value):
    if isinstance(value, (date, datetime)): return value.isoformat()
    if isinstance(value, dict): return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list): return [_json_safe(item) for item in value]
    return value


def roster_quality(players: list[dict]) -> dict:
    scores = [float(x["player_strength_v3"]) for x in players if x.get("player_strength_v3") is not None]
    if not scores: return {"score": None, "reliability": 0., "avg_all": None, "avg_top_2": None, "avg_bottom_2": None, "players": players, "formula": ROSTER_WEIGHTS}
    ordered = sorted(scores, reverse=True)
    avg = sum(scores)/len(scores); top = sum(ordered[:2])/min(2, len(ordered)); bottom = sum(ordered[-2:])/min(2, len(ordered))
    score = avg*ROSTER_WEIGHTS["average"] + top*ROSTER_WEIGHTS["top_2"] + bottom*ROSTER_WEIGHTS["bottom_2"]
    rels = [float(x.get("reliability") or 0) for x in players if x.get("player_strength_v3") is not None]
    count_factor = min(len(scores), 5) / max(len(scores), 5)
    reliability = 100 * (sum(rels)/len(rels) if rels else 0) * count_factor
    return {"score": round(score, 2), "reliability": round(reliability, 1), "avg_all": round(avg, 2),
            "avg_top_2": round(top, 2), "avg_bottom_2": round(bottom, 2), "players": players,
            "formula": ROSTER_WEIGHTS}


def execution_quality(profile: dict) -> dict:
    values = profile["scopes"]["overall"]
    available = [(key, values[key]) for key in EXECUTION_WEIGHTS if values[key]["score"] is not None]
    weight = sum(EXECUTION_WEIGHTS[key] for key, _ in available)
    score = sum(value["score"] * EXECUTION_WEIGHTS[key]/weight for key, value in available) if weight else None
    reliability = sum(value["reliability"] * EXECUTION_WEIGHTS[key]/weight for key, value in available) if weight else 0.
    return {"score": None if score is None else round(score, 2), "reliability": round(reliability, 1),
            "coverage": round(weight, 2), "metrics": {key: {"score": values[key]["score"],
            "reliability": values[key]["reliability"], "sample_size": values[key]["sample_size"],
            "weight": EXECUTION_WEIGHTS[key]} for key in EXECUTION_WEIGHTS}, "formula": EXECUTION_WEIGHTS,
            "excluded": ["firepower", "sniping"]}


def compose_score(components: dict[str, dict]) -> tuple[float | None, float]:
    available = [(key, value) for key, value in components.items() if value.get("score") is not None]
    total_weight = sum(COMPONENT_WEIGHTS[key] for key, _ in available)
    score = (sum(value["score"] * COMPONENT_WEIGHTS[key] for key, value in available) /
             total_weight) if total_weight else None
    return score, total_weight


def reliability_score(*, roster: dict, execution: dict, results: dict, cutoff: date) -> tuple[float, dict]:
    sample = results["sample"]
    latest = sample.get("latest_current_roster_map_date")
    recency = max(0., 1. - max(0, (cutoff-latest).days-30)/150) if latest else 0.
    factors = {
        "player_strength": min(1., float(roster.get("reliability", 0))/100),
        "current_roster_maps": sqrt(min(1., sample["current_roster_maps"]/RELIABILITY_TARGETS["current_roster_maps"])),
        "current_roster_matches": sqrt(min(1., sample["current_roster_matches"]/RELIABILITY_TARGETS["current_roster_matches"])),
        "rounds": sqrt(min(1., sample["effective_rounds"]/RELIABILITY_TARGETS["rounds"])),
        "team_performance_profile": (execution.get("coverage", 0) * float(execution.get("reliability", 0))/100),
        "opponent_rankings": float(sample.get("ranking_coverage", 0))/100,
        "results_coverage": sqrt(min(1., sample["effective_maps"]/RELIABILITY_TARGETS["results_maps"])),
        "roster_data_relevance": recency,
    }
    reliability = 100 * sum(factors[key]*weight for key, weight in RELIABILITY_WEIGHTS.items())
    return reliability, {key: round(value, 3) for key, value in factors.items()}


class TeamStrengthV3Service:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.player_service = PlayerStrengthV3Service(session)
        self.performance_service = PerformanceProfileService(session)
        self.results_service = OpponentAdjustedResultsService(session)

    async def _roster(self, team: Team, as_of: date, historical: bool) -> TeamRoster | None:
        if not historical and team.current_roster_id:
            current = await self.session.get(TeamRoster, team.current_roster_id)
            return current if current and current.resolution_status == "complete" else None
        roster_id = await self.session.scalar(select(DemoTeamRoster.roster_id).join(
            DemoFile, DemoFile.id == DemoTeamRoster.demo_file_id).where(
                DemoTeamRoster.team_id == team.id, DemoTeamRoster.resolution_status == "complete",
                DemoTeamRoster.roster_id.is_not(None), DemoFile.match_date < as_of).order_by(
                    DemoFile.match_date.desc(), DemoFile.id.desc()).limit(1))
        if roster_id: return await self.session.get(TeamRoster, roster_id)
        return await self.session.scalar(select(TeamRoster).where(TeamRoster.team_id == team.id,
            (TeamRoster.active_from.is_(None) | (TeamRoster.active_from < as_of)),
            (TeamRoster.active_to.is_(None) | (TeamRoster.active_to >= as_of))).order_by(TeamRoster.active_from.desc()).limit(1))

    async def calculate(self, team_id: int, as_of: date | None = None, *, exclude_match_id: int | None = None,
                        force: bool = False, tournament_id: int | None = None,
                        match_id: int | None = None) -> dict:
        team = await self.session.get(Team, team_id)
        if team is None: raise ValueError("Team not found")
        today = date.today()
        if (as_of is None and exclude_match_id is None and tournament_id is None and match_id is None and not force
                and team.team_strength_v3_breakdown
                and team.team_strength_v3_breakdown.get("calculation_revision") == CALCULATION_REVISION):
            return team.team_strength_v3_breakdown
        historical = as_of is not None; cutoff = as_of or today; roster = await self._roster(team, cutoff, historical)
        members = list((await self.session.scalars(select(TeamRosterMember).where(
            TeamRosterMember.roster_id == roster.id, TeamRosterMember.player_id.is_not(None)))).all()) if roster else []
        permanent_ids = [int(member.player_id) for member in members if member.player_id is not None]
        effective = (await EffectiveRosterService(self.session).get_effective_roster(
            team_id, tournament_id, match_id, as_of or today)) if tournament_id is not None or match_id is not None else None
        effective_ids = [x["id"] for x in effective["effective_roster"]] if effective else permanent_ids
        player_values = []
        baseline_player_values = []
        for player_id in list(dict.fromkeys(permanent_ids + effective_ids)):
            player = await self.session.get(Player, player_id)
            if player is None: continue
            value = await self.player_service.calculate(player.id, cutoff,
                                                        exclude_match_id=exclude_match_id)
            item = {"id": player.id, "nickname": player.nickname,
                "player_strength_v3": value["player_strength"], "mechanical_strength": value["mechanical_strength"],
                "supporting_strength": value["supporting_strength"], "reliability": value["reliability"]}
            if player_id in effective_ids: player_values.append(item)
            if player_id in permanent_ids: baseline_player_values.append(item)
        roster_component = roster_quality(player_values)
        baseline_roster_component = roster_quality(baseline_player_values)
        performance = await self.performance_service.team_roster(
            team.id, roster.id, cutoff, exclude_match_id=exclude_match_id
        ) if roster else await self.performance_service.calculate(
            team_id=team.id, as_of=cutoff, exclude_match_id=exclude_match_id)
        execution = execution_quality(performance)
        results = await self.results_service.calculate(team.id, as_of=cutoff, roster_id=roster.id if roster else None, exclude_match_id=exclude_match_id)
        components = {"roster_quality": roster_component, "team_execution": execution, "results_quality": results}
        score, total_weight = compose_score(components)
        baseline_score, _ = compose_score({"roster_quality": baseline_roster_component,
                                           "team_execution": execution, "results_quality": results})
        penalty = float(effective["stand_in_penalty"]) if effective else 0.0
        if score is not None: score = max(0.0, min(100.0, score + penalty))
        reliability, reliability_factors = reliability_score(
            roster=roster_component, execution=execution, results=results, cutoff=cutoff)
        result = {"score": None if score is None else round(score, 2), "reliability": round(reliability, 1),
            "model_version": MODEL_VERSION, "calculation_revision": CALCULATION_REVISION,
            "baseline_team_strength_v3": None if baseline_score is None else round(baseline_score, 2),
            "effective_roster_quality": roster_component,
            "event_effective_strength": None if score is None else round(score, 2),
            "temporary_replacement_factor": {"type": "TEMPORARY_REPLACEMENT", "impact": penalty,
                "applied_once": True, "replacements": effective["replacements"] if effective else []},
            "effective_roster": effective,
            "as_of": cutoff, "roster": {"id": roster.id if roster else None,
            "active_from": roster.active_from if roster else None, "active_to": roster.active_to if roster else None,
            "players_count": len(player_values), "age_days": (cutoff-roster.active_from).days if roster and roster.active_from else None,
            **results["sample"]}, "components": {key: {**value, "weight": COMPONENT_WEIGHTS[key]} for key, value in components.items()},
            "reliability_breakdown": {"score": round(reliability, 1), "factors": reliability_factors,
                "weights": RELIABILITY_WEIGHTS, "score_component_coverage": round(total_weight, 3)},
            "formula": COMPONENT_WEIGHTS,
            "invariants": {"opponent_independent": True, "form_excluded": True, "firepower_not_double_counted": True,
            "sniping_not_required": True, "ranking_groups_diagnostic_only": True,
            "stand_in_penalty_applied_once": True, "stand_in_player_strength_unmodified": True}}
        result.update(roster_quality=roster_component, team_execution=execution,
                      results_quality=results, breakdown={
                          "components": result["components"],
                          "reliability": result["reliability_breakdown"],
                          "roster": result["roster"], "invariants": result["invariants"]})
        if force and not historical and exclude_match_id is None:
            team.team_strength_v3=result["score"]; team.team_strength_v3_reliability=result["reliability"]
            team.team_strength_v3_breakdown=_json_safe(result); team.team_strength_v3_model_version=MODEL_VERSION
            team.team_strength_v3_calculated_at=datetime.now(UTC)
        if force and exclude_match_id is None:
            snapshot = await self.session.scalar(select(TeamStrengthV3Snapshot).where(
                TeamStrengthV3Snapshot.team_id == team.id, TeamStrengthV3Snapshot.as_of == cutoff,
                TeamStrengthV3Snapshot.model_version == MODEL_VERSION))
            if snapshot is None:
                snapshot = TeamStrengthV3Snapshot(team_id=team.id, as_of=cutoff,
                    score=result["score"], reliability=result["reliability"], model_version=MODEL_VERSION,
                    breakdown=_json_safe(result))
                self.session.add(snapshot)
            else:
                snapshot.score=result["score"]; snapshot.reliability=result["reliability"]
                snapshot.breakdown=_json_safe(result); snapshot.calculated_at=datetime.now(UTC)
        return result
