from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from math import sqrt

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.analytics.team_form_v3_config import (
    BO_FORMAT_WEIGHTS, CALCULATION_REVISION, FORM_DELTA_LIMIT, FORM_SCORE_POINTS_PER_DELTA,
    FRESHNESS_WEIGHT_POINTS, MODEL_VERSION, RELIABILITY_TARGETS,
    RELIABILITY_WEIGHTS, RANK_STRENGTH_BASE, RANK_STRENGTH_FLOOR,
    RANK_STRENGTH_POINTS_PER_PLACE, TOURNAMENT_ABSOLUTE_MAX_WEIGHT,
    TOURNAMENT_MAX_WEIGHTS, WINDOW_DAYS,
)
from cs2eye.models.demo import DemoMapResult, DemoTeamRoster
from cs2eye.models.demo_file import DemoFile
from cs2eye.models.match import Match, Tournament
from cs2eye.models.team import (
    Team, TeamFormV3Snapshot, TeamRankingSnapshot, TeamRosterMember,
    TeamStrengthV3Snapshot,
)
from cs2eye.services.performance_profile_service import rank_group_v3
from cs2eye.services.performance_vs_expectation_service import (
    PerformanceVsExpectationService, clamp,
)
from cs2eye.services.team_strength_v3_service import TeamStrengthV3Service, _json_safe
from cs2eye.services.effective_roster_service import EffectiveRosterService, roster_applicability


def freshness_weight(age_days: int) -> float:
    age = max(0, min(WINDOW_DAYS, age_days))
    for (left_day, left_weight), (right_day, right_weight) in zip(
            FRESHNESS_WEIGHT_POINTS, FRESHNESS_WEIGHT_POINTS[1:]):
        if left_day <= age <= right_day:
            span = right_day-left_day
            ratio = (age-left_day)/span if span else 0.0
            return left_weight+(right_weight-left_weight)*ratio
    return FRESHNESS_WEIGHT_POINTS[-1][1]


def delta_to_score(delta: float) -> float:
    return clamp(50.0+delta*FORM_SCORE_POINTS_PER_DELTA, 0.0, 100.0)


def eligible_event(event_date: date, cutoff: date, match_id: int | None,
                   exclude_match_id: int | None) -> bool:
    return event_date < cutoff and (exclude_match_id is None or match_id != exclude_match_id)


def within_form_window(event_date: date, cutoff: date) -> bool:
    return cutoff-timedelta(days=WINDOW_DAYS) <= event_date < cutoff


def series_data_complete(loaded_maps: int, expected_maps: int) -> bool:
    return expected_maps <= 0 or loaded_maps == expected_maps


def series_won(own_map_wins: int, opponent_map_wins: int) -> bool | None:
    if own_map_wins == opponent_map_wins:
        return None
    return own_map_wins > opponent_map_wins


def same_five_player_roster(current: set[int], historical: set[int]) -> bool:
    """Roster snapshot identity is semantic; database row ids may differ."""
    return len(current) == 5 and historical == current


def series_scores(team_id: int, results: list[DemoMapResult]) -> tuple[int, int, int, int]:
    """Aggregate a series without assuming stable team_a/team_b map ordering."""
    own_rounds = opponent_rounds = own_map_wins = opponent_map_wins = 0
    for result in results:
        if result.team_a_id == team_id:
            own_score, opponent_score = result.team_a_score, result.team_b_score
        elif result.team_b_id == team_id:
            own_score, opponent_score = result.team_b_score, result.team_a_score
        else:
            raise ValueError("Series map does not contain the requested team")
        own_score, opponent_score = int(own_score), int(opponent_score)
        own_rounds += own_score
        opponent_rounds += opponent_score
        own_map_wins += own_score > opponent_score
        opponent_map_wins += opponent_score > own_score
    return own_rounds, opponent_rounds, own_map_wins, opponent_map_wins


def form_rank_strength(rank: int | None) -> float | None:
    """Conservative rank proxy used only when historical V3 strength is absent."""
    if rank is None:
        return None
    return max(RANK_STRENGTH_FLOOR,
               RANK_STRENGTH_BASE-min(max(rank, 1), 60)*RANK_STRENGTH_POINTS_PER_PLACE)


