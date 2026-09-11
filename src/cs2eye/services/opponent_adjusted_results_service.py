from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.analytics.team_strength_v3_config import RESULT_WEIGHTS, ROSTER_APPLICABILITY_WEIGHTS
from cs2eye.models.demo import DemoMapResult, DemoTeamRoster
from cs2eye.models.demo_file import DemoFile
from cs2eye.models.team import TeamRankingSnapshot, TeamRosterMember
from cs2eye.services.performance_profile_service import rank_group_v3


def clamp(value: float, low: float = 0., high: float = 1.) -> float:
    return max(low, min(high, value))


def opponent_rank_strength(rank: int | None) -> float | None:
    if rank is None: return None
    return clamp((61 - min(rank, 60)) / 60)


def eligible_historical_event(event_date: date, as_of: date, match_id: int | None,
                              exclude_match_id: int | None = None) -> bool:
    return event_date < as_of and (exclude_match_id is None or match_id != exclude_match_id)


def adjusted_map_quality(*, won: bool, round_diff: int, opponent_rank: int | None) -> dict:
    strength = opponent_rank_strength(opponent_rank)
    context = .5 if strength is None else strength
    result_value = (.62 + .38 * context) if won else (.38 * context)
    margin = clamp(round_diff / 13., -1., 1.)
    margin_value = clamp(.5 + .30 * margin + .20 * (context - .5))
    score = 100 * (result_value * RESULT_WEIGHTS["map_result"] + margin_value * RESULT_WEIGHTS["round_differential"])
    return {"score": round(score, 2), "map_result_value": round(result_value * 100, 2),
            "round_differential_value": round(margin_value * 100, 2),
            "opponent_strength": None if strength is None else round(strength * 100, 2)}


def roster_applicability(linked_roster_id: int | None, current_roster_id: int | None,
                         overlap: int = 0) -> str:
    if linked_roster_id is None or current_roster_id is None:
        return "unknown"
    if linked_roster_id == current_roster_id:
        return "current"
    return "partial" if overlap >= 3 else "old"


