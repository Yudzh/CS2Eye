from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.demo import DemoBombRoundStat, DemoParseRun, DemoRoundStat


@dataclass(frozen=True)
class TeamMapRecentMatch:
    parse_run_id: UUID
    tournament_name: str | None
    match_date: date | None
    map_name: str | None
    team_name: str
    opponent_name: str | None
    rounds_won: int
    rounds_lost: int
    won: bool


@dataclass(frozen=True)
class TeamMapStatsItem:
    team_name: str
    map_name: str | None

    total_matches_on_map: int
    wins_on_map: int
    losses_on_map: int
    win_rate_on_map: float

    rounds_won_total: int
    rounds_lost_total: int
    avg_round_diff: float
    avg_rounds_won_per_map: float
    avg_rounds_lost_per_map: float

    win_rate_last_5_maps: float
    win_rate_last_10_maps: float
    win_rate_last_20_maps: float
    current_win_streak_on_map: int
    current_lose_streak_on_map: int
    last_played_date_on_map: date | None
    days_since_last_played_map: int | None

    win_rate_30_days: float
    win_rate_60_days: float
    win_rate_90_days: float
    matches_30_days: int
    matches_60_days: int
    matches_90_days: int

    ct_rounds_played: int
    ct_rounds_won: int
    ct_win_rate: float
    t_rounds_played: int
    t_rounds_won: int
    t_win_rate: float

    avg_bomb_plants_per_map: float
    avg_bomb_explosions_per_map: float
    avg_bomb_defuses_per_map: float

    map_sample_size_score: float
    recent_form_score: float
    map_strength_score: float
    map_confidence_score: float
    map_confidence_level: str
    map_tier: str
    is_strong_map: bool
    is_weak_map: bool
    is_permaban_map: bool

    recent_matches: list[TeamMapRecentMatch]


@dataclass(frozen=True)
class TeamMapStatsResult:
    team_name: str | None
    map_name: str | None
    items: list[TeamMapStatsItem]

@dataclass(frozen=True)
class TeamMapMatchupTeamStats:
    team_name: str
    map_name: str | None

    total_matches_on_map: int
    win_rate_on_map: float

    ct_win_rate: float
    t_win_rate: float

    avg_bomb_plants_per_map: float
    avg_bomb_explosions_per_map: float
    avg_bomb_defuses_per_map: float

    map_strength_score: float
    map_confidence_score: float
    map_confidence_level: str
    map_tier: str


@dataclass(frozen=True)
class TeamMapMatchupItem:
    map_name: str | None

    team_a: TeamMapMatchupTeamStats
    team_b: TeamMapMatchupTeamStats

    advantage_team_name: str | None
    advantage_score: float
    matchup_confidence_level: str
    recommendation: str


@dataclass(frozen=True)
class TeamMapMatchupResult:
    team_a_name: str
    team_b_name: str
    map_name: str | None

    items: list[TeamMapMatchupItem]


@dataclass
class _SingleMatchTeamStats:
    parse_run_id: UUID
    tournament_name: str | None
    match_date: date | None
    map_name: str | None
    team_name: str
    opponent_name: str | None

    rounds_won: int
    rounds_lost: int

    ct_rounds_played: int
    ct_rounds_won: int
    t_rounds_played: int
    t_rounds_won: int

    bomb_plants: int
    bomb_explosions: int
    bomb_defuses: int

    @property
    def won(self) -> bool:
        return self.rounds_won > self.rounds_lost


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None

    value = value.strip()

    return value or None


def _same_team(left: str | None, right: str | None) -> bool:
    if left is None or right is None:
        return False

    return left.strip().casefold() == right.strip().casefold()


def _rate(wins: int, total: int) -> float:
    if total <= 0:
        return 0.0

    return round(wins / total * 100, 2)


def _avg(value: int | float, total: int) -> float:
    if total <= 0:
        return 0.0

    return round(value / total, 2)


def _get_winner_team_name(round_stat: DemoRoundStat) -> str | None:
    if round_stat.winner_team_name:
        return round_stat.winner_team_name

    if round_stat.winner_side == "CT":
        return round_stat.ct_team_name

    if round_stat.winner_side == "T":
        return round_stat.t_team_name

    return None


