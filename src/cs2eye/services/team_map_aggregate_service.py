from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.demo import (
    DemoMapResult, DemoParseRun, DemoTeamBombStat, DemoTeamCombatStat, DemoTeamEconomyStat,
    DemoTeamOpponentContext, DemoTeamSideStat, DemoTeamUtilityStat,
    DemoTeamRoster, TeamMapAggregate,
)
from cs2eye.models.demo_file import DemoFile
from cs2eye.services.demo_map_result_service import STANDARD_MAPS
from cs2eye.services.demo_utility_service import COUNT_KEYS, _base as utility_base, finalize as finalize_utility

RECENT_WINDOWS = (5, 10, 20)
RANK_GROUPS = ("top_15", "top_16_30", "outside_top_30", "tier_2_3", "unknown")


@dataclass(frozen=True)
class SourceMap:
    demo_file_id: int
    match_date: date | None
    won: bool
    went_to_overtime: bool
    side: DemoTeamSideStat
    bomb: DemoTeamBombStat | None
    opponent_context: DemoTeamOpponentContext | None
    economy: DemoTeamEconomyStat | None = None
    combat: DemoTeamCombatStat | None = None
    utility: DemoTeamUtilityStat | None = None


@dataclass
class TeamMapAggregateResult:
    team_id: int
    map_name: str
    source_maps_found: int
    aggregates_upserted: int
    aggregates_deleted: int
    warnings: list[str] = field(default_factory=list)


def calculate_sample_size_score(maps_played: int) -> float:
    points = ((0, 0), (1, 15), (2, 25), (3, 35), (5, 50), (8, 65),
              (10, 75), (15, 90), (20, 100))
    count = max(0, maps_played)
    if count >= 20:
        return 100.0
    for (left_x, left_y), (right_x, right_y) in zip(points, points[1:]):
        if left_x <= count <= right_x:
            return float(left_y + (count - left_x) * (right_y - left_y) / (right_x - left_x))
    return 0.0


def sample_size_label(maps_played: int) -> str:
    if maps_played == 0:
        return "no_data"
    if maps_played <= 2:
        return "very_low"
    if maps_played <= 4:
        return "low"
    if maps_played <= 9:
        return "medium"
    if maps_played <= 14:
        return "good"
    return "high"


def calculate_freshness_score(last_match_date: date | None, today: date) -> float:
    if last_match_date is None:
        return 0.0
    age = max(0, (today - last_match_date).days)
    if age <= 7: return 100.0
    if age <= 14: return 90.0
    if age <= 30: return 75.0
    if age <= 60: return 55.0
    if age <= 90: return 35.0
    if age <= 180: return 15.0
    return 5.0


def freshness_label(last_match_date: date | None, today: date) -> str:
    if last_match_date is None:
        return "unknown"
    age = max(0, (today - last_match_date).days)
    if age <= 14: return "fresh"
    if age <= 30: return "acceptable"
    if age <= 90: return "stale"
    return "very_stale"


def _rate(won: int, played: int) -> Decimal | None:
    return None if played == 0 else Decimal(won * 100) / Decimal(played)