class OpponentAdjustedResultsService:
    def __init__(self, session: AsyncSession): self.session = session

    async def calculate(self, team_id: int, *, as_of: date, roster_id: int | None,
                        exclude_match_id: int | None = None) -> dict:
        query = (select(DemoFile, DemoMapResult, DemoTeamRoster)
                 .join(DemoMapResult, DemoMapResult.demo_file_id == DemoFile.id)
                 .outerjoin(DemoTeamRoster, (DemoTeamRoster.demo_file_id == DemoFile.id) &
                            (DemoTeamRoster.team_id == team_id))
                 .where(DemoFile.match_date < as_of,
                        ((DemoMapResult.team_a_id == team_id) | (DemoMapResult.team_b_id == team_id)),
                        DemoMapResult.team_a_score.is_not(None), DemoMapResult.team_b_score.is_not(None)))
        rows = (await self.session.execute(query)).all()
        rows = [row for row in rows if eligible_historical_event(row[0].match_date, as_of, row[0].match_id, exclude_match_id)]
        total_maps = len(rows)
        linked_roster_ids = {row[2].roster_id for row in rows if row[2] and row[2].roster_id}
        member_rows = list((await self.session.execute(select(
            TeamRosterMember.roster_id, TeamRosterMember.player_id).where(
                TeamRosterMember.roster_id.in_(linked_roster_ids | ({roster_id} if roster_id else set())),
                TeamRosterMember.player_id.is_not(None)))).all()) if linked_roster_ids or roster_id else []
        members: dict[int, set[int]] = defaultdict(set)
        for linked_id, player_id in member_rows:
            members[linked_id].add(player_id)
        current_members = members.get(roster_id, set()) if roster_id else set()
        classified = []
        for row in rows:
            link = row[2]
            linked_id = link.roster_id if link and link.resolution_status == "complete" else None
            overlap = len(current_members & members.get(linked_id, set())) if linked_id else 0
            applicability = roster_applicability(linked_id, roster_id, overlap)
            classified.append((row, applicability, ROSTER_APPLICABILITY_WEIGHTS[applicability]))
        selected = [row for row in classified if row[2] > 0]
        opponent_ids = {result.team_b_id if result.team_a_id == team_id else result.team_a_id
                        for ((_, result, _), _, _) in selected}
        rankings = list((await self.session.scalars(select(TeamRankingSnapshot).where(
            TeamRankingSnapshot.team_id.in_({x for x in opponent_ids if x}),
            TeamRankingSnapshot.ranking_date < as_of).order_by(
                TeamRankingSnapshot.team_id, TeamRankingSnapshot.ranking_date))).all()) if opponent_ids else []
        by_team = defaultdict(list)
        for ranking in rankings: by_team[ranking.team_id].append(ranking)
        items = []
        for (demo, result, link), applicability, applicability_weight in selected:
            own_a = result.team_a_id == team_id
            opponent_id = result.team_b_id if own_a else result.team_a_id
            opponent_rank = None
            eligible = [r for r in by_team.get(opponent_id, []) if r.ranking_date <= demo.match_date]
            if eligible: opponent_rank = eligible[-1].rank
            own_score = result.team_a_score if own_a else result.team_b_score
            opponent_score = result.team_b_score if own_a else result.team_a_score
            won = own_score > opponent_score
            quality = adjusted_map_quality(won=won, round_diff=own_score-opponent_score, opponent_rank=opponent_rank)
            items.append({"demo_file_id": demo.id, "match_id": demo.match_id, "date": demo.match_date,
                          "map_name": result.map_name, "won": won, "round_diff": own_score-opponent_score,
                          "opponent_id": opponent_id, "opponent_rank": opponent_rank,
                          "opponent_rank_group": rank_group_v3(opponent_rank), "roster_id": link.roster_id if link else None,
                          "roster_applicability": applicability, "roster_weight": applicability_weight,
                          "rounds": own_score + opponent_score,
                          **quality})
        def aggregate(values: list[dict]) -> dict:
            weight = sum(x["roster_weight"] for x in values)
            return {"maps": len(values), "wins": sum(x["won"] for x in values),
                    "losses": sum(not x["won"] for x in values),
                    "average_round_diff": round(sum(x["round_diff"] for x in values)/len(values), 2) if values else None,
                    "adjusted_score": round(sum(x["score"]*x["roster_weight"] for x in values)/weight, 2) if weight else None}
        known = sum(x["opponent_rank"] is not None for x in items)
        score = aggregate(items)["adjusted_score"]
        sample_rel = min(1., len(items)/20); ranking_coverage = known/len(items) if items else 0.
        applicable_weight = sum(x["roster_weight"] for x in items)
        effective_rounds = sum(x["rounds"]*x["roster_weight"] for x in items)
        applicability_coverage = applicable_weight/len(items) if items else 0.
        reliability = 100 * (sample_rel ** .5) * ranking_coverage * applicability_coverage
        current_maps = sum(x["roster_applicability"] == "current" for x in items)
        partial_maps = sum(x["roster_applicability"] == "partial" for x in items)
        current_matches = len({x["match_id"] if x["match_id"] is not None else f'demo:{x["demo_file_id"]}'
                               for x in items if x["roster_applicability"] == "current"})
        return {"score": score, "reliability": round(reliability, 1), "sample": {"total_maps": total_maps,
                "current_roster_maps": current_maps, "partial_roster_maps": partial_maps,
                "old_roster_maps": sum(applicability == "old" for _, applicability, _ in classified),
                "unknown_roster_maps": sum(applicability == "unknown" for _, applicability, _ in classified),
                "current_roster_matches": current_matches, "selected_maps": len(items),
                "selected_rounds": sum(x["rounds"] for x in items),
                "effective_maps": round(applicable_weight, 2),
                "effective_rounds": round(effective_rounds, 2),
                "current_roster_percentage": round(100*current_maps/total_maps, 1) if total_maps else 0,
                "ranking_snapshots": known, "ranking_coverage": round(100*ranking_coverage, 1),
                "roster_applicability_coverage": round(100*applicability_coverage, 1),
                "latest_current_roster_map_date": max((x["date"] for x in items if x["roster_applicability"] == "current"), default=None)},
                "overall": aggregate(items), "groups": {group: aggregate([x for x in items if x["opponent_rank_group"] == group])
                for group in ("top_1_10", "top_11_20", "top_21_30", "others", "unknown")},
                "maps": items, "formula": RESULT_WEIGHTS}