def _get_opponent_name(
        *,
        parse_run: DemoParseRun,
        team_name: str,
) -> str | None:
    if _same_team(parse_run.team_a_name, team_name):
        return parse_run.team_b_name

    if _same_team(parse_run.team_b_name, team_name):
        return parse_run.team_a_name

    return None


def _get_team_names_for_parse_run(
        *,
        parse_run: DemoParseRun,
        requested_team_name: str | None,
) -> list[str]:
    available_team_names = [
        team_name
        for team_name in [parse_run.team_a_name, parse_run.team_b_name]
        if team_name is not None
    ]

    if requested_team_name is None:
        return available_team_names

    return [
        team_name
        for team_name in available_team_names
        if _same_team(team_name, requested_team_name)
    ]


def _count_period_matches(
        *,
        matches: list[_SingleMatchTeamStats],
        days: int,
        today: date,
) -> tuple[int, int]:
    min_date = today - timedelta(days=days)

    period_matches = [
        match
        for match in matches
        if match.match_date is not None and match.match_date >= min_date
    ]

    period_wins = sum(1 for match in period_matches if match.won)

    return len(period_matches), period_wins


def _current_streak(matches: list[_SingleMatchTeamStats]) -> tuple[int, int]:
    if not matches:
        return 0, 0

    latest_result_is_win = matches[0].won

    streak = 0

    for match in matches:
        if match.won != latest_result_is_win:
            break

        streak += 1

    if latest_result_is_win:
        return streak, 0

    return 0, streak


def _get_map_tier(
        *,
        total_matches: int,
        map_strength_score: float,
) -> str:
    if total_matches <= 0:
        return "permaban"

    if total_matches < 3:
        return "floating"

    if map_strength_score >= 65:
        return "strong"

    if map_strength_score <= 40:
        return "weak"

    return "average"


def _get_freshness_score(
        *,
        days_since_last_played: int | None,
) -> float:
    """
    Оценивает свежесть статистики карты.

    100 = команда недавно играла карту
    0 = нет данных по дате
    """

    if days_since_last_played is None:
        return 0.0

    if days_since_last_played <= 14:
        return 100.0

    if days_since_last_played <= 30:
        return 85.0

    if days_since_last_played <= 60:
        return 70.0

    if days_since_last_played <= 90:
        return 55.0

    if days_since_last_played <= 180:
        return 35.0

    return 15.0


def _get_map_confidence_score(
        *,
        sample_size_score: float,
        days_since_last_played: int | None,
) -> float:
    """
    Confidence показывает не силу карты, а доверие к статистике.

    Пока учитываем только:
    - размер выборки;
    - свежесть последнего матча.

    Позже сюда можно добавить:
    - силу соперников;
    - LAN/online;
    - стабильность состава;
    - stage турнира.
    """

    freshness_score = _get_freshness_score(
        days_since_last_played=days_since_last_played,
    )

    return round(
        sample_size_score * 0.7
        + freshness_score * 0.3,
        2,
    )


def _get_map_confidence_level(
        *,
        total_matches: int,
        map_confidence_score: float,
) -> str:
    if total_matches <= 0:
        return "not_enough_data"

    if total_matches < 3:
        return "low"

    if map_confidence_score >= 75:
        return "high"

    if map_confidence_score >= 50:
        return "medium"

    return "low"


