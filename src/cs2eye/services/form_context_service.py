from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from math import exp

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.demo import DemoMapResult, DemoTeamRoster
from cs2eye.models.demo_file import DemoFile
from cs2eye.models.match import Match, Tournament
from cs2eye.models.team import TeamRankingSnapshot


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def rank_strength(rank: int | None) -> float | None:
    """Convert an as-of rank to a conservative 0..100 opponent-strength scale."""
    if rank is None:
        return None
    return clamp(98.0 - min(rank, 60) * 1.6, 20.0, 96.4)


def expected_probability(team_rank: int | None, opponent_rank: int | None) -> float:
    own, opponent = rank_strength(team_rank), rank_strength(opponent_rank)
    if own is None or opponent is None:
        return .5
    return 1.0 / (1.0 + exp(-(own - opponent) / 12.0))


def series_quality(won: bool, maps_for: int, maps_against: int,
                   round_margin: float | None = None) -> tuple[float, bool]:
    total = max(1, maps_for + maps_against)
    dominance = abs(maps_for - maps_against) / total
    if round_margin is not None:
        dominance = dominance * .7 + min(1.0, abs(round_margin)) * .3
    quality = (.65 + .30 * dominance) if won else (.35 - .30 * dominance)
    return max(.02, min(.98, quality)), dominance < .45


@dataclass(frozen=True)
class SeriesSignal:
    match_id: int
    match_date: date
    tournament_id: int | None
    opponent_rank: int | None
    expectation: float
    actual_quality: float
    opponent_strength: float | None
    performance_delta: float
    won: bool
    close: bool
    weight: float
    ranking_available: bool


