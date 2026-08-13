from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.analytics.combat.core import CombatKill, calculate_combat
from cs2eye.models.demo import DemoKill, DemoMapResult, DemoPlayerStat, DemoRound, DemoTeamCombatStat
from cs2eye.services.demo_parser_service import DeathEvent


def _same(left: str | None, right: str | None) -> bool:
    return bool(left and right and left.strip().casefold() == right.strip().casefold())


def _team(raw: str | None, result: DemoMapResult) -> tuple[str | None, int | None]:
    if _same(raw, result.team_a_name): return result.team_a_name, result.team_a_id
    if _same(raw, result.team_b_name): return result.team_b_name, result.team_b_id
    return raw, None


def _event_team(raw: str | None, team_num: int | None, round_row: DemoRound,
                result: DemoMapResult) -> tuple[str | None, int | None]:
    resolved = _team(raw, result)
    if resolved[0] is not None:
        return resolved
    side = "T" if team_num == 2 else "CT" if team_num == 3 else None
    if side == round_row.team_a_side:
        return result.team_a_name, result.team_a_id
    if side == round_row.team_b_side:
        return result.team_b_name, result.team_b_id
    return None, None


def _event_round(rounds: list[DemoRound], tick: int, ordinal: int | None) -> DemoRound | None:
    """Bind by normalized physical interval; ordinal only disambiguates split demos."""
    candidate = next((row for row in rounds if row.round_number == ordinal), None)
    if candidate is not None and candidate.ended_at_tick is not None:
        starts_before = candidate.started_at_tick is None or candidate.started_at_tick <= tick
        if starts_before and tick <= candidate.ended_at_tick:
            return candidate
    interval_matches = [
        row for row in rounds
        if row.ended_at_tick is not None and tick <= row.ended_at_tick
        and (row.started_at_tick is None or row.started_at_tick <= tick)
    ]
    if not interval_matches:
        return None
    return min(interval_matches, key=lambda row: (
        abs(row.round_number - ordinal) if ordinal is not None else 0,
        row.ended_at_tick - tick,
        row.round_number,
    ))


def _post_round_event_round(rounds: list[DemoRound], tick: int) -> DemoRound | None:
    """Return the preceding round only while still before the next round start."""
    previous = [row for row in rounds if row.ended_at_tick is not None and row.ended_at_tick < tick]
    if not previous:
        return None
    candidate = max(previous, key=lambda row: row.ended_at_tick)
    next_starts = [row.started_at_tick for row in rounds
                   if row.started_at_tick is not None and row.started_at_tick > candidate.ended_at_tick]
    return candidate if not next_starts or tick < min(next_starts) else None


def _is_enemy_player_death(event: DeathEvent) -> bool:
    return bool(
        event.attacker and event.attacker.key != event.victim.key
        and event.attacker.team_num in {2, 3} and event.victim.team_num in {2, 3}
        and event.attacker.team_num != event.victim.team_num
    )


