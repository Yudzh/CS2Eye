from cs2eye.analytics.combat.config import TRADE_WINDOW_TICKS
from cs2eye.analytics.combat.core import CombatKill, calculate_combat
from cs2eye.services.demo_combat_service import _event_round, _is_enemy_player_death, _post_round_event_round
from cs2eye.services.demo_parser_service import DeathEvent, PlayerRef
from types import SimpleNamespace


ROSTERS = {"A": {"a1", "a2", "a3", "a4", "a5"}, "B": {"b1", "b2", "b3", "b4", "b5"}}


def test_kill_binding_prefers_normalized_tick_interval_over_shifted_ordinal():
    rounds = [
        SimpleNamespace(round_number=1, started_at_tick=100, ended_at_tick=200),
        SimpleNamespace(round_number=2, started_at_tick=300, ended_at_tick=400),
    ]
    # Parser ordinal 3 was shifted by a duplicate round_end, but the physical
    # event belongs to normalized round 2.
    assert _event_round(rounds, 350, 3).round_number == 2
    assert _event_round(rounds, 450, 3) is None


def test_post_round_tick_binds_only_before_next_round_start():
    rounds = [
        SimpleNamespace(round_number=1, started_at_tick=100, ended_at_tick=200),
        SimpleNamespace(round_number=2, started_at_tick=300, ended_at_tick=400),
    ]
    assert _post_round_event_round(rounds, 250).round_number == 1
    assert _post_round_event_round(rounds, 350) is None


def test_unbound_bomb_world_death_is_not_enemy_kill():
    victim = PlayerRef("1", "victim", "A", 2)
    enemy = PlayerRef("2", "enemy", "B", 3)
    assert not _is_enemy_player_death(DeathEvent(1, victim, None, None, 100, "planted_c4"))
    assert not _is_enemy_player_death(DeathEvent(1, victim, victim, None, 100, "world"))
    assert _is_enemy_player_death(DeathEvent(1, victim, enemy, None, 100, "ak47"))


def kill(tick, attacker, victim, attacker_team="A", victim_team="B", *, round_number=1,
         attacker_side="T", victim_side="CT", teamkill=False, suicide=False):
    return CombatKill(round_number, tick, attacker, victim, attacker_team, victim_team,
                      attacker_side, victim_side, is_teamkill=teamkill, is_suicide=suicide)


def test_first_enemy_kill_is_opening_and_conversion():
    events, players, teams, issues = calculate_combat([kill(100, "a1", "b1")], ROSTERS, {1: "A"})
    assert not issues and events[0].is_opening_kill
    assert players["a1"]["opening_kills"] == 1
    assert players["b1"]["opening_deaths"] == 1
    assert teams["A"]["opening_conversion_wins"] == 1
    assert teams["B"]["opening_recovery_losses"] == 1
    assert players["a1"]["t_opening_kills"] == 1


def test_invalid_deaths_are_not_opening():
    invalid = [
        kill(10, None, "b1", None, "B"),
        kill(20, "b1", "b1", "B", "B", suicide=True),
        kill(30, "b2", "b1", "B", "B", teamkill=True),
    ]
    events, _, teams, _ = calculate_combat(invalid + [kill(40, "a1", "b3")], ROSTERS, {1: "B"})
    assert [event.is_opening_kill for event in events] == [False, False, False, True]
    assert teams["A"]["opening_conversion_losses"] == 1
    assert teams["B"]["opening_recovery_wins"] == 1


def test_trade_window_intermediate_kill_and_single_was_traded():
    source = [kill(100, "a1", "b1"), kill(120, "b2", "a2", "B", "A", attacker_side="CT", victim_side="T"),
              kill(130, "b3", "a1", "B", "A", attacker_side="CT", victim_side="T"),
              kill(140, "b4", "a1", "B", "A", attacker_side="CT", victim_side="T")]
    events, players, teams, _ = calculate_combat(source, ROSTERS, {1: "B"})
    assert events[2].is_trade_kill and events[0].was_traded
    assert not events[3].is_trade_kill
    assert players["b3"]["trade_kills"] == 1
    assert teams["B"]["trade_kills"] == 1


def test_revenge_after_window_or_other_round_is_not_trade():
    source = [kill(100, "a1", "b1"),
              kill(101 + TRADE_WINDOW_TICKS, "b2", "a1", "B", "A", attacker_side="CT", victim_side="T"),
              kill(110, "b3", "a1", "B", "A", round_number=2, attacker_side="CT", victim_side="T")]
    events, _, _, _ = calculate_combat(source, ROSTERS, {1: "A", 2: "B"})
    assert not any(event.is_trade_kill for event in events)


def test_trade_chain_counts_two_source_deaths():
    source = [kill(100, "a1", "b1"),
              kill(120, "b2", "a1", "B", "A", attacker_side="CT", victim_side="T"),
              kill(140, "a3", "b2")]
    events, _, _, _ = calculate_combat(source, ROSTERS, {1: "A"})
    assert [event.is_trade_kill for event in events] == [False, True, True]
    assert [event.was_traded for event in events] == [True, True, False]


def test_1v3_transition_is_one_clutch_and_win():
    source = [kill(10, "b1", "a1", "B", "A"), kill(20, "b2", "a2", "B", "A"),
              kill(30, "b3", "a3", "B", "A"), kill(40, "b4", "a4", "B", "A"),
              kill(50, "a5", "b1"), kill(60, "a5", "b2"), kill(70, "a5", "b3"),
              kill(80, "a5", "b4"), kill(90, "a5", "b5")]
    _, players, teams, _ = calculate_combat(source, ROSTERS, {1: "A"})
    # At clutch start all five opponents are alive; later 1vX transitions do not add attempts.
    assert players["a5"]["clutch_opportunities"] == 1
    assert players["a5"]["clutch_1v5_attempts"] == 1
    assert players["a5"]["clutch_1v5_wins"] == 1
    assert teams["A"]["clutch_wins"] == 1


def test_1v1_loss_and_empty_rates_are_null():
    rosters = {"A": {"a1", "a2"}, "B": {"b1", "b2"}}
    source = [kill(10, "a1", "b1"),
              kill(20, "b2", "a1", "B", "A", attacker_side="CT", victim_side="T"),
              kill(30, "b2", "a2", "B", "A", attacker_side="CT", victim_side="T")]
    _, players, teams, _ = calculate_combat(source, rosters, {1: "B"})
    assert players["a2"]["clutch_1v1_attempts"] == 1
    assert players["a2"]["clutch_losses"] == 1
    assert teams["A"]["clutch_win_rate"] == 0
    _, empty_players, _, _ = calculate_combat([], rosters, {})
    assert empty_players == {}
