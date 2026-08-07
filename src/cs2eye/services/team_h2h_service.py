from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Literal

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from cs2eye.models.demo import DemoMapResult, DemoPlayerStat, DemoTeamRoster
from cs2eye.models.demo_file import DemoFile
from cs2eye.models.team import Player, Team, TeamRoster, TeamRosterMember
from cs2eye.models.match import Match
from cs2eye.services.match_service import MatchService


SliceStatus = Literal[
    "available", "no_meetings", "current_roster_unavailable",
    "current_rosters_never_met", "partial_data",
]


class SameTeamH2HError(ValueError):
    pass


class H2HTeamNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class H2HTeam:
    id: int
    name: str
    current_roster_id: int | None


@dataclass(frozen=True)
class H2HRecentMap:
    demo_file_id: int
    match_date: date
    tournament: str
    map_name: str
    team_a_score: int
    team_b_score: int
    winner_team_id: int
    went_to_overtime: bool
    team_a_roster_id: int | None
    team_b_roster_id: int | None
    recency_weight: float


@dataclass(frozen=True)
class H2HTeamMetrics:
    maps_won: int
    map_win_rate: float | None
    weighted_map_win_rate: float | None
    rounds_won: int
    round_win_rate: float | None
    weighted_round_win_rate: float | None
    performance_score: float | None
    h2h_rating: float | None


@dataclass(frozen=True)
class H2HMapBreakdown:
    map_name: str
    maps_played: int
    team_a_maps_won: int
    team_b_maps_won: int
    team_a_map_win_rate: float
    team_b_map_win_rate: float
    team_a_rounds_won: int
    team_b_rounds_won: int
    team_a_round_win_rate: float
    team_b_round_win_rate: float
    first_meeting_date: date
    last_meeting_date: date
    overtime_maps: int


@dataclass(frozen=True)
class H2HFactor:
    code: str
    score: float
    weight: float
    explanation: str


@dataclass(frozen=True)
class H2HSlice:
    status: SliceStatus
    candidate_maps_count: int
    included_maps_count: int
    excluded_maps_count: int
    maps_played: int
    effective_maps: float
    sample_label: str
    confidence_score: float
    confidence_level: str
    first_meeting_date: date | None
    last_meeting_date: date | None
    team_a: H2HTeamMetrics
    team_b: H2HTeamMetrics
    advantage_team_id: int | None
    advantage_team_name: str | None
    advantage_diff: float | None
    advantage_level: str
    maps: list[H2HMapBreakdown]
    recent_maps: list[H2HRecentMap]
    factors: list[H2HFactor]
    warnings: list[str]
    series_played: int = 0
    team_a_series_won: int = 0
    team_b_series_won: int = 0


@dataclass(frozen=True)
class H2HPlayerExperience:
    player_id: int | None
    nickname: str
    maps_against_opponent: int
    has_h2h_experience: bool


@dataclass(frozen=True)
class H2HPlayerContext:
    current_roster_id: int | None
    current_players_count: int
    players_with_h2h_experience_count: int
    players_without_h2h_experience_count: int
    experience_coverage_percent: float | None
    average_maps_per_current_player: float | None
    experience_data_status: str
    players: list[H2HPlayerExperience]


@dataclass(frozen=True)
class H2HLatestRosterOverlap:
    status: str
    latest_h2h_roster_id: int | None
    current_roster_id: int | None
    latest_roster_players_count: int
    current_roster_players_count: int
    retained_players_count: int
    changed_players_count: int
    retained_players: list[H2HPlayerExperience]
    new_current_players: list[H2HPlayerExperience]
    former_players: list[H2HPlayerExperience]


@dataclass(frozen=True)
class H2HRosterTeamContext:
    experience: H2HPlayerContext
    latest_roster_overlap: H2HLatestRosterOverlap


@dataclass(frozen=True)
class H2HRosterContext:
    team_a: H2HRosterTeamContext
    team_b: H2HRosterTeamContext
    history_applicability: str


@dataclass(frozen=True)
class H2HInsight:
    code: str
    text: str