def _build_team_match_stats(
        *,
        parse_run: DemoParseRun,
        team_name: str,
        round_stats: list[DemoRoundStat],
        bomb_stats: list[DemoBombRoundStat],
) -> _SingleMatchTeamStats:
    opponent_name = _get_opponent_name(
        parse_run=parse_run,
        team_name=team_name,
    )

    rounds_won = 0
    rounds_lost = 0

    ct_rounds_played = 0
    ct_rounds_won = 0
    t_rounds_played = 0
    t_rounds_won = 0

    team_t_round_numbers: set[int] = set()
    team_ct_round_numbers: set[int] = set()

    for round_stat in round_stats:
        winner_team_name = _get_winner_team_name(round_stat)

        if _same_team(round_stat.ct_team_name, team_name):
            ct_rounds_played += 1
            team_ct_round_numbers.add(round_stat.round_number)

            if _same_team(winner_team_name, team_name):
                ct_rounds_won += 1

        if _same_team(round_stat.t_team_name, team_name):
            t_rounds_played += 1
            team_t_round_numbers.add(round_stat.round_number)

            if _same_team(winner_team_name, team_name):
                t_rounds_won += 1

        if _same_team(winner_team_name, team_name):
            rounds_won += 1
        elif _same_team(winner_team_name, opponent_name):
            rounds_lost += 1

    bomb_plants = 0
    bomb_explosions = 0
    bomb_defuses = 0

    for bomb_stat in bomb_stats:
        team_was_t_in_round = bomb_stat.round_number in team_t_round_numbers
        team_was_ct_in_round = bomb_stat.round_number in team_ct_round_numbers

        if (
                _same_team(bomb_stat.planter_team_name, team_name)
                or (
                    bomb_stat.planter_team_name is None
                    and team_was_t_in_round
                )
        ):
            bomb_plants += 1

        if bomb_stat.outcome == "exploded" and team_was_t_in_round:
            bomb_explosions += 1

        if (
                bomb_stat.outcome == "defused"
                and (
                    _same_team(bomb_stat.defuser_team_name, team_name)
                    or team_was_ct_in_round
                )
        ):
            bomb_defuses += 1

    return _SingleMatchTeamStats(
        parse_run_id=parse_run.id,
        tournament_name=parse_run.tournament_name,
        match_date=parse_run.match_date,
        map_name=parse_run.map_name,
        team_name=team_name,
        opponent_name=opponent_name,
        rounds_won=rounds_won,
        rounds_lost=rounds_lost,
        ct_rounds_played=ct_rounds_played,
        ct_rounds_won=ct_rounds_won,
        t_rounds_played=t_rounds_played,
        t_rounds_won=t_rounds_won,
        bomb_plants=bomb_plants,
        bomb_explosions=bomb_explosions,
        bomb_defuses=bomb_defuses,
    )


