from collections import defaultdict
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.demo import DemoMapResult, DemoPlayerStat, DemoRound, DemoTeamUtilityStat, DemoUtilityEvent
from cs2eye.services.demo_combat_service import _event_round, _event_team, _same, _team
from cs2eye.services.demo_parser_service import UtilityEvent


COUNT_KEYS = ("he_thrown", "flash_thrown", "smoke_thrown", "fire_thrown", "decoy_thrown",
              "he_damage", "fire_damage", "utility_friendly_damage", "utility_self_damage",
              "enemies_flashed", "teammates_flashed", "flash_assists")


def _base(rounds: int) -> dict:
    return {"rounds_played": rounds, **{key: 0 for key in COUNT_KEYS},
            "enemy_flash_duration": 0.0, "teammate_flash_duration": 0.0,
            "ct": {"rounds_played": 0, **{key: 0 for key in COUNT_KEYS}},
            "t": {"rounds_played": 0, **{key: 0 for key in COUNT_KEYS}}}


def finalize(value: dict) -> dict:
    def div(num: str, den: str | int):
        denominator = value.get(den, 0) if isinstance(den, str) else den
        return round(value.get(num, 0) / denominator, 4) if denominator else None
    value["total_utility_thrown"] = sum(value[key] for key in ("he_thrown", "flash_thrown", "smoke_thrown", "fire_thrown"))
    value["utility_damage"] = value["he_damage"] + value["fire_damage"]
    rounds = value["rounds_played"]
    value.update({
        "utility_per_round": round(value["total_utility_thrown"] / rounds, 4) if rounds else None,
        "he_per_round": div("he_thrown", rounds), "flash_per_round": div("flash_thrown", rounds),
        "smoke_per_round": div("smoke_thrown", rounds), "fire_per_round": div("fire_thrown", rounds),
        "he_damage_per_round": div("he_damage", rounds), "fire_damage_per_round": div("fire_damage", rounds),
        "utility_damage_per_round": div("utility_damage", rounds),
        "he_damage_per_he": div("he_damage", "he_thrown"),
        "fire_damage_per_grenade": div("fire_damage", "fire_thrown"),
        "enemies_flashed_per_flash": div("enemies_flashed", "flash_thrown"),
        "teammates_flashed_per_flash": div("teammates_flashed", "flash_thrown"),
        "enemy_flash_seconds_per_flash": div("enemy_flash_duration", "flash_thrown"),
        "flash_assists_per_round": div("flash_assists", rounds),
        "utility_left_on_death_total": None, "average_utility_left_on_death": None,
    })
    for side in ("ct", "t"):
        current = value[side]; side_rounds = current["rounds_played"]
        current["total_utility_thrown"] = sum(current[key] for key in ("he_thrown", "flash_thrown", "smoke_thrown", "fire_thrown"))
        current["utility_damage"] = current["he_damage"] + current["fire_damage"]
        for key in ("utility", "he_damage", "fire_damage", "utility_damage"):
            source = "total_utility_thrown" if key == "utility" else key
            current[f"{key}_per_round"] = round(current[source] / side_rounds, 4) if side_rounds else None
        current["enemies_flashed_per_flash"] = round(current["enemies_flashed"] / current["flash_thrown"], 4) if current["flash_thrown"] else None
    return value