def _aggregate_model(
    team_id: int, map_name: str, scope: str, scope_key: str,
    maps: list[SourceMap], today: date, *, window_size: int | None = None,
    opponent_rank_group: str | None = None,
    aggregation_level: str = "organization", roster_id: int | None = None,
) -> TeamMapAggregate:
    count = len(maps)
    wins = sum(item.won for item in maps)
    rounds_played = sum(item.side.total_rounds_played for item in maps)
    rounds_won = sum(item.side.total_rounds_won for item in maps)
    ct_played = sum(item.side.ct_rounds_played for item in maps)
    ct_won = sum(item.side.ct_rounds_won for item in maps)
    t_played = sum(item.side.t_rounds_played for item in maps)
    t_won = sum(item.side.t_rounds_won for item in maps)
    bomb_maps = [item.bomb for item in maps if item.bomb is not None]
    bomb_t_rounds = sum(item.t_rounds_played for item in bomb_maps)
    plants = sum(item.bomb_plants for item in bomb_maps)
    postplant_rounds = sum(item.postplant_rounds for item in bomb_maps)
    postplant_wins = sum(item.postplant_wins for item in bomb_maps)
    retake_opportunities = sum(item.retake_opportunities for item in bomb_maps)
    retake_wins = sum(item.retake_wins for item in bomb_maps)
    economy_maps = [item.economy for item in maps if item.economy is not None]
    economy_pairs = {
        "pistol": ("pistol_rounds_played", "pistol_rounds_won"),
        "first_pistol": ("first_pistol_opportunities", "first_pistol_wins"),
        "second_pistol": ("second_pistol_opportunities", "second_pistol_wins"),
        "both_pistols": ("both_pistols_opportunities", "both_pistols_wins"),
        "conversion": ("pistol_conversion_opportunities", "pistol_conversions"),
        "post_pistol_vs_force": ("post_pistol_vs_force_rounds", "post_pistol_vs_force_wins"),
        "second_round_comeback": ("second_round_comeback_opportunities", "second_round_comeback_wins"),
        "eco": ("eco_rounds", "eco_wins"), "force_buy": ("force_buy_rounds", "force_buy_wins"),
        "full_buy": ("full_buy_rounds", "full_buy_wins"), "anti_eco": ("anti_eco_rounds", "anti_eco_wins"),
        "full_buy_vs_full_buy": ("full_buy_vs_full_buy_rounds", "full_buy_vs_full_buy_wins"),
        "force_vs_full_buy": ("force_vs_full_buy_rounds", "force_vs_full_buy_wins"),
    }
    economy_data = {}
    for label, (rounds_field, wins_field) in economy_pairs.items():
        played = sum(getattr(item, rounds_field) for item in economy_maps)
        metric_wins = sum(getattr(item, wins_field) for item in economy_maps)
        economy_data[label] = {
            "rounds": played, "wins": metric_wins, "losses": played - metric_wins,
            "win_rate": float(_rate(metric_wins, played)) if played else None,
        }
    economy_data["save"] = {
        "rounds": sum(item.save_rounds for item in economy_maps),
        "players_saved": sum(item.players_saved for item in economy_maps),
        "status": "not_parsed",
    }
    combat_maps = [item.combat.combat_data for item in maps if item.combat is not None]
    def combat_sum(key: str) -> int:
        return sum(int(item.get(key, 0)) for item in combat_maps)
    def combat_rate(num: str, den: str) -> float | None:
        denominator = combat_sum(den)
        return float(_rate(combat_sum(num), denominator)) if denominator else None
    opening_attempts = combat_sum("opening_kills") + combat_sum("opening_deaths")
    combat_data = {
        "opening": {
            "kills": combat_sum("opening_kills"), "deaths": combat_sum("opening_deaths"),
            "success_rate": float(_rate(combat_sum("opening_kills"), opening_attempts)) if opening_attempts else None,
            "conversion_wins": combat_sum("opening_conversion_wins"),
            "conversion_losses": combat_sum("opening_conversion_losses"),
            "conversion_rate": combat_rate("opening_conversion_wins", "rounds_with_opening_kill"),
            "recovery_wins": combat_sum("opening_recovery_wins"),
            "recovery_losses": combat_sum("opening_recovery_losses"),
            "recovery_rate": combat_rate("opening_recovery_wins", "opening_death_rounds"),
            "ct_kills": combat_sum("ct_opening_kills"), "ct_deaths": combat_sum("ct_opening_deaths"),
            "t_kills": combat_sum("t_opening_kills"), "t_deaths": combat_sum("t_opening_deaths"),
            "ct_success_rate": float(_rate(combat_sum("ct_opening_kills"), combat_sum("ct_opening_kills") + combat_sum("ct_opening_deaths"))) if combat_sum("ct_opening_kills") + combat_sum("ct_opening_deaths") else None,
            "t_success_rate": float(_rate(combat_sum("t_opening_kills"), combat_sum("t_opening_kills") + combat_sum("t_opening_deaths"))) if combat_sum("t_opening_kills") + combat_sum("t_opening_deaths") else None,
        },
        "trade": {"trade_kills": combat_sum("trade_kills"), "deaths_traded": combat_sum("deaths_traded"),
                  "eligible_team_deaths": combat_sum("eligible_team_deaths"),
                  "trade_rate": combat_rate("deaths_traded", "eligible_team_deaths")},
        "clutch": {"opportunities": combat_sum("clutch_opportunities"), "wins": combat_sum("clutch_wins"),
                   "win_rate": combat_rate("clutch_wins", "clutch_opportunities"),
                   "clutches_lost_to_opponent": combat_sum("clutches_lost_to_opponent"),
                   "breakdown": {f"1v{x}": {"attempts": combat_sum(f"clutch_1v{x}_attempts"), "wins": combat_sum(f"clutch_1v{x}_wins")} for x in range(1, 6)}},
    } if combat_maps else None
    utility_maps = [item.utility.utility_data for item in maps if item.utility is not None]
    utility_data = None
    if utility_maps:
        utility_data = utility_base(sum(int(item.get("rounds_played", 0)) for item in utility_maps))
        for item in utility_maps:
            for key in COUNT_KEYS: utility_data[key] += int(item.get(key, 0))
            utility_data["enemy_flash_duration"] += float(item.get("enemy_flash_duration", 0))
            utility_data["teammate_flash_duration"] += float(item.get("teammate_flash_duration", 0))
            for side_key in ("ct", "t"):
                utility_data[side_key]["rounds_played"] += int(item.get(side_key, {}).get("rounds_played", 0))
                for key in COUNT_KEYS: utility_data[side_key][key] += int(item.get(side_key, {}).get(key, 0))
        utility_data = finalize_utility(utility_data)
    dated = [item.match_date for item in maps if item.match_date is not None]
    first_date, last_date = (min(dated), max(dated)) if dated else (None, None)
    return TeamMapAggregate(
        team_id=team_id, map_name=map_name, scope=scope, scope_key=scope_key,
        aggregation_level=aggregation_level, roster_id=roster_id,
        window_size=window_size, opponent_rank_group=opponent_rank_group,
        maps_played=count, maps_won=wins, maps_lost=count - wins,
        map_win_rate=_rate(wins, count), rounds_played=rounds_played,
        rounds_won=rounds_won, rounds_lost=rounds_played - rounds_won,
        round_win_rate=_rate(rounds_won, rounds_played),
        ct_rounds_played=ct_played, ct_rounds_won=ct_won,
        ct_rounds_lost=ct_played - ct_won, ct_win_rate=_rate(ct_won, ct_played),
        t_rounds_played=t_played, t_rounds_won=t_won,
        t_rounds_lost=t_played - t_won, t_win_rate=_rate(t_won, t_played),
        bomb_t_rounds_played=bomb_t_rounds, bomb_plants=plants,
        plant_rate=_rate(plants, bomb_t_rounds),
        postplant_rounds=postplant_rounds, postplant_wins=postplant_wins,
        postplant_losses=postplant_rounds-postplant_wins,
        postplant_win_rate=_rate(postplant_wins, postplant_rounds),
        retake_opportunities=retake_opportunities, retake_wins=retake_wins,
        retake_losses=retake_opportunities-retake_wins,
        retake_win_rate=_rate(retake_wins, retake_opportunities),
        bomb_explosions=sum(item.bomb_explosions for item in bomb_maps),
        bomb_defuses=sum(item.bomb_defuses for item in bomb_maps),
        economy_data=economy_data,
        combat_data=combat_data,
        utility_data=utility_data,
        overtime_maps=sum(item.went_to_overtime for item in maps),
        overtime_rounds_played=sum(item.side.overtime_rounds_played for item in maps),
        overtime_rounds_won=sum(item.side.overtime_rounds_won for item in maps),
        first_match_date=first_date, last_match_date=last_date,
        sample_size_score=Decimal(str(calculate_sample_size_score(count))),
        freshness_score=Decimal(str(calculate_freshness_score(last_date, today))),
        calculated_at=datetime.now(UTC),
    )