def _build_team_map_stats_item(
        *,
        team_name: str,
        map_name: str | None,
        matches: list[_SingleMatchTeamStats],
) -> TeamMapStatsItem:
    matches = sorted(
        matches,
        key=lambda match: (
            match.match_date or date.min,
            str(match.parse_run_id),
        ),
        reverse=True,
    )

    total_matches = len(matches)

    wins = sum(1 for match in matches if match.won)
    losses = total_matches - wins

    rounds_won_total = sum(match.rounds_won for match in matches)
    rounds_lost_total = sum(match.rounds_lost for match in matches)

    ct_rounds_played = sum(match.ct_rounds_played for match in matches)
    ct_rounds_won = sum(match.ct_rounds_won for match in matches)

    t_rounds_played = sum(match.t_rounds_played for match in matches)
    t_rounds_won = sum(match.t_rounds_won for match in matches)

    bomb_plants = sum(match.bomb_plants for match in matches)
    bomb_explosions = sum(match.bomb_explosions for match in matches)
    bomb_defuses = sum(match.bomb_defuses for match in matches)

    last_5_matches = matches[:5]
    last_10_matches = matches[:10]
    last_20_matches = matches[:20]

    win_streak, lose_streak = _current_streak(matches)

    today = date.today()

    matches_30_days, wins_30_days = _count_period_matches(
        matches=matches,
        days=30,
        today=today,
    )
    matches_60_days, wins_60_days = _count_period_matches(
        matches=matches,
        days=60,
        today=today,
    )
    matches_90_days, wins_90_days = _count_period_matches(
        matches=matches,
        days=90,
        today=today,
    )

    last_played_date = matches[0].match_date if matches else None

    days_since_last_played = (
        None
        if last_played_date is None
        else (today - last_played_date).days
    )

    win_rate = _rate(wins, total_matches)

    sample_size_score = round(min(total_matches / 10, 1) * 100, 2)

    recent_form_score = _rate(
        sum(1 for match in last_10_matches if match.won),
        len(last_10_matches),
    )

    map_strength_score = round(
        win_rate * 0.6
        + recent_form_score * 0.3
        + sample_size_score * 0.1,
        2,
    )

    map_confidence_score = _get_map_confidence_score(
        sample_size_score=sample_size_score,
        days_since_last_played=days_since_last_played,
    )

    map_confidence_level = _get_map_confidence_level(
        total_matches=total_matches,
        map_confidence_score=map_confidence_score,
    )

    map_tier = _get_map_tier(
        total_matches=total_matches,
        map_strength_score=map_strength_score,
    )

    return TeamMapStatsItem(
        team_name=team_name,
        map_name=map_name,

        total_matches_on_map=total_matches,
        wins_on_map=wins,
        losses_on_map=losses,
        win_rate_on_map=win_rate,

        rounds_won_total=rounds_won_total,
        rounds_lost_total=rounds_lost_total,
        avg_round_diff=_avg(
            rounds_won_total - rounds_lost_total,
            total_matches,
        ),
        avg_rounds_won_per_map=_avg(rounds_won_total, total_matches),
        avg_rounds_lost_per_map=_avg(rounds_lost_total, total_matches),

        win_rate_last_5_maps=_rate(
            sum(1 for match in last_5_matches if match.won),
            len(last_5_matches),
        ),
        win_rate_last_10_maps=_rate(
            sum(1 for match in last_10_matches if match.won),
            len(last_10_matches),
        ),
        win_rate_last_20_maps=_rate(
            sum(1 for match in last_20_matches if match.won),
            len(last_20_matches),
        ),
        current_win_streak_on_map=win_streak,
        current_lose_streak_on_map=lose_streak,
        last_played_date_on_map=last_played_date,
        days_since_last_played_map=days_since_last_played,

        win_rate_30_days=_rate(wins_30_days, matches_30_days),
        win_rate_60_days=_rate(wins_60_days, matches_60_days),
        win_rate_90_days=_rate(wins_90_days, matches_90_days),
        matches_30_days=matches_30_days,
        matches_60_days=matches_60_days,
        matches_90_days=matches_90_days,

        ct_rounds_played=ct_rounds_played,
        ct_rounds_won=ct_rounds_won,
        ct_win_rate=_rate(ct_rounds_won, ct_rounds_played),

        t_rounds_played=t_rounds_played,
        t_rounds_won=t_rounds_won,
        t_win_rate=_rate(t_rounds_won, t_rounds_played),

        avg_bomb_plants_per_map=_avg(bomb_plants, total_matches),
        avg_bomb_explosions_per_map=_avg(bomb_explosions, total_matches),
        avg_bomb_defuses_per_map=_avg(bomb_defuses, total_matches),

        map_sample_size_score=sample_size_score,
        recent_form_score=recent_form_score,
        map_strength_score=map_strength_score,
        map_confidence_score=map_confidence_score,
        map_confidence_level=map_confidence_level,
        map_tier=map_tier,
        is_strong_map=map_tier == "strong",
        is_weak_map=map_tier == "weak",
        is_permaban_map=map_tier == "permaban",

        recent_matches=[
            TeamMapRecentMatch(
                parse_run_id=match.parse_run_id,
                tournament_name=match.tournament_name,
                match_date=match.match_date,
                map_name=match.map_name,
                team_name=match.team_name,
                opponent_name=match.opponent_name,
                rounds_won=match.rounds_won,
                rounds_lost=match.rounds_lost,
                won=match.won,
            )
            for match in matches[:10]
        ],
    )


