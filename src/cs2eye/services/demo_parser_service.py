from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from demoparser2 import DemoParser

from cs2eye.services.demo_player_link_service import normalize_nickname
from cs2eye.services.player_internal_rating_service import (
    INTERNAL_RATING_VERSION, calculate_internal_rating,
)
from cs2eye.services.demo_map_result_service import ParsedMapResult
from cs2eye.services.demo_round_service import ParsedRound


@dataclass(frozen=True)
class PlayerRef:
    steam_id: str | None
    nickname: str
    team_name: str | None
    team_num: int | None

    @property
    def key(self) -> str:
        return f"steam:{self.steam_id}" if self.steam_id else f"nick:{normalize_nickname(self.nickname)}"


@dataclass(frozen=True)
class RoundSnapshot:
    round_number: int
    players: list[tuple[PlayerRef, bool]]


@dataclass(frozen=True)
class DeathEvent:
    round_number: int
    victim: PlayerRef
    attacker: PlayerRef | None
    assister: PlayerRef | None


@dataclass(frozen=True)
class DamageEvent:
    round_number: int
    attacker: PlayerRef
    victim: PlayerRef
    damage: int


@dataclass
class ParsedDemoPlayerStat:
    steam_id: str | None
    nickname: str
    team_name: str | None
    rounds_played: int
    kills: int
    deaths: int
    assists: int
    total_damage: int
    adr: Decimal
    kast_rounds: int
    kast_percent: Decimal
    internal_rating: Decimal
    internal_rating_version: str = INTERNAL_RATING_VERSION

    @property
    def identity_key(self) -> str:
        return f"steam:{self.steam_id}" if self.steam_id else f"nick:{normalize_nickname(self.nickname)}"


@dataclass
class ParsedDemo:
    map_result: ParsedMapResult
    player_stats: list[ParsedDemoPlayerStat]
    rounds: list[ParsedRound] = None

    def __post_init__(self) -> None:
        if self.rounds is None:
            self.rounds = []

    def __iter__(self):
        """Preserve the old adapter's iterable player-stat contract."""
        return iter(self.player_stats)


def aggregate_player_events(
    snapshots: list[RoundSnapshot], deaths: list[DeathEvent],
    damages: list[DamageEvent],
) -> list[ParsedDemoPlayerStat]:
    refs: dict[str, PlayerRef] = {}
    rounds: dict[str, set[int]] = defaultdict(set)
    survived: dict[str, set[int]] = defaultdict(set)
    kills: dict[str, int] = defaultdict(int)
    assists: dict[str, int] = defaultdict(int)
    death_counts: dict[str, int] = defaultdict(int)
    damage_totals: dict[str, int] = defaultdict(int)
    kast_actions: dict[str, set[int]] = defaultdict(set)
    deaths_by_round: dict[int, list[DeathEvent]] = defaultdict(list)

    def remember(player: PlayerRef) -> None:
        current = refs.get(player.key)
        if current is None or (current.team_name is None and player.team_name is not None):
            refs[player.key] = player

    for snapshot in snapshots:
        for player, is_alive in snapshot.players:
            if not player.nickname or player.team_num not in {2, 3}:
                continue
            remember(player)
            rounds[player.key].add(snapshot.round_number)
            if is_alive:
                survived[player.key].add(snapshot.round_number)
                kast_actions[player.key].add(snapshot.round_number)

    for event in deaths:
        if event.attacker and event.attacker.team_num == event.victim.team_num:
            continue
        deaths_by_round[event.round_number].append(event)
        remember(event.victim)
        death_counts[event.victim.key] += 1
        if event.attacker and event.attacker.team_num != event.victim.team_num:
            remember(event.attacker)
            kills[event.attacker.key] += 1
            kast_actions[event.attacker.key].add(event.round_number)
        if event.assister and event.assister.team_num != event.victim.team_num:
            remember(event.assister)
            assists[event.assister.key] += 1
            kast_actions[event.assister.key].add(event.round_number)

    for round_events in deaths_by_round.values():
        for index, death in enumerate(round_events):
            killer = death.attacker
            if killer is None or killer.team_num == death.victim.team_num:
                continue
            traded = any(
                later.victim.key == killer.key
                and later.attacker is not None
                and later.attacker.team_num == death.victim.team_num
                for later in round_events[index + 1:]
            )
            if traded:
                kast_actions[death.victim.key].add(death.round_number)

    for event in damages:
        if event.attacker.team_num == event.victim.team_num:
            continue
        remember(event.attacker)
        damage_totals[event.attacker.key] += max(0, event.damage)

    result: list[ParsedDemoPlayerStat] = []
    for key, player in refs.items():
        played = len(rounds[key])
        if played <= 0:
            continue
        total_damage = damage_totals[key]
        adr = (Decimal(total_damage) / Decimal(played)).quantize(Decimal("0.0001"))
        kast_rounds = len(kast_actions[key] & rounds[key])
        kast = (Decimal(kast_rounds) * 100 / Decimal(played)).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP,
        )
        result.append(ParsedDemoPlayerStat(
            steam_id=player.steam_id, nickname=player.nickname,
            team_name=player.team_name, rounds_played=played,
            kills=kills[key], deaths=death_counts[key], assists=assists[key],
            total_damage=total_damage, adr=adr, kast_rounds=kast_rounds,
            kast_percent=kast,
            internal_rating=calculate_internal_rating(
                rounds_played=played, kills=kills[key], deaths=death_counts[key],
                assists=assists[key], adr=adr, kast_percent=kast,
            ),
        ))
    return sorted(result, key=lambda item: item.nickname.casefold())