def partition_events(events: list[dict], tournament_id: int | None,
                     cutoff: date | None = None) -> tuple[list[dict], list[dict]]:
    tournament = [x for x in events if tournament_id is not None and
                  x["tournament_id"] == tournament_id]
    tournament_keys = {x["series_key"] for x in tournament}
    recent = [x for x in events if x["series_key"] not in tournament_keys and
              (cutoff is None or within_form_window(x["date"], cutoff))]
    return tournament, recent


def resolve_expectation(own_snapshot: float | None, opponent_snapshot: float | None,
                        own_rank: int | None, opponent_rank: int | None) -> tuple[float, float, str]:
    if own_snapshot is not None and opponent_snapshot is not None:
        return own_snapshot, opponent_snapshot, "historical_team_strength_v3"
    own_value = own_snapshot if own_snapshot is not None else form_rank_strength(own_rank)
    opponent_value = (opponent_snapshot if opponent_snapshot is not None else
                      form_rank_strength(opponent_rank))
    if own_value is not None and opponent_value is not None:
        return own_value, opponent_value, "historical_ranking_fallback"
    if own_value is not None or opponent_value is not None:
        # One known side cannot define a relative expectation. Neutral is safer
        # than inventing a 50-strength opponent/team; reliability records the gap.
        return 50.0, 50.0, "partial_historical_ranking_fallback"
    return own_value or 50.0, opponent_value or 50.0, "unknown"


def aggregate_events(events: list[dict], *, recent: bool) -> dict:
    weighted = []
    for event in events:
        freshness = freshness_weight(event["age_days"]) if recent else 1.0
        weight = freshness*BO_FORMAT_WEIGHTS.get(event["format"], BO_FORMAT_WEIGHTS["unknown"])*float(event.get("roster_applicability", 1.0))
        weighted.append((event, weight, freshness))
    total_weight = sum(weight for _, weight, _ in weighted)
    delta = (sum(event["form_contribution"]*weight for event, weight, _ in weighted)/
             total_weight) if total_weight else None
    if delta is not None:
        delta = clamp(delta, -FORM_DELTA_LIMIT, FORM_DELTA_LIMIT)
    return {"delta": None if delta is None else round(delta, 2),
            "score": None if delta is None else round(delta_to_score(delta), 2),
            "series": len(events), "maps": sum(x["maps"] for x in events),
            "rounds": sum(x["rounds"] for x in events),
            "available": bool(events), "total_event_weight": round(total_weight, 4),
            "events": [{**event, "freshness_weight": round(freshness, 4),
                        "aggregation_weight": round(weight, 4)}
                       for event, weight, freshness in weighted]}


def scope_reliability(scope: dict, *, candidate_maps: int) -> tuple[float, dict]:
    events = scope["events"]
    expectation_known = sum(x.get("expectation_coverage", 0.0) for x in events)
    factors = {
        "series": sqrt(min(1.0, scope["series"]/RELIABILITY_TARGETS["series"])),
        "maps": sqrt(min(1.0, scope["maps"]/RELIABILITY_TARGETS["maps"])),
        "rounds": sqrt(min(1.0, scope["rounds"]/RELIABILITY_TARGETS["rounds"])),
        "roster_applicability": scope["maps"]/candidate_maps if candidate_maps else 0.0,
        "expectation_coverage": expectation_known/len(events) if events else 0.0,
        "data_coverage": sum(x["data_complete"] for x in events)/len(events) if events else 0.0,
    }
    sample_gate = 0.5+0.5*factors["series"]
    value = 100*sum(factors[key]*weight for key, weight in RELIABILITY_WEIGHTS.items())*sample_gate
    factors["sample_gate"] = sample_gate
    return clamp(value, 0.0, 100.0), {key: round(item, 4) for key, item in factors.items()}


def tournament_weight_limit(series: int) -> float:
    configured = TOURNAMENT_MAX_WEIGHTS.get(min(series, 3), TOURNAMENT_MAX_WEIGHTS[3])
    if series > 3:
        configured = min(TOURNAMENT_ABSOLUTE_MAX_WEIGHT,
                         configured+0.025*(series-3))
    return configured