async def replace_demo_combat(session: AsyncSession, result: DemoMapResult,
                              parsed_kills: list[DeathEvent], round_status: str) -> list[str]:
    await session.execute(delete(DemoKill).where(DemoKill.demo_file_id == result.demo_file_id))
    await session.execute(delete(DemoTeamCombatStat).where(DemoTeamCombatStat.demo_file_id == result.demo_file_id))
    player_rows = list((await session.execute(select(DemoPlayerStat).where(
        DemoPlayerStat.demo_file_id == result.demo_file_id))).scalars())
    rounds = list((await session.execute(select(DemoRound).where(
        DemoRound.demo_file_id == result.demo_file_id, DemoRound.is_complete.is_(True)
    ).order_by(DemoRound.round_number))).scalars())
    if round_status != "complete":
        result.combat_data_status = "partial" if round_status in {"partial", "not_parsed"} else "needs_review"
        for row in player_rows: row.combat_data = None
        return []
    round_by_number = {row.round_number: row for row in rounds}
    players = {row.identity_key: row for row in player_rows}
    rosters: dict[str, set[str]] = {}
    for row in player_rows:
        team_name, _ = _team(row.demo_team_name or row.team_name, result)
        if team_name: rosters.setdefault(team_name, set()).add(row.identity_key)
    normalized: list[CombatKill] = []
    source_by_event: list[DeathEvent] = []
    issues: list[str] = []
    for event in parsed_kills:
        number = event.gameplay_round_number or event.round_number
        round_row = _event_round(rounds, event.tick, number)
        if round_row is None or event.tick <= 0:
            # GOTV emits pregame, post-round and post-match deaths even when
            # warmup/noreplay flags are inconsistent. Combat is gameplay-only.
            continue
        number = round_row.round_number
        attacker_team, _ = _event_team(
            event.attacker.team_name if event.attacker else None,
            event.attacker.team_num if event.attacker else None, round_row, result,
        )
        victim_team, _ = _event_team(event.victim.team_name, event.victim.team_num, round_row, result)
        attacker_side = (round_row.team_a_side if _same(attacker_team, result.team_a_name) else
                         round_row.team_b_side if _same(attacker_team, result.team_b_name) else None)
        victim_side = (round_row.team_a_side if _same(victim_team, result.team_a_name) else
                       round_row.team_b_side if _same(victim_team, result.team_b_name) else None)
        attacker_key = event.attacker.key if event.attacker else None
        normalized.append(CombatKill(
            number, event.tick, attacker_key, event.victim.key, attacker_team, victim_team,
            attacker_side, victim_side, event.weapon, event.is_headshot,
            event.assister.key if event.assister else None,
            bool(attacker_key and attacker_team == victim_team), attacker_key == event.victim.key,
        ))
        source_by_event.append(event)
    if rounds and not normalized:
        issues.append("no_gameplay_kill_events")
    winners = {row.round_number: row.winner_team_name for row in rounds if row.winner_team_name}
    derived, player_data, team_data, calculation_issues = calculate_combat(normalized, rosters, winners)
    issues.extend(calculation_issues)
    for row in player_rows: row.combat_data = player_data.get(row.identity_key, _empty_player_payload())
    for event, data in zip(source_by_event, derived):
        round_row = round_by_number[data.round_number]
        attacker_team, attacker_team_id = _team(data.attacker_team, result)
        victim_team, victim_team_id = _team(data.victim_team, result)
        session.add(DemoKill(
            demo_file_id=result.demo_file_id, demo_map_result_id=result.id, round_id=round_row.id,
            tick=data.tick, attacker_player_id=players.get(data.attacker_key).player_id if data.attacker_key in players else None,
            victim_player_id=players.get(data.victim_key).player_id if data.victim_key in players else None,
            assister_player_id=players.get(data.assister_key).player_id if data.assister_key in players else None,
            attacker_identity_key=data.attacker_key, victim_identity_key=data.victim_key, assister_identity_key=data.assister_key,
            attacker_name=event.attacker.nickname if event.attacker else None, victim_name=event.victim.nickname,
            attacker_team_id=attacker_team_id, victim_team_id=victim_team_id,
            attacker_team_name=attacker_team, victim_team_name=victim_team,
            attacker_side=data.attacker_side, victim_side=data.victim_side, weapon=data.weapon,
            is_headshot=data.is_headshot, is_teamkill=data.is_teamkill, is_suicide=data.is_suicide,
            is_opening_kill=data.is_opening_kill, is_trade_kill=data.is_trade_kill, was_traded=data.was_traded,
        ))
    for team_name, team_id in ((result.team_a_name, result.team_a_id), (result.team_b_name, result.team_b_id)):
        if team_name:
            session.add(DemoTeamCombatStat(demo_file_id=result.demo_file_id, demo_map_result_id=result.id,
                                           team_id=team_id, team_name=team_name,
                                           combat_data=team_data.get(team_name, _empty_team_payload())))
    result.combat_data_status = "needs_review" if issues else "complete"
    return list(dict.fromkeys(issues))


def _empty_player_payload() -> dict:
    # Running the pure calculator keeps empty-sample rates consistently null.
    return calculate_combat([], {}, {})[1].get("_", {
        "opening_kills": 0, "opening_deaths": 0, "opening_attempts": 0,
        "opening_success_rate": None, "trade_kills": 0, "trade_opportunities": 0,
        "trade_success_rate": None, "deaths_traded": 0, "deaths_not_traded": 0,
        "death_trade_rate": None, "clutch_opportunities": 0, "clutch_wins": 0,
        "clutch_losses": 0, "clutch_win_rate": None,
        "ct_opening_kills": 0, "ct_opening_deaths": 0, "ct_opening_success_rate": None,
        "t_opening_kills": 0, "t_opening_deaths": 0, "t_opening_success_rate": None,
        **{f"clutch_1v{x}_{field}": 0 for x in range(1, 6) for field in ("attempts", "wins")},
    })


def _empty_team_payload() -> dict:
    return {
        "opening_kills": 0, "opening_deaths": 0, "rounds_with_opening_kill": 0,
        "rounds_with_opening_death": 0, "opening_success_rate": None,
        "opening_conversion_wins": 0, "opening_conversion_losses": 0, "opening_conversion_rate": None,
        "opening_death_rounds": 0, "opening_recovery_wins": 0, "opening_recovery_losses": 0, "opening_recovery_rate": None,
        "ct_opening_kills": 0, "ct_opening_deaths": 0, "ct_opening_success_rate": None,
        "t_opening_kills": 0, "t_opening_deaths": 0, "t_opening_success_rate": None,
        "trade_kills": 0, "team_deaths": 0, "eligible_team_deaths": 0, "deaths_traded": 0, "trade_rate": None,
        "clutch_opportunities": 0, "clutch_wins": 0, "clutch_losses": 0, "clutch_win_rate": None,
        "clutches_lost_to_opponent": 0,
        **{f"clutch_1v{x}_{field}": 0 for x in range(1, 6) for field in ("attempts", "wins")},
    }