async def get_team_map_stats(
        *,
        session: AsyncSession,
        team_name: str | None = None,
        map_name: str | None = None,
) -> TeamMapStatsResult:
    normalized_team_name = _normalize_text(team_name)
    normalized_map_name = _normalize_text(map_name)

    filters = [
        DemoParseRun.status == "success",
    ]

    if normalized_map_name is not None:
        filters.append(DemoParseRun.map_name == normalized_map_name)

    if normalized_team_name is not None:
        filters.append(
            or_(
                DemoParseRun.team_a_name == normalized_team_name,
                DemoParseRun.team_b_name == normalized_team_name,
            )
        )

    parse_runs_result = await session.execute(
        select(DemoParseRun)
        .where(*filters)
        .order_by(
            DemoParseRun.match_date.desc().nullslast(),
            DemoParseRun.started_at.desc(),
        )
    )

    parse_runs = list(parse_runs_result.scalars().all())

    if not parse_runs:
        return TeamMapStatsResult(
            team_name=normalized_team_name,
            map_name=normalized_map_name,
            items=[],
        )

    parse_run_ids = [parse_run.id for parse_run in parse_runs]

    round_stats_result = await session.execute(
        select(DemoRoundStat)
        .where(DemoRoundStat.parse_run_id.in_(parse_run_ids))
        .order_by(DemoRoundStat.round_number.asc())
    )

    bomb_stats_result = await session.execute(
        select(DemoBombRoundStat)
        .where(DemoBombRoundStat.parse_run_id.in_(parse_run_ids))
        .order_by(DemoBombRoundStat.round_number.asc())
    )

    round_stats_by_parse_run_id: dict[UUID, list[DemoRoundStat]] = defaultdict(list)
    bomb_stats_by_parse_run_id: dict[UUID, list[DemoBombRoundStat]] = defaultdict(list)

    for round_stat in round_stats_result.scalars().all():
        round_stats_by_parse_run_id[round_stat.parse_run_id].append(round_stat)

    for bomb_stat in bomb_stats_result.scalars().all():
        bomb_stats_by_parse_run_id[bomb_stat.parse_run_id].append(bomb_stat)

    grouped_matches: dict[tuple[str, str | None], list[_SingleMatchTeamStats]] = defaultdict(list)

    for parse_run in parse_runs:
        team_names = _get_team_names_for_parse_run(
            parse_run=parse_run,
            requested_team_name=normalized_team_name,
        )

        for current_team_name in team_names:
            match_stats = _build_team_match_stats(
                parse_run=parse_run,
                team_name=current_team_name,
                round_stats=round_stats_by_parse_run_id[parse_run.id],
                bomb_stats=bomb_stats_by_parse_run_id[parse_run.id],
            )

            grouped_matches[
                (current_team_name, parse_run.map_name)
            ].append(match_stats)

    items = [
        _build_team_map_stats_item(
            team_name=current_team_name,
            map_name=current_map_name,
            matches=matches,
        )
        for (current_team_name, current_map_name), matches in grouped_matches.items()
    ]

    items.sort(
        key=lambda item: (
            item.team_name.casefold(),
            item.map_name or "",
            item.total_matches_on_map,
        )
    )

    return TeamMapStatsResult(
        team_name=normalized_team_name,
        map_name=normalized_map_name,
        items=items,
    )


def _build_empty_matchup_team_stats(
        *,
        team_name: str,
        map_name: str | None,
) -> TeamMapMatchupTeamStats:
    return TeamMapMatchupTeamStats(
        team_name=team_name,
        map_name=map_name,

        total_matches_on_map=0,
        win_rate_on_map=0.0,

        ct_win_rate=0.0,
        t_win_rate=0.0,

        avg_bomb_plants_per_map=0.0,
        avg_bomb_explosions_per_map=0.0,
        avg_bomb_defuses_per_map=0.0,

        map_strength_score=0.0,
        map_confidence_score=0.0,
        map_confidence_level="not_enough_data",
        map_tier="permaban",
    )


def _build_matchup_team_stats(
        *,
        team_name: str,
        map_name: str | None,
        item: TeamMapStatsItem | None,
) -> TeamMapMatchupTeamStats:
    if item is None:
        return _build_empty_matchup_team_stats(
            team_name=team_name,
            map_name=map_name,
        )

    return TeamMapMatchupTeamStats(
        team_name=item.team_name,
        map_name=item.map_name,

        total_matches_on_map=item.total_matches_on_map,
        win_rate_on_map=item.win_rate_on_map,

        ct_win_rate=item.ct_win_rate,
        t_win_rate=item.t_win_rate,

        avg_bomb_plants_per_map=item.avg_bomb_plants_per_map,
        avg_bomb_explosions_per_map=item.avg_bomb_explosions_per_map,
        avg_bomb_defuses_per_map=item.avg_bomb_defuses_per_map,

        map_strength_score=item.map_strength_score,
        map_confidence_score=item.map_confidence_score,
        map_confidence_level=item.map_confidence_level,
        map_tier=item.map_tier,
    )


def _get_matchup_confidence_level(
        *,
        team_a: TeamMapMatchupTeamStats,
        team_b: TeamMapMatchupTeamStats,
) -> str:
    if team_a.total_matches_on_map <= 0 and team_b.total_matches_on_map <= 0:
        return "not_enough_data"

    if team_a.total_matches_on_map <= 0 or team_b.total_matches_on_map <= 0:
        return "low"

    min_confidence_score = min(
        team_a.map_confidence_score,
        team_b.map_confidence_score,
    )

    if min_confidence_score >= 75:
        return "high"

    if min_confidence_score >= 50:
        return "medium"

    return "low"