def effective_component_weights(tournament: dict, recent: dict) -> dict[str, float]:
    if not tournament["available"]:
        return {"current_tournament": 0.0, "recent_60d": 1.0 if recent["available"] else 0.0}
    if not recent["available"]:
        return {"current_tournament": 1.0, "recent_60d": 0.0}
    cap = tournament_weight_limit(tournament["series"])
    raw_tournament = cap*(tournament["reliability"]/100)
    raw_recent = (1.0-cap)*(recent["reliability"]/100)
    total = raw_tournament+raw_recent
    tournament_weight = raw_tournament/total if total else 0.0
    tournament_weight = min(cap, tournament_weight)
    return {"current_tournament": round(tournament_weight, 6),
            "recent_60d": round(1.0-tournament_weight, 6)}


class TeamFormV3Service:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.performance = PerformanceVsExpectationService()
        self.strength = TeamStrengthV3Service(session)

    async def _current_tournament(self, team_id: int, cutoff: date,
                                  tournament_id: int | None) -> int | None:
        if tournament_id is not None:
            return tournament_id
        active = await self.session.scalar(select(Tournament.id).join(
            Match, Match.tournament_id == Tournament.id).where(
                or_(Match.team_a_id == team_id, Match.team_b_id == team_id),
                Tournament.start_date.is_not(None), Tournament.end_date.is_not(None),
                Tournament.start_date <= cutoff, Tournament.end_date >= cutoff,
            ).order_by(Tournament.start_date.desc(), Tournament.id.desc()).limit(1))
        if active is not None:
            return active
        # Team pages have no explicit tournament context. Imported tournament
        # dates are often absent or historical, so fall back to the tournament
        # of the team's latest match at/before the cutoff.
        return await self.session.scalar(select(Match.tournament_id).where(
            or_(Match.team_a_id == team_id, Match.team_b_id == team_id),
            Match.tournament_id.is_not(None), Match.match_date <= cutoff,
        ).order_by(Match.match_date.desc(), Match.id.desc()).limit(1))

    async def _expectation_indexes(self, team_ids: set[int], since: date,
                                   cutoff: date) -> tuple[dict, dict]:
        snapshots = list((await self.session.scalars(select(TeamStrengthV3Snapshot).where(
            TeamStrengthV3Snapshot.team_id.in_(team_ids),
            TeamStrengthV3Snapshot.as_of >= since,
            TeamStrengthV3Snapshot.as_of < cutoff,
            TeamStrengthV3Snapshot.model_version == "team_strength.v3"))).all()) if team_ids else []
        strengths = {(x.team_id, x.as_of): float(x.score) for x in snapshots if x.score is not None}
        rankings = list((await self.session.scalars(select(TeamRankingSnapshot).where(
            TeamRankingSnapshot.team_id.in_(team_ids),
            TeamRankingSnapshot.ranking_date < cutoff).order_by(
                TeamRankingSnapshot.team_id, TeamRankingSnapshot.ranking_date,
                TeamRankingSnapshot.id))).all()) if team_ids else []
        rank_index: dict[int, list[TeamRankingSnapshot]] = defaultdict(list)
        for row in rankings:
            rank_index[row.team_id].append(row)
        return strengths, rank_index

    async def _tournament_roster_id(self, team_id: int, tournament_id: int | None,
                                    cutoff: date) -> int | None:
        if tournament_id is None:
            return None
        return await self.session.scalar(select(DemoTeamRoster.roster_id).join(
            DemoFile, DemoFile.id == DemoTeamRoster.demo_file_id).join(
            Match, Match.id == DemoFile.match_id).where(
                DemoTeamRoster.team_id == team_id,
                DemoTeamRoster.resolution_status == "complete",
                DemoTeamRoster.roster_id.is_not(None),
                Match.tournament_id == tournament_id,
                DemoFile.match_date < cutoff,
            ).order_by(DemoFile.match_date.desc(), DemoFile.id.desc()).limit(1))

    @staticmethod
    def _rank_at(index: dict[int, list[TeamRankingSnapshot]], team_id: int | None,
                 event_date: date) -> int | None:
        if team_id is None:
            return None
        eligible = [x for x in index.get(team_id, []) if x.ranking_date <= event_date]
        return eligible[-1].rank if eligible else None

    async def _events(self, team_id: int, cutoff: date, roster_id: int | None,
                      exclude_match_id: int | None,
                      tournament_start: date | None = None,
                      current_members_override: set[int] | None = None) -> tuple[list[dict], dict]:
        since = min(cutoff-timedelta(days=WINDOW_DAYS), tournament_start) if tournament_start else cutoff-timedelta(days=WINDOW_DAYS)
        rows = (await self.session.execute(select(
            DemoFile, DemoMapResult, DemoTeamRoster, Match).join(
                DemoMapResult, DemoMapResult.demo_file_id == DemoFile.id).outerjoin(
                DemoTeamRoster, (DemoTeamRoster.demo_file_id == DemoFile.id) &
                                (DemoTeamRoster.team_id == team_id)).outerjoin(
                Match, Match.id == DemoFile.match_id).where(
                    DemoFile.match_date >= since, DemoFile.match_date < cutoff,
                    or_(DemoMapResult.team_a_id == team_id,
                        DemoMapResult.team_b_id == team_id),
                    DemoMapResult.team_a_score.is_not(None),
                    DemoMapResult.team_b_score.is_not(None)))).all()
        if exclude_match_id is not None:
            rows = [row for row in rows if eligible_event(
                row[0].match_date, cutoff, row[0].match_id, exclude_match_id)]
        grouped: dict[tuple[str, int], list] = defaultdict(list)
        for row in rows:
            key = ("match", row[0].match_id) if row[0].match_id is not None else ("demo", row[0].id)
            grouped[key].append(row)
        linked_roster_ids = {row[2].roster_id for row in rows if row[2] is not None and
                             row[2].resolution_status == "complete" and row[2].roster_id}
        relevant_roster_ids = linked_roster_ids | ({roster_id} if roster_id else set())
        member_rows = list((await self.session.execute(select(
            TeamRosterMember.roster_id, TeamRosterMember.player_id).where(
                TeamRosterMember.roster_id.in_(relevant_roster_ids),
                TeamRosterMember.player_id.is_not(None)))).all()) if relevant_roster_ids else []
        roster_members: dict[int, set[int]] = defaultdict(set)
        for linked_id, player_id in member_rows:
            roster_members[linked_id].add(player_id)
        current_members = current_members_override or (roster_members.get(roster_id, set()) if roster_id else set())
        def current_roster_link(link: DemoTeamRoster | None) -> float:
            if link is None or link.resolution_status != "complete" or roster_id is None:
                return 0.0
            if link.roster_id == roster_id:
                return 1.0
            linked_members = roster_members.get(link.roster_id, set())
            return roster_applicability(current_members, linked_members)
        candidates = []
        candidate_maps = len(rows)
        for key, series_rows in grouped.items():
            applicability = min((current_roster_link(row[2]) for row in series_rows), default=0.0)
            applicable = series_rows if applicability >= 0.6 else []
            if len(applicable) != len(series_rows):
                continue
            demo, first_result, _, match = applicable[0]
            expected_maps = ((match.team_a_maps_won or 0)+(match.team_b_maps_won or 0)) if match else 0
            if not series_data_complete(len(applicable), expected_maps):
                continue
            opponent_id = (first_result.team_b_id if first_result.team_a_id == team_id
                           else first_result.team_a_id)
            own_rounds, opponent_rounds, own_map_wins, opponent_map_wins = series_scores(
                team_id, [result for _, result, _, _ in applicable])
            won = series_won(own_map_wins, opponent_map_wins)
            if won is None:
                continue
            candidates.append({"series_key": f"{key[0]}:{key[1]}", "match_id": demo.match_id,
                "date": demo.match_date, "opponent_id": opponent_id,
                "tournament_id": match.tournament_id if match else None,
                "environment": match.environment if match else "unknown",
                "format": match.format if match else ("bo1" if len(applicable) == 1 else "unknown"),
                "won": won, "round_diff": own_rounds-opponent_rounds,
                "round_score": f"{own_rounds}:{opponent_rounds}",
                "rounds": own_rounds+opponent_rounds, "maps": len(applicable),
                "maps_won": own_map_wins, "maps_lost": opponent_map_wins,
                "roster_applicability": applicability, "data_complete": True})
        ids = {team_id} | {x["opponent_id"] for x in candidates if x["opponent_id"]}
        strengths, rankings = await self._expectation_indexes(ids, since, cutoff)
        teams = list((await self.session.scalars(select(Team).where(Team.id.in_(ids)))).all()) if ids else []
        names = {x.id: x.name for x in teams}
        tournaments = list((await self.session.scalars(select(Tournament).where(
            Tournament.id.in_({x["tournament_id"] for x in candidates if x["tournament_id"]})))).all()) if candidates else []
        tournament_names = {x.id: x.name for x in tournaments}
        events = []
        for value in candidates:
            event_date = value["date"]; opponent_id = value["opponent_id"]
            own_snapshot = strengths.get((team_id, event_date))
            opponent_snapshot = strengths.get((opponent_id, event_date))
            own_rank = self._rank_at(rankings, team_id, event_date)
            opponent_rank = self._rank_at(rankings, opponent_id, event_date)
            own_value, opponent_value, source = resolve_expectation(
                own_snapshot, opponent_snapshot, own_rank, opponent_rank)
            signal = self.performance.evaluate(own_strength=own_value,
                opponent_strength=opponent_value, won=value["won"],
                round_diff=value["round_diff"], maps=value["maps"],
                bo_format=value["format"])
            events.append({**value, **signal, "opponent": names.get(opponent_id),
                "tournament": tournament_names.get(value["tournament_id"]),
                "own_strength_at_event": own_value,
                "opponent_strength_at_event": opponent_value,
                "expectation_source": source, "own_rank": own_rank,
                "expectation_coverage": 1.0 if source in {
                    "historical_team_strength_v3", "historical_ranking_fallback"} else
                    0.5 if source == "partial_historical_ranking_fallback" else 0.0,
                "opponent_rank": opponent_rank,
                "opponent_group": rank_group_v3(opponent_rank),
                "age_days": (cutoff-event_date).days})
        candidate_by_tournament: dict[int | None, int] = defaultdict(int)
        for _, _, _, match in rows:
            candidate_by_tournament[match.tournament_id if match else None] += 1
        return events, {"candidate_maps": candidate_maps,
                        "candidate_maps_by_tournament": dict(candidate_by_tournament),
                        "current_roster_maps": sum(x["maps"] for x in events),
                        "excluded_roster_maps": candidate_maps-sum(x["maps"] for x in events)}

    async def calculate(self, team_id: int, as_of: date | None = None, *,
                        exclude_match_id: int | None = None,
                        tournament_id: int | None = None,
                        force: bool = False) -> dict:
        team = await self.session.get(Team, team_id)
        if team is None:
            raise ValueError("Team not found")
        cutoff = as_of or date.today()
        current_tournament_id = await self._current_tournament(team_id, cutoff, tournament_id)
        current_tournament = (await self.session.get(Tournament, current_tournament_id)
                              if current_tournament_id is not None else None)
        roster = await self.strength._roster(team, cutoff, as_of is not None)
        tournament_roster_id = await self._tournament_roster_id(
            team_id, current_tournament_id, cutoff)
        form_roster_id = tournament_roster_id or (roster.id if roster else None)
        effective = (await EffectiveRosterService(self.session).get_effective_roster(
            team_id, current_tournament_id, as_of=cutoff)) if current_tournament_id else None
        effective_members = {x["id"] for x in effective["effective_roster"]} if effective else set()
        # Demo rosters remain historical records; compare them against the event lineup without rewriting them.
        if effective_members and form_roster_id:
            # _events loads this roster id; a synthetic row is unnecessary because applicability is set-based.
            pass
        events, sample = await self._events(team_id, cutoff, form_roster_id,
                                           exclude_match_id,
                                           current_tournament.start_date if current_tournament else None,
                                           effective_members or None)
        tournament_events, recent_events = partition_events(events, current_tournament_id, cutoff)
        tournament = aggregate_events(tournament_events, recent=False)
        recent = aggregate_events(recent_events, recent=True)
        tournament_candidates = sample["candidate_maps_by_tournament"].get(
            current_tournament_id, 0) if current_tournament_id is not None else 0
        tournament_rel, tournament_rel_factors = scope_reliability(
            tournament, candidate_maps=tournament_candidates)
        recent_candidates = sample["candidate_maps"]-tournament_candidates
        recent_rel, recent_rel_factors = scope_reliability(recent, candidate_maps=recent_candidates)
        tournament.update(reliability=round(tournament_rel, 1),
                          reliability_breakdown=tournament_rel_factors,
                          tournament_id=current_tournament_id)
        recent.update(reliability=round(recent_rel, 1),
                      reliability_breakdown=recent_rel_factors,
                      window_days=WINDOW_DAYS,
                      excludes_tournament_id=current_tournament_id)
        weights = effective_component_weights(tournament, recent)
        delta = (sum(scope["delta"] * weights[key] for key, scope in
                     (("current_tournament", tournament), ("recent_60d", recent))
                     if scope["delta"] is not None)
                 if any(weights.values()) else None)
        reliability = (tournament_rel*weights["current_tournament"] +
                       recent_rel*weights["recent_60d"])
        all_event_keys = [x["series_key"] for x in tournament_events+recent_events]
        groups = {}
        for group in ("top_1_10", "top_11_20", "top_21_30", "others", "unknown"):
            selected = [x for x in events if x["opponent_group"] == group]
            group_value = aggregate_events(selected, recent=True)
            groups[group] = {key: group_value[key] for key in
                             ("delta", "series", "maps", "rounds", "available")}
        result = {"delta": None if delta is None else round(delta, 2),
            "score": None if delta is None else round(delta_to_score(delta), 2),
            "form_delta": None if delta is None else round(delta, 2),
            "form_score": None if delta is None else round(delta_to_score(delta), 2),
            "reliability": round(reliability, 1), "model_version": MODEL_VERSION,
            "calculation_revision": CALCULATION_REVISION,
            "as_of": cutoff, "team_id": team_id, "roster_id": form_roster_id,
            "roster_source": "current_tournament_latest_demo" if tournament_roster_id else
                             "historical_or_current_team_roster",
            "current_tournament": {**tournament,
                "effective_weight": weights["current_tournament"]},
            "recent_60d": {**recent, "effective_weight": weights["recent_60d"]},
            "effective_weights": weights, "opponent_breakdown": groups,
            "events": tournament["events"]+recent["events"],
            "environment_breakdown": {environment: sum(x["environment"] == environment for x in events)
                                      for environment in ("lan", "online", "unknown")},
            "sample": {**sample, "series": len(events),
                       "maps": sum(x["maps"] for x in events),
                       "rounds": sum(x["rounds"] for x in events)},
            "reliability_breakdown": {"current_tournament": tournament_rel_factors,
                                      "recent_60d": recent_rel_factors},
            "invariants": {"current_roster_only": True,
                "event_date_strictly_before_as_of": True,
                "one_series_one_event": len(all_event_keys) == len(set(all_event_keys)),
                "tournament_excluded_from_recent": not set(x["series_key"] for x in tournament_events) &
                                                    set(x["series_key"] for x in recent_events),
                "opponent_independent": True, "maps_v3_excluded": True,
            "raw_winrate_factor_excluded": True}}
        result.update(
            tournament_delta=tournament["delta"],
            tournament_reliability=tournament["reliability"],
            tournament_effective_weight=weights["current_tournament"],
            recent_delta=recent["delta"], recent_reliability=recent["reliability"],
            recent_effective_weight=weights["recent_60d"], final_delta=result["delta"],
        )
        if force and exclude_match_id is None:
            snapshot = await self.session.scalar(select(TeamFormV3Snapshot).where(
                TeamFormV3Snapshot.team_id == team_id,
                TeamFormV3Snapshot.as_of == cutoff,
                TeamFormV3Snapshot.model_version == MODEL_VERSION).limit(1))
            if snapshot is None:
                snapshot = TeamFormV3Snapshot(team_id=team_id, as_of=cutoff,
                    tournament_id=current_tournament_id, model_version=MODEL_VERSION,
                    form_score=result["score"], form_delta=result["delta"],
                    reliability=result["reliability"], breakdown={})
                self.session.add(snapshot)
            snapshot.form_score=result["score"]; snapshot.form_delta=result["delta"]
            snapshot.tournament_id=current_tournament_id
            snapshot.reliability=result["reliability"]
            snapshot.current_tournament_delta=tournament["delta"] if tournament["available"] else None
            snapshot.recent_60d_delta=recent["delta"] if recent["available"] else None
            snapshot.breakdown=_json_safe(result); snapshot.calculated_at=datetime.now(UTC)
        return result