def _rows(frame: Any) -> list[dict[str, Any]]:
    return frame.to_dicts() if hasattr(frame, "to_dicts") else frame.to_dict("records")


def _value(row: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return default


def _player(row: dict[str, Any], prefix: str = "") -> PlayerRef | None:
    steam = _value(row, f"{prefix}steamid", f"{prefix}steam_id", f"{prefix}player_steamid")
    nickname = _value(row, f"{prefix}name", f"{prefix}player_name")
    if not nickname:
        return None
    if str(nickname).strip().upper().startswith("BOT ") or str(nickname).strip().upper() in {
        "GOTV", "SOURCE TV",
    }:
        return None
    return PlayerRef(
        steam_id=str(steam) if steam and str(steam) != "0" else None,
        nickname=str(nickname),
        team_name=_value(row, f"{prefix}team_clan_name", f"{prefix}team_name"),
        team_num=_value(row, f"{prefix}team_num"),
    )


def is_valid_round_row(row: dict[str, Any]) -> bool:
    return not bool(_value(row, "is_warmup_period", default=False)) and not bool(
        _value(row, "is_technical_timeout", default=False),
    )


def completed_rounds_count(rows: list[dict[str, Any]]) -> int:
    """Count gameplay rounds without double-counting repeated round_end events."""
    round_numbers = {
        int(value) for row in rows
        if (value := _value(row, "total_rounds_played")) is not None
    }
    if round_numbers:
        return len(round_numbers)
    return len({int(row["tick"]) for row in rows if row.get("tick") is not None})


class Demoparser2Adapter:
    parser_name = "demoparser2"

    def __init__(self, version: str = "0.41.4") -> None:
        self.parser_version = version

    def parse(self, path: Path) -> ParsedDemo:
        parser = DemoParser(str(path))
        round_rows = _rows(parser.parse_event(
            "round_end", other=[
                "total_rounds_played", "is_warmup_period", "is_technical_timeout",
                "game_time", "round_start_time", "round_win_reason", "is_game_restart",
            ],
        ))
        valid = [row for row in round_rows if is_valid_round_row(row)]
        ticks = [int(row["tick"]) for row in valid if row.get("tick") is not None]
        round_by_tick = {int(row["tick"]): int(_value(row, "total_rounds_played", default=index + 1)) for index, row in enumerate(valid) if row.get("tick") is not None}
        tick_rows = _rows(parser.parse_ticks(
            ["team_clan_name", "team_num", "team_rounds_total", "team_score_overtime", "is_alive"],
            ticks=ticks,
        )) if ticks else []
        snapshot_players: dict[int, list[tuple[PlayerRef, bool]]] = defaultdict(list)
        for row in tick_rows:
            player = _player(row)
            tick = int(_value(row, "tick", default=-1))
            if player and tick in round_by_tick:
                snapshot_players[round_by_tick[tick]].append((player, bool(_value(row, "is_alive", default=False))))
        snapshots = [RoundSnapshot(number, players) for number, players in snapshot_players.items()]

        death_events: list[DeathEvent] = []
        for row in _rows(parser.parse_event(
            "player_death", player=["team_num"],
            other=["total_rounds_played", "is_warmup_period", "is_technical_timeout"],
        )):
            if _value(row, "is_warmup_period", default=False) or _value(row, "is_technical_timeout", default=False):
                continue
            victim = _player(row, "user_")
            if victim:
                death_events.append(DeathEvent(
                    int(_value(row, "total_rounds_played", default=0)), victim,
                    _player(row, "attacker_"), _player(row, "assister_"),
                ))
        damage_events: list[DamageEvent] = []
        for row in _rows(parser.parse_event(
            "player_hurt", player=["team_num"],
            other=["total_rounds_played", "is_warmup_period", "is_technical_timeout"],
        )):
            if _value(row, "is_warmup_period", default=False) or _value(row, "is_technical_timeout", default=False):
                continue
            attacker, victim = _player(row, "attacker_"), _player(row, "user_")
            if attacker and victim:
                damage_events.append(DamageEvent(
                    int(_value(row, "total_rounds_played", default=0)), attacker,
                    victim, int(_value(row, "dmg_health", default=0)),
                ))
        header = parser.parse_header() or {} if hasattr(parser, "parse_header") else {}
        raw_map_name = _value(header, "map_name", "map", "mapname")
        teams_by_tick: dict[int, dict[int, tuple[str | None, int | None, int | None]]] = defaultdict(dict)
        for row in tick_rows:
            tick = int(_value(row, "tick", default=-1))
            if tick >= 0:
                team_num = _value(row, "team_num")
                if team_num in {2, 3}:
                    name = _value(row, "team_clan_name", "team_name")
                    score = _value(row, "team_rounds_total")
                    overtime_score = _value(row, "team_score_overtime")
                    current = teams_by_tick[tick].get(int(team_num))
                    if current is None or (current[0] is None and name):
                        teams_by_tick[tick][int(team_num)] = (
                            str(name) if name else None,
                            int(score) if score is not None else None,
                            int(overtime_score) if overtime_score is not None else None,
                        )
        final_teams = teams_by_tick.get(max(ticks), {}) if ticks else {}
        ordered = [final_teams.get(number, (None, None, None)) for number in (2, 3)]
        overtime_values = [item[2] for item in ordered if item[2] is not None]
        parsed_rounds: list[ParsedRound] = []
        for row in valid:
            tick = int(_value(row, "tick", default=-1))
            state = teams_by_tick.get(tick, {})
            t_state, ct_state = state.get(2, (None, None, None)), state.get(3, (None, None, None))
            game_time, start_time = _value(row, "game_time"), _value(row, "round_start_time")
            duration = None
            if game_time is not None and start_time is not None and float(game_time) >= float(start_time):
                duration = Decimal(str(float(game_time) - float(start_time))).quantize(Decimal("0.0001"))
            scores = {
                name: score for name, score, _ in (t_state, ct_state)
                if name and score is not None
            }
            raw_reason = _value(row, "reason", "end_reason", "round_end_reason", "round_win_reason")
            parsed_rounds.append(ParsedRound(
                raw_round_index=int(_value(row, "total_rounds_played", default=len(parsed_rounds))),
                winner_side=_value(row, "winner", "winner_side", "team_num"),
                t_team_name=t_state[0], ct_team_name=ct_state[0], end_reason=raw_reason,
                raw_scores_after=scores, is_warmup=False,
                is_restart=bool(_value(row, "is_game_restart", default=False)) or str(raw_reason).casefold() in {"game_commencing", "15"},
                is_complete=_value(row, "winner", "winner_side", "team_num") in {2, 3, "2", "3", "T", "CT"},
                ended_at_tick=tick if tick >= 0 else None, duration_seconds=duration,
            ))
        return ParsedDemo(
            map_result=ParsedMapResult(
                raw_map_name=str(raw_map_name) if raw_map_name else None,
                team_a_name=ordered[0][0], team_a_score=ordered[0][1],
                team_b_name=ordered[1][0], team_b_score=ordered[1][1],
                # round_end rows are not a reliable independent completed-round
                # counter in demoparser2 (restarts/duplicate service events occur).
                # The normalized service derives rounds_count from the final score.
                parser_rounds_count=None,
                parser_overtime_periods=(1 if any(value > 0 for value in overtime_values) else 0) if overtime_values else None,
            ),
            player_stats=aggregate_player_events(snapshots, death_events, damage_events),
            rounds=parsed_rounds,
        )
