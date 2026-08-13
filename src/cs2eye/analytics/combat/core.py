from collections import defaultdict
from dataclasses import dataclass, replace
from typing import Iterable

from cs2eye.analytics.combat.config import TRADE_WINDOW_TICKS


@dataclass(frozen=True)
class CombatKill:
    round_number: int
    tick: int
    attacker_key: str | None
    victim_key: str
    attacker_team: str | None
    victim_team: str | None
    attacker_side: str | None = None
    victim_side: str | None = None
    weapon: str | None = None
    is_headshot: bool | None = None
    assister_key: str | None = None
    is_teamkill: bool = False
    is_suicide: bool = False
    is_opening_kill: bool = False
    is_trade_kill: bool = False
    was_traded: bool = False

    @property
    def valid_enemy_kill(self) -> bool:
        return bool(self.attacker_key and self.attacker_team and self.victim_team
                    and self.attacker_team != self.victim_team
                    and not self.is_teamkill and not self.is_suicide)


def _empty_player() -> dict:
    return {
        "opening_kills": 0, "opening_deaths": 0, "opening_attempts": 0,
        "ct_opening_kills": 0, "ct_opening_deaths": 0,
        "t_opening_kills": 0, "t_opening_deaths": 0,
        "trade_kills": 0, "trade_opportunities": 0,
        "deaths_traded": 0, "deaths_not_traded": 0,
        "clutch_opportunities": 0, "clutch_wins": 0, "clutch_losses": 0,
        **{f"clutch_1v{x}_{field}": 0 for x in range(1, 6) for field in ("attempts", "wins")},
    }


def _empty_team() -> dict:
    return {
        "rounds_with_opening_kill": 0, "rounds_with_opening_death": 0,
        "opening_kills": 0, "opening_deaths": 0,
        "opening_conversion_wins": 0, "opening_conversion_losses": 0,
        "opening_death_rounds": 0, "opening_recovery_wins": 0, "opening_recovery_losses": 0,
        "ct_opening_kills": 0, "ct_opening_deaths": 0,
        "t_opening_kills": 0, "t_opening_deaths": 0,
        "trade_kills": 0, "team_deaths": 0, "eligible_team_deaths": 0, "deaths_traded": 0,
        "clutch_opportunities": 0, "clutch_wins": 0, "clutch_losses": 0,
        "clutches_lost_to_opponent": 0,
        **{f"clutch_1v{x}_{field}": 0 for x in range(1, 6) for field in ("attempts", "wins")},
    }


def _rates(value: dict) -> dict:
    def rate(a: str, b: str) -> float | None:
        return round(value[a] * 100 / value[b], 4) if value[b] else None
    if "opening_attempts" in value:
        value["opening_success_rate"] = rate("opening_kills", "opening_attempts")
        value["ct_opening_success_rate"] = (round(value["ct_opening_kills"] * 100 / (value["ct_opening_kills"] + value["ct_opening_deaths"]), 4)
                                             if value["ct_opening_kills"] + value["ct_opening_deaths"] else None)
        value["t_opening_success_rate"] = (round(value["t_opening_kills"] * 100 / (value["t_opening_kills"] + value["t_opening_deaths"]), 4)
                                            if value["t_opening_kills"] + value["t_opening_deaths"] else None)
        value["trade_success_rate"] = rate("trade_kills", "trade_opportunities")
        death_total = value["deaths_traded"] + value["deaths_not_traded"]
        value["death_trade_rate"] = round(value["deaths_traded"] * 100 / death_total, 4) if death_total else None
    else:
        value["opening_success_rate"] = (round(value["opening_kills"] * 100 / (value["opening_kills"] + value["opening_deaths"]), 4)
                                         if value["opening_kills"] + value["opening_deaths"] else None)
        value["opening_kill_rate"] = value["opening_success_rate"]
        value["opening_conversion_rate"] = rate("opening_conversion_wins", "rounds_with_opening_kill")
        value["opening_recovery_rate"] = rate("opening_recovery_wins", "opening_death_rounds")
        for side in ("ct", "t"):
            attempts = value[f"{side}_opening_kills"] + value[f"{side}_opening_deaths"]
            value[f"{side}_opening_success_rate"] = round(value[f"{side}_opening_kills"] * 100 / attempts, 4) if attempts else None
        value["trade_rate"] = rate("deaths_traded", "eligible_team_deaths")
    value["clutch_win_rate"] = rate("clutch_wins", "clutch_opportunities")
    return value