class FormContextService:
    """Opponent-adjusted series form using only information strictly before as_of."""
    def __init__(self, session: AsyncSession):
        self.session = session

    async def calculate(self, team_id: int, as_of: date | None = None,
                        tournament_id: int | None = None,
        exclude_match_id: int | None = None) -> dict:
        as_of = as_of or date.today()
        if tournament_id is None:
            tournament_id = await self._context_tournament(team_id, as_of)
        window = Match.match_date >= as_of - timedelta(days=60)
        date_scope = or_(window, Match.tournament_id == tournament_id) if tournament_id is not None else window
        matches = list((await self.session.scalars(select(Match).where(
            or_(Match.team_a_id == team_id, Match.team_b_id == team_id),
            Match.match_date < as_of,
            date_scope,
            Match.status == "completed",
            Match.winner_team_id.is_not(None),
        ).order_by(Match.match_date, Match.id))).all())
        if exclude_match_id is not None:
            matches = [match for match in matches if match.id != exclude_match_id]
        signals = await self._signals(team_id, matches, as_of)
        recent_signals = [item for item in signals if item.match_date >= as_of - timedelta(days=60)]
        recent = self._aggregate(recent_signals, minimum=2)
        tournament_signals = [item for item in signals if item.tournament_id == tournament_id]
        tournament = self._aggregate(tournament_signals, minimum=1)
        counts = self._counts(recent_signals)
        return {
            "as_of": as_of, "window_days": 60, "tournament_id": tournament_id,
            "tournament_form_score": tournament["adjusted_form_score"],
            "tournament_strength_of_schedule_score": tournament["strength_of_schedule_score"],
            "tournament_reliability": tournament["reliability"],
            "recent_60d_adjusted_form_score": recent["adjusted_form_score"],
            "strength_of_schedule_score": recent["strength_of_schedule_score"],
            "performance_vs_expectation_score": recent["performance_vs_expectation_score"],
            "recent_60d_reliability": recent["reliability"],
            "tournament_matches_count": len(tournament_signals),
            "recent_60d_matches_count": len(recent_signals),
            **counts,
            "status": "available" if len(recent_signals) >= 2 else "insufficient_data",
            "tournament_status": "available" if tournament_signals else "insufficient_data",
            "cutoff_policy": "event_date < as_of; same-day isolated",
        }

    async def compare(self, team_a_id: int, team_b_id: int, as_of: date | None = None,
                      tournament_id: int | None = None, exclude_match_id: int | None = None) -> dict:
        if tournament_id is None:
            tournament_id = await self._common_tournament(team_a_id, team_b_id, as_of or date.today())
        a = await self.calculate(team_a_id, as_of, tournament_id, exclude_match_id)
        b = await self.calculate(team_b_id, as_of, tournament_id, exclude_match_id)
        return {"team_a_form_context": a, "team_b_form_context": b, "tournament_id": tournament_id}

    async def _signals(self, team_id: int, matches: list[Match], as_of: date) -> list[SeriesSignal]:
        if not matches:
            return []
        team_ids = {value for match in matches for value in (match.team_a_id, match.team_b_id) if value}
        rankings = list((await self.session.scalars(select(TeamRankingSnapshot).where(
            TeamRankingSnapshot.team_id.in_(team_ids),
            TeamRankingSnapshot.ranking_date <= as_of,
        ).order_by(TeamRankingSnapshot.team_id, TeamRankingSnapshot.ranking_date))).all())
        rank_index: dict[int, list[TeamRankingSnapshot]] = defaultdict(list)
        for row in rankings:
            rank_index[row.team_id].append(row)
        elo_before = await self._elo_before(as_of, {value for match in matches for value in (match.team_a_id, match.team_b_id) if value})
        map_rows = (await self.session.execute(select(DemoFile.match_id, DemoMapResult).join(
            DemoMapResult, DemoMapResult.demo_file_id == DemoFile.id
        ).where(DemoFile.match_id.in_([match.id for match in matches])))).all()
        maps_by_match: dict[int, list[DemoMapResult]] = defaultdict(list)
        for match_id, item in map_rows:
            maps_by_match[match_id].append(item)
        roster_rows = (await self.session.execute(select(
            DemoFile.match_id, DemoTeamRoster.team_id, DemoTeamRoster.roster_id,
        ).join(DemoTeamRoster, DemoTeamRoster.demo_file_id == DemoFile.id).where(
            DemoFile.match_id.in_([match.id for match in matches]),
            DemoTeamRoster.resolution_status == "complete",
        ))).all()
        match_rosters: dict[tuple[int, int], int] = {}
        for match_id, roster_team_id, roster_id in roster_rows:
            if roster_id is not None:
                match_rosters[(match_id, roster_team_id)] = roster_id
        current_roster = next((match_rosters[(match.id, team_id)] for match in reversed(matches)
            if (match.id, team_id) in match_rosters), None)
        signals = []
        for match in matches:
            opponent_id = match.team_b_id if match.team_a_id == team_id else match.team_a_id
            if opponent_id is None:
                continue
            team_rank = self._rank(rank_index, team_id, match.match_date)
            opponent_rank = self._rank(rank_index, opponent_id, match.match_date)
            team_strength = rank_strength(team_rank)
            opponent_strength = rank_strength(opponent_rank)
            if team_strength is None:
                team_strength = self._elo_strength(elo_before.get((match.id, team_id), 1500.0))
            if opponent_strength is None:
                opponent_strength = self._elo_strength(elo_before.get((match.id, opponent_id), 1500.0))
            expectation = 1.0 / (1.0 + exp(-(team_strength - opponent_strength) / 12.0))
            team_is_a = match.team_a_id == team_id
            maps_for = match.team_a_maps_won if team_is_a else match.team_b_maps_won
            maps_against = match.team_b_maps_won if team_is_a else match.team_a_maps_won
            margins = []
            for item in maps_by_match[match.id]:
                if item.team_a_score is None or item.team_b_score is None:
                    continue
                own = item.team_a_score if item.team_a_id == team_id else item.team_b_score
                other = item.team_b_score if item.team_a_id == team_id else item.team_a_score
                if own is not None and other is not None:
                    margins.append((own - other) / max(1, own + other))
            round_margin = sum(margins) / len(margins) if margins else None
            won = match.winner_team_id == team_id
            quality, close = series_quality(won, maps_for, maps_against, round_margin)
            age = max(0, (as_of - match.match_date).days)
            weight = exp(-age / 35.0) * {"bo1": .85, "bo3": 1.0, "bo5": 1.1}.get(match.format, .9)
            if match.environment == "lan":
                weight *= 1.05
            match_roster = match_rosters.get((match.id, team_id))
            if current_roster is not None and match_roster is not None and match_roster != current_roster:
                weight *= .75
            if match_rosters and (match.id, opponent_id) not in match_rosters:
                weight *= .9
            signals.append(SeriesSignal(match.id, match.match_date, match.tournament_id,
                opponent_rank, expectation, quality, opponent_strength, quality - expectation,
                won, close, weight, opponent_rank is not None))
        return signals

    @staticmethod
    def _aggregate(rows: list[SeriesSignal], minimum: int) -> dict:
        if len(rows) < minimum:
            return {"adjusted_form_score": None, "strength_of_schedule_score": None,
                    "performance_vs_expectation_score": None, "reliability": 0.0}
        total = sum(row.weight for row in rows)
        known = [row for row in rows if row.opponent_strength is not None]
        known_weight = sum(row.weight for row in known)
        schedule = sum(row.opponent_strength * row.weight for row in known) / known_weight if known_weight else None
        performance = clamp(50 + sum(row.performance_delta * row.weight for row in rows) / total * 100)
        adjusted_values = [
            row.actual_quality * .55 + ((row.opponent_strength or 50) / 100) * .25
            + clamp(50 + row.performance_delta * 100) / 100 * .20 for row in rows
        ]
        adjusted = clamp(sum(value * row.weight for value, row in zip(adjusted_values, rows, strict=True)) / total * 100)
        ranking_weight = sum(row.weight for row in rows if row.ranking_available)
        coverage = ranking_weight / total if total else 0
        reliability = min(1.0, len(rows) / 6) * (.65 + .35 * coverage)
        return {"adjusted_form_score": round(adjusted, 2),
                "strength_of_schedule_score": round(schedule, 2) if schedule is not None else None,
                "performance_vs_expectation_score": round(performance, 2),
                "reliability": round(reliability, 4)}

    @staticmethod
    def _counts(rows: list[SeriesSignal]) -> dict:
        ranks = [row.opponent_rank for row in rows]
        return {"top5_matches_60d": sum(rank is not None and rank <= 5 for rank in ranks),
                "top10_matches_60d": sum(rank is not None and rank <= 10 for rank in ranks),
                "top20_matches_60d": sum(rank is not None and rank <= 20 for rank in ranks),
                "top30_matches_60d": sum(rank is not None and rank <= 30 for rank in ranks),
                "close_series_count": sum(row.close for row in rows),
                "upset_wins_count": sum(row.won and row.expectation < .4 for row in rows),
                "strong_losses_count": sum(not row.won and row.close and row.expectation < .4 for row in rows),
                "performed_above_expectation_count": sum(row.performance_delta > .05 for row in rows),
                "performed_below_expectation_count": sum(row.performance_delta < -.05 for row in rows)}

    @staticmethod
    def _rank(index: dict[int, list[TeamRankingSnapshot]], team_id: int, as_of: date) -> int | None:
        row = next((item for item in reversed(index.get(team_id, [])) if item.ranking_date <= as_of), None)
        return row.rank if row else None

    async def _context_tournament(self, team_id: int, as_of: date) -> int | None:
        rows = list((await self.session.scalars(select(Tournament).join(
            Match, Match.tournament_id == Tournament.id
        ).where(or_(Match.team_a_id == team_id, Match.team_b_id == team_id),
            Tournament.end_date >= as_of - timedelta(days=7),
            or_(Tournament.start_date.is_(None), Tournament.start_date <= as_of + timedelta(days=30)))
            .distinct())).all())
        if not rows:
            return None
        def distance(item: Tournament) -> tuple[int, int]:
            if item.start_date and item.end_date and item.start_date <= as_of <= item.end_date:
                return 0, 0
            anchor=item.start_date or item.end_date or as_of
            return 1, abs((anchor-as_of).days)
        return min(rows,key=distance).id

    async def _elo_before(self, as_of: date, relevant_teams: set[int]) -> dict[tuple[int, int], float]:
        if not relevant_teams:
            return {}
        history = list((await self.session.scalars(select(Match).where(
            Match.match_date < as_of, Match.status == "completed", Match.winner_team_id.is_not(None),
            or_(Match.team_a_id.in_(relevant_teams), Match.team_b_id.in_(relevant_teams)),
        ).order_by(Match.match_date, Match.id))).all())
        ratings: dict[int, float] = defaultdict(lambda: 1500.0)
        before: dict[tuple[int, int], float] = {}
        by_day: dict[date, list[Match]] = defaultdict(list)
        for match in history:
            by_day[match.match_date].append(match)
        for day in sorted(by_day):
            for match in by_day[day]:
                if match.team_a_id and match.team_b_id:
                    before[(match.id, match.team_a_id)] = ratings[match.team_a_id]
                    before[(match.id, match.team_b_id)] = ratings[match.team_b_id]
            changes: dict[int, float] = defaultdict(float)
            for match in by_day[day]:
                if not match.team_a_id or not match.team_b_id or match.winner_team_id not in {match.team_a_id, match.team_b_id}:
                    continue
                a,b=match.team_a_id,match.team_b_id
                expected_a=1/(1+10**((ratings[b]-ratings[a])/400))
                actual_a=1.0 if match.winner_team_id==a else 0.0
                changes[a]+=24*(actual_a-expected_a);changes[b]-=24*(actual_a-expected_a)
            for team,change in changes.items():ratings[team]+=change
        return before

    @staticmethod
    def _elo_strength(rating: float) -> float:
        return clamp(50+(rating-1500)/8,20,90)

    async def _common_tournament(self, a: int, b: int, as_of: date) -> int | None:
        rows = list((await self.session.scalars(select(Match).where(
            Match.tournament_id.is_not(None), Match.match_date >= as_of - timedelta(days=30),
            or_((Match.team_a_id == a) & (Match.team_b_id == b),
                (Match.team_a_id == b) & (Match.team_b_id == a)))
            .order_by(Match.match_date, Match.id))).all())
        return min(rows,key=lambda item:abs((item.match_date-as_of).days)).tournament_id if rows else None