async def _source_maps(session: AsyncSession, team_id: int, map_name: str,
                       roster_id: int | None = None) -> list[SourceMap]:
    query = (
        select(DemoFile, DemoMapResult, DemoTeamSideStat, DemoTeamBombStat, DemoTeamEconomyStat, DemoTeamCombatStat, DemoTeamUtilityStat, DemoTeamOpponentContext)
        .join(DemoMapResult, DemoMapResult.demo_file_id == DemoFile.id)
        .join(DemoParseRun, DemoParseRun.demo_file_id == DemoFile.id)
        .join(DemoTeamSideStat, and_(
            DemoTeamSideStat.demo_file_id == DemoFile.id,
            DemoTeamSideStat.team_id == team_id,
        ))
        .outerjoin(DemoTeamBombStat, and_(
            DemoTeamBombStat.demo_file_id == DemoFile.id,
            DemoTeamBombStat.team_id == team_id,
            DemoMapResult.bomb_data_status == "complete",
        ))
        .outerjoin(DemoTeamEconomyStat, and_(
            DemoTeamEconomyStat.demo_file_id == DemoFile.id,
            DemoTeamEconomyStat.team_id == team_id,
            DemoMapResult.economy_data_status == "complete",
        ))
        .outerjoin(DemoTeamCombatStat, and_(
            DemoTeamCombatStat.demo_file_id == DemoFile.id,
            DemoTeamCombatStat.team_id == team_id,
            DemoMapResult.combat_data_status == "complete",
        ))
        .outerjoin(DemoTeamUtilityStat, and_(
            DemoTeamUtilityStat.demo_file_id == DemoFile.id,
            DemoTeamUtilityStat.team_id == team_id,
            DemoMapResult.utility_data_status == "complete",
        ))
        .outerjoin(DemoTeamOpponentContext, and_(
            DemoTeamOpponentContext.demo_file_id == DemoFile.id,
            DemoTeamOpponentContext.team_id == team_id,
        ))
        .where(
            DemoParseRun.status == "success", DemoMapResult.map_name == map_name,
            DemoMapResult.metadata_status.in_(("complete", "needs_review")),
            DemoMapResult.round_data_status == "complete",
            DemoMapResult.team_a_score.is_not(None),
            DemoMapResult.team_b_score.is_not(None),
            or_(DemoMapResult.team_a_id == team_id, DemoMapResult.team_b_id == team_id),
        ))
    if roster_id is not None:
        query = query.join(DemoTeamRoster, and_(
            DemoTeamRoster.demo_file_id == DemoFile.id,
            DemoTeamRoster.team_id == team_id,
            DemoTeamRoster.roster_id == roster_id,
            DemoTeamRoster.resolution_status == "complete",
        ))
    rows = (await session.execute(query)).all()
    sources = []
    for demo, result, side, bomb, economy, combat, utility, context in rows:
        if result.map_name not in STANDARD_MAPS:
            continue
        is_a = result.team_a_id == team_id
        score_for = result.team_a_score if is_a else result.team_b_score
        score_against = result.team_b_score if is_a else result.team_a_score
        if score_for is None or score_against is None or score_for == score_against:
            continue
        # A missing opponent link is reviewable metadata, not damaged round data.
        # Require this team's normalized side totals to prove the score instead.
        if (side.total_rounds_played != score_for + score_against
                or side.total_rounds_won != score_for
                or side.total_rounds_lost != score_against):
            continue
        sources.append(SourceMap(
            demo_file_id=demo.id, match_date=demo.match_date,
            won=score_for > score_against,
            went_to_overtime=bool(result.went_to_overtime), side=side,
            bomb=bomb,
            economy=economy,
            combat=combat,
            utility=utility,
            opponent_context=context,
        ))
    return sources