def calculate_combat(kills: Iterable[CombatKill], rosters: dict[str, set[str]],
                     round_winners: dict[int, str]) -> tuple[list[CombatKill], dict[str, dict], dict[str, dict], list[str]]:
    """Pure deterministic combat derivation. Team names are stable demo snapshots."""
    events = sorted(kills, key=lambda x: (x.round_number, x.tick))
    players = defaultdict(_empty_player)
    teams = defaultdict(_empty_team)
    issues: list[str] = []
    by_round: dict[int, list[tuple[int, CombatKill]]] = defaultdict(list)
    for index, event in enumerate(events):
        by_round[event.round_number].append((index, event))
    output = list(events)
    for round_number, indexed in by_round.items():
        valid = [(i, e) for i, e in indexed if e.valid_enemy_kill]
        if not valid:
            continue
        opening_i, opening = valid[0]
        output[opening_i] = replace(opening, is_opening_kill=True)
        players[opening.attacker_key]["opening_kills"] += 1
        players[opening.victim_key]["opening_deaths"] += 1
        for key, side in ((opening.attacker_key, opening.attacker_side), (opening.victim_key, opening.victim_side)):
            players[key]["opening_attempts"] += 1
            if side in {"CT", "T"}:
                players[key][f"{side.lower()}_opening_{'kills' if key == opening.attacker_key else 'deaths'}"] += 1
        attack, victim = teams[opening.attacker_team], teams[opening.victim_team]
        attack["rounds_with_opening_kill"] += 1; attack["opening_kills"] += 1
        victim["rounds_with_opening_death"] += 1; victim["opening_deaths"] += 1; victim["opening_death_rounds"] += 1
        if opening.attacker_side in {"CT", "T"}: attack[f"{opening.attacker_side.lower()}_opening_kills"] += 1
        if opening.victim_side in {"CT", "T"}: victim[f"{opening.victim_side.lower()}_opening_deaths"] += 1
        winner = round_winners.get(round_number)
        attack[f"opening_conversion_{'wins' if winner == opening.attacker_team else 'losses'}"] += 1
        victim[f"opening_recovery_{'wins' if winner == opening.victim_team else 'losses'}"] += 1

        alive = {team: set(members) for team, members in rosters.items()}
        clutch_started: dict[str, tuple[str, int]] = {}
        for pos, (event_i, event) in enumerate(valid):
            if event.victim_key not in alive.get(event.victim_team, set()):
                issues.append(f"invalid_kill_sequence:round={round_number}:victim={event.victim_key}")
            teams[event.victim_team]["team_deaths"] += 1
            teams[event.victim_team]["eligible_team_deaths"] += 1
            possible = alive.get(event.victim_team, set()) - {event.victim_key}
            for key in possible:
                players[key]["trade_opportunities"] += 1
            alive.setdefault(event.victim_team, set()).discard(event.victim_key)
            for prior_pos in range(pos - 1, -1, -1):
                prior_i, prior = valid[prior_pos]
                if event.tick - prior.tick > TRADE_WINDOW_TICKS:
                    break
                if prior.attacker_key == event.victim_key and prior.victim_team == event.attacker_team and not output[prior_i].was_traded:
                    output[event_i] = replace(output[event_i], is_trade_kill=True)
                    output[prior_i] = replace(output[prior_i], was_traded=True)
                    players[event.attacker_key]["trade_kills"] += 1
                    players[prior.victim_key]["deaths_traded"] += 1
                    teams[event.attacker_team]["trade_kills"] += 1
                    teams[prior.victim_team]["deaths_traded"] += 1
                    break
            for team, members in alive.items():
                opponents = sum(len(v) for other, v in alive.items() if other != team)
                if len(members) == 1 and opponents >= 1 and team not in clutch_started:
                    player = next(iter(members)); size = min(5, opponents)
                    clutch_started[team] = (player, size)
        for team, (player, size) in clutch_started.items():
            won = round_winners.get(round_number) == team
            players[player]["clutch_opportunities"] += 1; players[player]["clutch_wins" if won else "clutch_losses"] += 1
            players[player][f"clutch_1v{size}_attempts"] += 1
            if won: players[player][f"clutch_1v{size}_wins"] += 1
            teams[team]["clutch_opportunities"] += 1; teams[team]["clutch_wins" if won else "clutch_losses"] += 1
            teams[team][f"clutch_1v{size}_attempts"] += 1
            if won: teams[team][f"clutch_1v{size}_wins"] += 1
            if not won and round_winners.get(round_number): teams[round_winners[round_number]]["clutches_lost_to_opponent"] += 1
    for event in output:
        if event.valid_enemy_kill and not event.was_traded:
            players[event.victim_key]["deaths_not_traded"] += 1
    return output, {k: _rates(v) for k, v in players.items()}, {k: _rates(v) for k, v in teams.items()}, issues