def _get_matchup_recommendation(
        *,
        advantage_team_name: str | None,
        advantage_score: float,
        matchup_confidence_level: str,
) -> str:
    if advantage_team_name is None:
        return "not_enough_data"

    if matchup_confidence_level == "not_enough_data":
        return "not_enough_data"

    if matchup_confidence_level == "low":
        return "no_bet_low_confidence"

    if advantage_score < 8:
        return "no_clear_advantage"

    if advantage_score < 15:
        return "small_edge"

    if advantage_score < 25:
        return "map_advantage"

    return "strong_map_advantage"


def _build_matchup_item(
        *,
        map_name: str | None,
        team_a: TeamMapMatchupTeamStats,
        team_b: TeamMapMatchupTeamStats,
) -> TeamMapMatchupItem:
    advantage_score = round(
        abs(team_a.map_strength_score - team_b.map_strength_score),
        2,
    )

    if team_a.total_matches_on_map <= 0 and team_b.total_matches_on_map <= 0:
        advantage_team_name = None
    elif team_a.map_strength_score > team_b.map_strength_score:
        advantage_team_name = team_a.team_name
    elif team_b.map_strength_score > team_a.map_strength_score:
        advantage_team_name = team_b.team_name
    else:
        advantage_team_name = None

    matchup_confidence_level = _get_matchup_confidence_level(
        team_a=team_a,
        team_b=team_b,
    )

    recommendation = _get_matchup_recommendation(
        advantage_team_name=advantage_team_name,
        advantage_score=advantage_score,
        matchup_confidence_level=matchup_confidence_level,
    )

    return TeamMapMatchupItem(
        map_name=map_name,
        team_a=team_a,
        team_b=team_b,
        advantage_team_name=advantage_team_name,
        advantage_score=advantage_score,
        matchup_confidence_level=matchup_confidence_level,
        recommendation=recommendation,
    )


async def get_team_map_matchup(
        *,
        session: AsyncSession,
        team_a_name: str,
        team_b_name: str,
        map_name: str | None = None,
) -> TeamMapMatchupResult:
    normalized_team_a_name = _normalize_text(team_a_name)
    normalized_team_b_name = _normalize_text(team_b_name)
    normalized_map_name = _normalize_text(map_name)

    if normalized_team_a_name is None:
        raise ValueError("team_a_name is required")

    if normalized_team_b_name is None:
        raise ValueError("team_b_name is required")

    team_a_stats = await get_team_map_stats(
        session=session,
        team_name=normalized_team_a_name,
        map_name=normalized_map_name,
    )

    team_b_stats = await get_team_map_stats(
        session=session,
        team_name=normalized_team_b_name,
        map_name=normalized_map_name,
    )

    team_a_items_by_map = {
        item.map_name: item
        for item in team_a_stats.items
    }

    team_b_items_by_map = {
        item.map_name: item
        for item in team_b_stats.items
    }

    matchup_map_names = sorted(
        set(team_a_items_by_map.keys()) | set(team_b_items_by_map.keys()),
        key=lambda current_map_name: current_map_name or "",
    )

    items: list[TeamMapMatchupItem] = []

    for current_map_name in matchup_map_names:
        team_a_item = team_a_items_by_map.get(current_map_name)
        team_b_item = team_b_items_by_map.get(current_map_name)

        team_a_matchup_stats = _build_matchup_team_stats(
            team_name=normalized_team_a_name,
            map_name=current_map_name,
            item=team_a_item,
        )

        team_b_matchup_stats = _build_matchup_team_stats(
            team_name=normalized_team_b_name,
            map_name=current_map_name,
            item=team_b_item,
        )

        items.append(
            _build_matchup_item(
                map_name=current_map_name,
                team_a=team_a_matchup_stats,
                team_b=team_b_matchup_stats,
            )
        )

    items.sort(
        key=lambda item: (
            item.matchup_confidence_level != "high",
            item.matchup_confidence_level != "medium",
            -item.advantage_score,
            item.map_name or "",
        )
    )

    return TeamMapMatchupResult(
        team_a_name=normalized_team_a_name,
        team_b_name=normalized_team_b_name,
        map_name=normalized_map_name,
        items=items,
    )