async def recalculate_team_map(
    session: AsyncSession, team_id: int, map_name: str, *, today: date | None = None,
) -> TeamMapAggregateResult:
    today = today or date.today()
    sources = await _source_maps(session, team_id, map_name)
    existing = list((await session.execute(select(TeamMapAggregate).where(
        TeamMapAggregate.team_id == team_id, TeamMapAggregate.map_name == map_name,
        TeamMapAggregate.aggregation_level == "organization",
    ))).scalars())
    await session.execute(delete(TeamMapAggregate).where(
        TeamMapAggregate.team_id == team_id, TeamMapAggregate.map_name == map_name,
        TeamMapAggregate.aggregation_level == "organization",
    ))
    if not sources:
        return TeamMapAggregateResult(team_id, map_name, 0, 0, len(existing))
    models = [_aggregate_model(team_id, map_name, "all", "all", sources, today)]
    dated = sorted((item for item in sources if item.match_date),
                   key=lambda item: (item.match_date, item.demo_file_id), reverse=True)
    for size in RECENT_WINDOWS:
        models.append(_aggregate_model(
            team_id, map_name, "recent", f"recent:{size}", dated[:size], today,
            window_size=size,
        ))
    for group in RANK_GROUPS:
        def aggregate_rank_group(item: SourceMap) -> str:
            context = item.opponent_context
            if context is None:
                return "unknown"
            if context.opponent_team_id is None and context.opponent_team_name:
                return "tier_2_3"
            return context.opponent_rank_group

        grouped = [item for item in sources if aggregate_rank_group(item) == group]
        models.append(_aggregate_model(
            team_id, map_name, "opponent_rank_group", f"rank:{group}", grouped,
            today, opponent_rank_group=group,
        ))
    session.add_all(models)
    warnings = []
    missing_dates = sum(item.match_date is None for item in sources)
    missing_context = sum(item.opponent_context is None for item in sources)
    if missing_dates: warnings.append(f"missing_match_date_for_recent:{missing_dates}")
    if missing_context: warnings.append(f"missing_opponent_context:{missing_context}")
    return TeamMapAggregateResult(team_id, map_name, len(sources), len(models), len(existing), warnings)