async def replace_demo_utility(session: AsyncSession, result: DemoMapResult,
                               events: list[UtilityEvent], round_status: str) -> list[str]:
    await session.execute(delete(DemoUtilityEvent).where(DemoUtilityEvent.demo_file_id == result.demo_file_id))
    await session.execute(delete(DemoTeamUtilityStat).where(DemoTeamUtilityStat.demo_file_id == result.demo_file_id))
    players = list((await session.execute(select(DemoPlayerStat).where(DemoPlayerStat.demo_file_id == result.demo_file_id))).scalars())
    rounds = list((await session.execute(select(DemoRound).where(DemoRound.demo_file_id == result.demo_file_id, DemoRound.is_complete.is_(True)))).scalars())
    if round_status != "complete":
        result.utility_data_status = "partial" if round_status in {"partial", "not_parsed"} else "needs_review"
        for player in players: player.utility_data = None
        return []
    player_by_key = {row.identity_key: row for row in players}
    pdata = {row.identity_key: _base(row.rounds_played) for row in players}
    teams = [(result.team_a_name, result.team_a_id), (result.team_b_name, result.team_b_id)]
    tdata = {name: _base(len(rounds)) for name, _ in teams if name}
    for row in players:
        player_team, _ = _team(row.demo_team_name or row.team_name, result)
        if player_team:
            for side in ("CT", "T"):
                pdata[row.identity_key][side.lower()]["rounds_played"] = sum(
                    (round_row.team_a_side if _same(player_team, result.team_a_name) else round_row.team_b_side) == side
                    for round_row in rounds
                )
    for name in tdata:
        for side in ("CT", "T"):
            tdata[name][side.lower()]["rounds_played"] = sum(
                (row.team_a_side if _same(name, result.team_a_name) else row.team_b_side) == side for row in rounds
            )
    issues: list[str] = []
    for event in events:
        round_row = _event_round(rounds, event.tick, event.gameplay_round_number)
        if round_row is None:
            # demoparser2 legitimately emits events in freeze/post-round gaps
            # and during post-match cleanup. Utility is gameplay-only.
            continue
        team_name, team_id = _event_team(event.player.team_name, event.player.team_num, round_row, result)
        if team_name not in tdata or event.player.key not in pdata:
            issues.append("utility_owner_unresolved"); continue
        side = (round_row.team_a_side if _same(team_name, result.team_a_name) else round_row.team_b_side)
        target_relation = None
        if event.target:
            target_team, _ = _event_team(event.target.team_name, event.target.team_num, round_row, result)
            target_relation = "self" if event.target.key == event.player.key else "teammate" if _same(target_team, team_name) else "enemy"
        targets = (pdata[event.player.key], tdata[team_name])
        if event.event_kind == "throw":
            for target in targets:
                target[f"{event.grenade_type}_thrown"] += 1; target[side.lower()][f"{event.grenade_type}_thrown"] += 1
        elif event.event_kind == "damage":
            field = f"{event.grenade_type}_damage"
            if target_relation == "enemy":
                for target in targets: target[field] += event.damage or 0; target[side.lower()][field] += event.damage or 0
            elif target_relation in {"teammate", "self"}:
                friendly = "utility_self_damage" if target_relation == "self" else "utility_friendly_damage"
                for target in targets: target[friendly] += event.damage or 0; target[side.lower()][friendly] += event.damage or 0
        elif event.event_kind == "flash":
            field = "enemies_flashed" if target_relation == "enemy" else "teammates_flashed"
            duration = "enemy_flash_duration" if target_relation == "enemy" else "teammate_flash_duration"
            for target in targets:
                target[field] += 1; target[side.lower()][field] += 1
                target[duration] += float(event.flash_duration or 0)
        elif event.event_kind == "flash_assist":
            for target in targets: target["flash_assists"] += 1; target[side.lower()]["flash_assists"] += 1
        target_row = player_by_key.get(event.target.key) if event.target else None
        session.add(DemoUtilityEvent(
            demo_file_id=result.demo_file_id, demo_map_result_id=result.id, round_id=round_row.id,
            tick=event.tick, event_kind=event.event_kind, grenade_type=event.grenade_type,
            raw_grenade_type=event.raw_grenade_type, player_id=player_by_key[event.player.key].player_id,
            player_identity_key=event.player.key, player_name=event.player.nickname, team_id=team_id,
            team_name=team_name, side=side, target_player_id=target_row.player_id if target_row else None,
            target_identity_key=event.target.key if event.target else None,
            target_name=event.target.nickname if event.target else None, target_relation=target_relation,
            damage=event.damage, flash_duration=event.flash_duration,
        ))
    for key, row in player_by_key.items(): row.utility_data = finalize(pdata[key])
    for name, team_id in teams:
        if name: session.add(DemoTeamUtilityStat(demo_file_id=result.demo_file_id, demo_map_result_id=result.id,
                                                team_id=team_id, team_name=name, utility_data=finalize(tdata[name])))
    for data in tdata.values():
        if data["he_damage"] and not data["he_thrown"]: issues.append("he_damage_without_throw")
        if data["enemies_flashed"] and not data["flash_thrown"]: issues.append("flash_effect_without_throw")
    result.utility_data_status = "needs_review" if issues else "complete"
    return list(dict.fromkeys(issues))