@dataclass(frozen=True)
class TeamH2HComparison:
    status: str
    team_a: H2HTeam
    team_b: H2HTeam
    organizations: H2HSlice
    current_rosters: H2HSlice
    roster_context: H2HRosterContext
    insights: list[H2HInsight]


@dataclass(frozen=True)
class _Candidate:
    demo: DemoFile
    result: DemoMapResult
    roster_a: DemoTeamRoster | None
    roster_b: DemoTeamRoster | None


@dataclass(frozen=True)
class _Normalized:
    demo_file_id: int
    match_date: date
    tournament: str
    map_name: str
    score_a: int
    score_b: int
    winner_team_id: int
    overtime: bool
    roster_a_id: int | None
    roster_b_id: int | None
    weight: float
    future_date: bool


class TeamH2HService:
    def __init__(self, session: AsyncSession, *, today: date | None = None) -> None:
        self._session = session
        self._today = today or date.today()

    async def compare(
        self, team_a_id: int, team_b_id: int, *, recent_limit: int = 10,
    ) -> TeamH2HComparison:
        if team_a_id == team_b_id:
            raise SameTeamH2HError("Нужно выбрать две разные команды.")
        team_a, team_b = await self._session.get(Team, team_a_id), await self._session.get(Team, team_b_id)
        if team_a is None or team_b is None:
            raise H2HTeamNotFoundError("Команда не найдена.")

        candidates = await self._load_candidates(team_a_id, team_b_id)
        valid = [item for item in (self._normalize(c, team_a_id, team_b_id) for c in candidates) if item]
        organizations = self._build_slice(candidates, valid, team_a, team_b, recent_limit, empty_status="no_meetings")

        current_available = await self._current_rosters_available(team_a, team_b)
        if current_available:
            current_candidates = [
                c for c in candidates
                if c.roster_a is not None and c.roster_b is not None
                and c.roster_a.roster_id == team_a.current_roster_id
                and c.roster_b.roster_id == team_b.current_roster_id
            ]
            current_valid = [
                n for c in current_candidates
                if c.roster_a.resolution_status == "complete" and c.roster_b.resolution_status == "complete"
                for n in [self._normalize(c, team_a_id, team_b_id)] if n is not None
            ]
            current = self._build_slice(
                current_candidates, current_valid, team_a, team_b, recent_limit,
                empty_status="current_rosters_never_met",
            )
        else:
            current = self._empty_slice("current_roster_unavailable")

        org_series = await self._series_counts(team_a, team_b, current_rosters=False)
        organizations = replace(organizations, series_played=sum(org_series),
                                team_a_series_won=org_series[0], team_b_series_won=org_series[1])
        if current_available:
            current_series = await self._series_counts(team_a, team_b, current_rosters=True)
            current = replace(current, series_played=sum(current_series),
                              team_a_series_won=current_series[0], team_b_series_won=current_series[1])

        roster_context = await self._roster_context(team_a, team_b, valid, current.maps_played)
        insights = self._insights(team_a, team_b, organizations, current, roster_context)
        return TeamH2HComparison(
            "available", self._team(team_a), self._team(team_b), organizations,
            current, roster_context, insights,
        )

    async def _load_candidates(self, team_a_id: int, team_b_id: int) -> list[_Candidate]:
        link_a, link_b = aliased(DemoTeamRoster), aliased(DemoTeamRoster)
        rows = (await self._session.execute(
            select(DemoFile, DemoMapResult, link_a, link_b)
            .join(DemoMapResult, DemoMapResult.demo_file_id == DemoFile.id)
            .outerjoin(link_a, and_(link_a.demo_file_id == DemoFile.id, link_a.team_id == team_a_id))
            .outerjoin(link_b, and_(link_b.demo_file_id == DemoFile.id, link_b.team_id == team_b_id))
            .where(or_(
                and_(DemoMapResult.team_a_id == team_a_id, DemoMapResult.team_b_id == team_b_id),
                and_(DemoMapResult.team_a_id == team_b_id, DemoMapResult.team_b_id == team_a_id),
            ))
            .order_by(DemoFile.match_date.desc(), DemoFile.id.desc())
        )).all()
        return [_Candidate(*row) for row in rows]

    def _normalize(self, candidate: _Candidate, team_a_id: int, team_b_id: int) -> _Normalized | None:
        result, demo = candidate.result, candidate.demo
        if (result.round_data_status != "complete" or result.map_name is None
                or result.team_a_id is None or result.team_b_id is None
                or result.team_a_score is None or result.team_b_score is None
                or result.team_a_score == result.team_b_score):
            return None
        a_on_left = result.team_a_id == team_a_id and result.team_b_id == team_b_id
        if not a_on_left and not (result.team_b_id == team_a_id and result.team_a_id == team_b_id):
            return None
        score_a = result.team_a_score if a_on_left else result.team_b_score
        score_b = result.team_b_score if a_on_left else result.team_a_score
        weight, future = self.recency_weight(demo.match_date, self._today)
        return _Normalized(
            demo.id, demo.match_date, demo.tournament_name, result.map_name, score_a, score_b,
            team_a_id if score_a > score_b else team_b_id, bool(result.went_to_overtime),
            candidate.roster_a.roster_id if candidate.roster_a and candidate.roster_a.resolution_status == "complete" else None,
            candidate.roster_b.roster_id if candidate.roster_b and candidate.roster_b.resolution_status == "complete" else None,
            weight, future,
        )

    @staticmethod
    def recency_weight(match_date: date, today: date) -> tuple[float, bool]:
        age = (today - match_date).days
        future = age < 0
        age = max(0, age)
        if age <= 90: return 1.0, future
        if age <= 180: return 0.8, future
        if age <= 365: return 0.6, future
        if age <= 730: return 0.35, future
        return 0.15, future

    @staticmethod
    def freshness_score(last_date: date | None, today: date) -> float:
        if last_date is None: return 0.0
        age = max(0, (today - last_date).days)
        if age <= 30: return 100.0
        if age <= 90: return 85.0
        if age <= 180: return 65.0
        if age <= 365: return 40.0
        return 15.0

    @staticmethod
    def sample_label(count: int) -> str:
        if count == 0: return "no_data"
        if count <= 2: return "very_small"
        if count <= 5: return "small"
        if count <= 9: return "medium"
        return "sufficient"

    @staticmethod
    def confidence_level(score: float, count: int) -> str:
        if count == 0: return "no_data"
        if score < 35: return "low"
        if score < 70: return "medium"
        return "high"

    @staticmethod
    def advantage_level(diff: float) -> str:
        if diff < 5: return "none"
        if diff < 10: return "small"
        if diff < 20: return "clear"
        return "strong"

    def _build_slice(
        self, candidates: list[_Candidate], maps: list[_Normalized], team_a: Team, team_b: Team,
        recent_limit: int, *, empty_status: SliceStatus,
    ) -> H2HSlice:
        excluded = len(candidates) - len(maps)
        if not maps:
            return self._empty_slice(empty_status, len(candidates), excluded)
        count = len(maps)
        wins_a = sum(item.winner_team_id == team_a.id for item in maps)
        rounds_a, rounds_b = sum(item.score_a for item in maps), sum(item.score_b for item in maps)
        effective = sum(item.weight for item in maps)
        weighted_map_a = sum(item.weight * (item.winner_team_id == team_a.id) for item in maps) / effective * 100
        weighted_round_a = sum(item.weight * item.score_a for item in maps) / sum(item.weight * (item.score_a + item.score_b) for item in maps) * 100
        performance_a = weighted_map_a * .65 + weighted_round_a * .35
        last_date = max(item.match_date for item in maps)
        sample_score = min(100.0, effective / 8 * 100)
        freshness = self.freshness_score(last_date, self._today)
        confidence = max(0.0, min(100.0, sample_score * .8 + freshness * .2))
        rating_a = max(0.0, min(100.0, 50 + (performance_a - 50) * confidence / 100))
        rating_b = 100 - rating_a
        diff, level = abs(rating_a - rating_b), self.advantage_level(abs(rating_a - rating_b))
        advantage = team_a if rating_a > rating_b else team_b
        raw_map_a = wins_a / count * 100
        raw_round_a = rounds_a / (rounds_a + rounds_b) * 100
        warnings: list[str] = []
        label = self.sample_label(count)
        if label == "very_small": warnings.append("very_small_sample")
        elif label == "small": warnings.append("small_sample")
        age = max(0, (self._today - last_date).days)
        if age > 365: warnings.append("very_stale_history")
        elif age > 180: warnings.append("stale_history")
        if any(item.roster_a_id is None or item.roster_b_id is None for item in maps): warnings.append("partial_roster_data")
        if excluded: warnings.append("excluded_invalid_maps")
        if any(item.future_date for item in maps): warnings.append("future_match_date")
        factors = [
            H2HFactor("map_results", weighted_map_a, .65, f"{team_a.name} выиграла {wins_a} из {count} очных карт; взвешенный winrate {weighted_map_a:.2f}%."),
            H2HFactor("round_results", weighted_round_a, .35, f"Взвешенная доля раундов {team_a.name}: {weighted_round_a:.2f}%."),
            H2HFactor("recency", freshness, .20, f"Свежесть последней очной карты: {freshness:.2f}/100."),
            H2HFactor("sample_size", sample_score, .80, f"Эффективный размер выборки: {effective:.2f} карты."),
            H2HFactor("confidence_adjustment", confidence, 1.0, f"Надёжность {confidence:.2f}/100 стягивает H2H-рейтинг к 50."),
        ]
        team_metrics_a = H2HTeamMetrics(wins_a, raw_map_a, weighted_map_a, rounds_a, raw_round_a, weighted_round_a, performance_a, rating_a)
        team_metrics_b = H2HTeamMetrics(count - wins_a, 100 - raw_map_a, 100 - weighted_map_a, rounds_b, 100 - raw_round_a, 100 - weighted_round_a, 100 - performance_a, rating_b)
        return H2HSlice(
            "partial_data" if excluded else "available", len(candidates), count, excluded, count,
            effective, label, confidence, self.confidence_level(confidence, count),
            min(item.match_date for item in maps), last_date, team_metrics_a, team_metrics_b,
            None if level == "none" else advantage.id, None if level == "none" else advantage.name,
            diff, level, self._map_breakdowns(maps), [self._recent(item) for item in maps[:recent_limit]],
            factors, warnings,
        )

    @staticmethod
    def _empty_slice(status: SliceStatus, candidates: int = 0, excluded: int = 0) -> H2HSlice:
        metrics = H2HTeamMetrics(0, None, None, 0, None, None, None, None)
        warnings = ["excluded_invalid_maps"] if excluded else []
        return H2HSlice(status, candidates, 0, excluded, 0, 0.0, "no_data", 0.0, "no_data", None, None,
                        metrics, metrics, None, None, None, "none", [], [], [], warnings)

    @staticmethod
    def _recent(item: _Normalized) -> H2HRecentMap:
        return H2HRecentMap(item.demo_file_id, item.match_date, item.tournament, item.map_name,
                            item.score_a, item.score_b, item.winner_team_id, item.overtime,
                            item.roster_a_id, item.roster_b_id, item.weight)

    @staticmethod
    def _map_breakdowns(maps: list[_Normalized]) -> list[H2HMapBreakdown]:
        grouped: dict[str, list[_Normalized]] = defaultdict(list)
        for item in maps: grouped[item.map_name].append(item)
        result = []
        for name, items in grouped.items():
            count = len(items); wins_a = sum(item.score_a > item.score_b for item in items)
            rounds_a, rounds_b = sum(item.score_a for item in items), sum(item.score_b for item in items)
            result.append(H2HMapBreakdown(name, count, wins_a, count - wins_a, wins_a / count * 100,
                (count - wins_a) / count * 100, rounds_a, rounds_b, rounds_a / (rounds_a + rounds_b) * 100,
                rounds_b / (rounds_a + rounds_b) * 100, min(i.match_date for i in items),
                max(i.match_date for i in items), sum(i.overtime for i in items)))
        return sorted(result, key=lambda item: (-item.maps_played, item.map_name.lower()))

    async def _current_rosters_available(self, team_a: Team, team_b: Team) -> bool:
        if team_a.current_roster_id is None or team_b.current_roster_id is None: return False
        rosters = [await self._session.get(TeamRoster, team_a.current_roster_id), await self._session.get(TeamRoster, team_b.current_roster_id)]
        return all(
            roster is not None and roster.resolution_status == "complete" and roster.team_id == team.id
            for roster, team in zip(rosters, (team_a, team_b), strict=True)
        )

    async def _series_counts(self, team_a: Team, team_b: Team, *, current_rosters: bool) -> tuple[int, int]:
        matches = list((await self._session.execute(select(Match).where(
            Match.resolution_status == "resolved", Match.status == "completed",
            or_(
                (Match.team_a_id == team_a.id) & (Match.team_b_id == team_b.id),
                (Match.team_a_id == team_b.id) & (Match.team_b_id == team_a.id),
            ),
        ))).scalars().all())
        if current_rosters:
            if team_a.current_roster_id is None or team_b.current_roster_id is None: return 0, 0
            match_service = MatchService(self._session)
            matches = [match for match in matches
                       if await match_service._match_uses_roster(match.id, team_a.id, team_a.current_roster_id)
                       and await match_service._match_uses_roster(match.id, team_b.id, team_b.current_roster_id)]
        return sum(match.winner_team_id == team_a.id for match in matches), sum(match.winner_team_id == team_b.id for match in matches)

    async def _members(self, roster_id: int | None) -> list[tuple[TeamRosterMember, Player | None]]:
        if roster_id is None: return []
        return list((await self._session.execute(select(TeamRosterMember, Player).outerjoin(Player, Player.id == TeamRosterMember.player_id)
            .where(TeamRosterMember.roster_id == roster_id).order_by(TeamRosterMember.id))).all())

    async def _player_context(self, team: Team, opponent: Team, history_ids: list[int]) -> H2HPlayerContext:
        members = await self._members(team.current_roster_id)
        if not members: return H2HPlayerContext(team.current_roster_id, 0, 0, 0, None, None, "unavailable", [])
        player_ids = [m.player_id for m, _ in members if m.player_id is not None]
        counts: dict[int, int] = defaultdict(int)
        if player_ids:
            rows = (await self._session.execute(select(DemoPlayerStat.player_id, DemoPlayerStat.demo_file_id).where(
                DemoPlayerStat.player_id.in_(player_ids), DemoPlayerStat.demo_team_id == team.id,
                DemoPlayerStat.opponent_team_id == opponent.id,
                DemoPlayerStat.demo_file_id.in_(history_ids) if history_ids else False,
            ))).all()
            for player_id, demo_id in set(rows): counts[player_id] += 1
        incomplete = len(player_ids) != len(members)
        if history_ids:
            linked_counts = (await self._session.execute(select(DemoPlayerStat.demo_file_id, DemoPlayerStat.player_id).where(
                DemoPlayerStat.demo_file_id.in_(history_ids), DemoPlayerStat.demo_team_id == team.id,
                DemoPlayerStat.opponent_team_id == opponent.id))).all()
            by_demo: dict[int, set[int]] = defaultdict(set)
            for demo_id, player_id in linked_counts:
                if player_id is not None: by_demo[demo_id].add(player_id)
                else: incomplete = True
            incomplete = incomplete or any(len(by_demo[demo_id]) < 5 for demo_id in history_ids)
        players = [H2HPlayerExperience(m.player_id, p.nickname if p else m.player_name_snapshot,
                   counts.get(m.player_id, 0) if m.player_id else 0, bool(m.player_id and counts.get(m.player_id, 0))) for m, p in members]
        experienced = sum(p.has_h2h_experience for p in players); total = len(players)
        return H2HPlayerContext(team.current_roster_id, total, experienced, total - experienced,
            experienced / total * 100 if total else None, sum(p.maps_against_opponent for p in players) / total if total else None,
            "partial" if incomplete else "available", players)

    async def _overlap(self, current_roster_id: int | None, latest_roster_id: int | None) -> H2HLatestRosterOverlap:
        current, latest = await self._members(current_roster_id), await self._members(latest_roster_id)
        def convert(row: tuple[TeamRosterMember, Player | None]) -> H2HPlayerExperience:
            member, player = row
            return H2HPlayerExperience(member.player_id, player.nickname if player else member.player_name_snapshot, 0, False)
        if not current or not latest or len(latest) != 5 or any(m.player_id is None for m, _ in latest):
            return H2HLatestRosterOverlap("unavailable", latest_roster_id, current_roster_id, len(latest), len(current), 0, 0, [], [], [])
        current_ids, latest_ids = {m.player_id for m, _ in current}, {m.player_id for m, _ in latest}
        retained = current_ids & latest_ids
        return H2HLatestRosterOverlap("available", latest_roster_id, current_roster_id, len(latest), len(current), len(retained),
            len(current_ids - latest_ids), [convert(r) for r in current if r[0].player_id in retained],
            [convert(r) for r in current if r[0].player_id not in latest_ids], [convert(r) for r in latest if r[0].player_id not in current_ids])

    async def _roster_context(self, team_a: Team, team_b: Team, history: list[_Normalized], current_maps: int) -> H2HRosterContext:
        ids = [item.demo_file_id for item in history]
        exp_a, exp_b = await self._player_context(team_a, team_b, ids), await self._player_context(team_b, team_a, ids)
        latest = history[0] if history else None
        overlap_a = await self._overlap(team_a.current_roster_id, latest.roster_a_id if latest else None)
        overlap_b = await self._overlap(team_b.current_roster_id, latest.roster_b_id if latest else None)
        if current_maps >= 3: applicability = "direct"
        elif current_maps >= 1: applicability = "high"
        elif overlap_a.status != "available" or overlap_b.status != "available": applicability = "unknown"
        elif overlap_a.retained_players_count == 5 and overlap_b.retained_players_count == 5: applicability = "high"
        elif overlap_a.retained_players_count >= 4 and overlap_b.retained_players_count >= 4: applicability = "medium"
        else: applicability = "low"
        return H2HRosterContext(H2HRosterTeamContext(exp_a, overlap_a), H2HRosterTeamContext(exp_b, overlap_b), applicability)

    @staticmethod
    def _insights(team_a: Team, team_b: Team, org: H2HSlice, current: H2HSlice, context: H2HRosterContext) -> list[H2HInsight]:
        result: list[H2HInsight] = []
        if org.maps_played < 3: result.append(H2HInsight("insufficient_organization_history", "История организаций основана на небольшой выборке очных карт."))
        if current.maps_played == 0: result.append(H2HInsight("current_rosters_never_met", "Текущие составы ещё не встречались на сохранённых картах."))
        elif current.maps_played < 3: result.append(H2HInsight("insufficient_current_roster_history", "История текущих составов пока недостаточна для высокой надёжности."))
        if org.advantage_team_id is not None:
            if current.maps_played == 0:
                result.append(H2HInsight("organization_advantage_not_confirmed", f"Исторически преимущество в очных картах у {org.advantage_team_name}, но текущие составы ещё не встречались."))
            elif current.advantage_team_id == org.advantage_team_id:
                result.append(H2HInsight("organization_advantage_confirmed", f"Преимущество {org.advantage_team_name} в истории организаций подтверждается очными картами текущих составов."))
            elif current.advantage_team_id is not None:
                result.append(H2HInsight("current_rosters_reverse_history", f"История организаций в пользу {org.advantage_team_name}, однако нынешние пятёрки показывают обратный результат."))
        if context.history_applicability == "low": result.append(H2HInsight("historical_data_low_applicability", "Составы заметно изменились, поэтому исторический H2H применим к нынешним пятёркам лишь ограниченно."))
        for team, ctx, opponent in ((team_a, context.team_a, team_b), (team_b, context.team_b, team_a)):
            exp = ctx.experience
            if exp.current_players_count:
                result.append(H2HInsight("player_h2h_experience", f"{exp.players_with_h2h_experience_count} из {exp.current_players_count} текущих игроков {team.name} имеют подтверждённый опыт очных карт против {opponent.name}."))
        return result

    @staticmethod
    def _team(team: Team) -> H2HTeam:
        return H2HTeam(team.id, team.name, team.current_roster_id)