async def recalculate_team_roster_map(
    session: AsyncSession, team_id: int, roster_id: int, map_name: str,
    *, today: date | None = None,
) -> TeamMapAggregateResult:
    today = today or date.today()
    sources = await _source_maps(session, team_id, map_name, roster_id)
    condition = and_(
        TeamMapAggregate.team_id == team_id,
        TeamMapAggregate.map_name == map_name,
        TeamMapAggregate.aggregation_level == "roster",
        TeamMapAggregate.roster_id == roster_id,
    )
    existing = list((await session.execute(select(TeamMapAggregate).where(condition))).scalars())
    await session.execute(delete(TeamMapAggregate).where(condition))
    if not sources:
        return TeamMapAggregateResult(team_id, map_name, 0, 0, len(existing))
    kwargs = {"aggregation_level": "roster", "roster_id": roster_id}
    models = [_aggregate_model(team_id, map_name, "all", "all", sources, today, **kwargs)]
    dated = sorted((item for item in sources if item.match_date),
                   key=lambda item: (item.match_date, item.demo_file_id), reverse=True)
    for size in RECENT_WINDOWS:
        models.append(_aggregate_model(team_id, map_name, "recent", f"recent:{size}",
                                       dated[:size], today, window_size=size, **kwargs))
    for group in RANK_GROUPS:
        def rank_group(item: SourceMap) -> str:
            if item.opponent_context is None: return "unknown"
            if item.opponent_context.opponent_team_id is None and item.opponent_context.opponent_team_name: return "tier_2_3"
            return item.opponent_context.opponent_rank_group
        grouped = [item for item in sources if rank_group(item) == group]
        models.append(_aggregate_model(team_id, map_name, "opponent_rank_group", f"rank:{group}",
                                       grouped, today, opponent_rank_group=group, **kwargs))
    session.add_all(models)
    return TeamMapAggregateResult(team_id, map_name, len(sources), len(models), len(existing))


async def recalculate_roster(session: AsyncSession, roster_id: int) -> list[TeamMapAggregateResult]:
    link = (await session.execute(select(DemoTeamRoster).where(
        DemoTeamRoster.roster_id == roster_id,
    ).limit(1))).scalar_one_or_none()
    if link is None:
        return []
    maps = set((await session.execute(
        select(DemoMapResult.map_name).join(DemoTeamRoster, DemoTeamRoster.demo_map_result_id == DemoMapResult.id)
        .where(DemoTeamRoster.roster_id == roster_id, DemoMapResult.map_name.is_not(None))
    )).scalars())
    maps.update((await session.execute(select(TeamMapAggregate.map_name).where(
        TeamMapAggregate.roster_id == roster_id,
    ))).scalars())
    return [await recalculate_team_roster_map(session, link.team_id, roster_id, name) for name in sorted(maps)]


async def recalculate_demo_roster_aggregates(session: AsyncSession, demo_file_id: int) -> list[TeamMapAggregateResult]:
    rows = (await session.execute(
        select(DemoTeamRoster, DemoMapResult.map_name)
        .join(DemoMapResult, DemoMapResult.id == DemoTeamRoster.demo_map_result_id)
        .where(DemoTeamRoster.demo_file_id == demo_file_id, DemoTeamRoster.roster_id.is_not(None))
    )).all()
    return [await recalculate_team_roster_map(session, link.team_id, link.roster_id, map_name)
            for link, map_name in rows if map_name]


async def recalculate_demo_affected_aggregates(
    session: AsyncSession, demo_file_id: int,
) -> list[TeamMapAggregateResult]:
    result = (await session.execute(select(DemoMapResult).where(
        DemoMapResult.demo_file_id == demo_file_id,
    ))).scalar_one_or_none()
    if result is None or not result.map_name:
        return []
    output = []
    for team_id in dict.fromkeys((result.team_a_id, result.team_b_id)):
        if team_id is not None:
            output.append(await recalculate_team_map(session, team_id, result.map_name))
    output.extend(await recalculate_demo_roster_aggregates(session, demo_file_id))
    return output


async def recalculate_team(session: AsyncSession, team_id: int) -> list[TeamMapAggregateResult]:
    maps = set((await session.execute(select(DemoMapResult.map_name).where(
        DemoMapResult.map_name.is_not(None),
        or_(DemoMapResult.team_a_id == team_id, DemoMapResult.team_b_id == team_id),
    ))).scalars())
    maps.update((await session.execute(select(TeamMapAggregate.map_name).where(
        TeamMapAggregate.team_id == team_id,
    ))).scalars())
    return [await recalculate_team_map(session, team_id, name) for name in sorted(maps)]
