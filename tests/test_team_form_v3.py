from datetime import date

import pytest

from cs2eye.services.performance_profile_service import rank_group_v3
from cs2eye.services.performance_vs_expectation_service import PerformanceVsExpectationService
from cs2eye.services.team_form_v3_service import (
    aggregate_events, effective_component_weights, eligible_event,
    form_rank_strength, freshness_weight, partition_events, resolve_expectation,
    same_five_player_roster, scope_reliability, series_data_complete, series_scores, series_won, tournament_weight_limit,
    within_form_window,
)


PVE = PerformanceVsExpectationService()


def performance(own, opponent, won, diff, maps=3, fmt="bo3"):
    return PVE.evaluate(own_strength=own, opponent_strength=opponent,
                        won=won, round_diff=diff, maps=maps, bo_format=fmt)


def event(key, contribution, *, age=5, tournament=1, maps=2, rounds=45,
          source="historical_team_strength_v3"):
    return {"series_key": key, "form_contribution": contribution,
            "age_days": age, "format": "bo3", "maps": maps,
            "rounds": rounds, "tournament_id": tournament,
            "expectation_source": source, "expectation_coverage": 1.0,
            "data_complete": True, "date": date(2026, 2, 20)}


def scope(events, recent=True):
    value = aggregate_events(events, recent=recent)
    value["reliability"] = 80
    return value


def test_three_expected_wins_over_weak_opponents_are_not_extreme_form():
    contributions = [performance(88, 42, True, diff)["form_contribution"]
                     for diff in (3, 5, 7)]
    value = aggregate_events([event(str(i), x) for i, x in enumerate(contributions)], recent=True)
    assert -5 < value["delta"] < 8


def test_routine_convincing_win_is_not_negative_due_to_scale_mismatch():
    own = form_rank_strength(1)
    opponent = form_rank_strength(32)
    assert performance(own, opponent, True, 11, maps=2)["form_contribution"] >= 0


def test_top5_upset_win_is_strong_positive():
    assert performance(58, 92, True, 5)["form_contribution"] > 12


def test_close_loss_to_top3_is_better_than_same_loss_to_rank50():
    top = performance(58, 94, False, -2)["form_contribution"]
    weak = performance(85, 40, False, -2)["form_contribution"]
    assert top > weak


def test_loss_to_weak_team_is_strong_negative():
    assert performance(88, 42, False, -12)["form_contribution"] <= -15


def test_current_tournament_is_excluded_from_recent_60d():
    values = [event("a", 8, tournament=7), event("b", 2, tournament=6)]
    tournament, recent = partition_events(values, 7)
    assert [x["series_key"] for x in tournament] == ["a"]
    assert [x["series_key"] for x in recent] == ["b"]
    assert not {x["series_key"] for x in tournament} & {x["series_key"] for x in recent}


def test_old_current_tournament_event_is_kept_but_old_recent_event_is_not():
    cutoff = date(2026, 4, 30)
    values = [event("t", 8, tournament=7), event("r", 2, tournament=6)]
    tournament, recent = partition_events(values, 7, cutoff)
    assert [x["series_key"] for x in tournament] == ["t"]
    assert recent == []


def test_one_tournament_series_cannot_take_all_weight():
    tournament, recent = scope([event("t", 10)], False), scope([event("r", 2)])
    weights = effective_component_weights(tournament, recent)
    assert weights["current_tournament"] <= .25


def test_three_tournament_series_increase_tournament_weight():
    recent = scope([event("r", 2)])
    one = effective_component_weights(scope([event("t", 10)], False), recent)
    three = effective_component_weights(scope([event(str(i), 10) for i in range(3)], False), recent)
    assert three["current_tournament"] > one["current_tournament"]
    assert tournament_weight_limit(10) <= .60


def test_new_roster_has_low_reliability_without_changing_delta():
    value = aggregate_events([event("a", 12)], recent=True)
    reliability, _ = scope_reliability(value, candidate_maps=10)
    assert value["delta"] == 12 and reliability < 50


def test_large_complete_sample_has_high_reliability():
    values = [event(str(i), 3, maps=2, rounds=50) for i in range(8)]
    value = aggregate_events(values, recent=True)
    reliability, _ = scope_reliability(value, candidate_maps=16)
    assert reliability > 95


def test_matches_older_than_60_days_are_outside_window_contract():
    cutoff = date(2026, 3, 3)
    assert within_form_window(date(2026, 1, 2), cutoff)
    assert not within_form_window(date(2026, 1, 1), cutoff)


def test_empty_sample_is_unavailable_not_fake_neutral_50():
    value = aggregate_events([], recent=True)
    assert value["delta"] is None and value["score"] is None
    assert value["available"] is False


def test_same_five_players_are_current_roster_even_with_another_snapshot_id():
    assert same_five_player_roster({1, 2, 3, 4, 5}, {5, 4, 3, 2, 1})
    assert not same_five_player_roster({1, 2, 3, 4, 5}, {1, 2, 3, 4, 6})
    assert not same_five_player_roster({1, 2, 3, 4}, {1, 2, 3, 4})


def test_freshness_weighting_is_moderate_and_monotonic():
    assert freshness_weight(0) == freshness_weight(14) == 1
    assert freshness_weight(14) > freshness_weight(30) > freshness_weight(60)
    assert freshness_weight(30) == pytest.approx(.75)
    assert freshness_weight(60) == pytest.approx(.45)


def test_ranking_boundaries():
    assert [rank_group_v3(x) for x in (10, 11, 20, 21, 30, 31, None)] == [
        "top_1_10", "top_11_20", "top_11_20", "top_21_30",
        "top_21_30", "others", "unknown"]


def test_unknown_ranking_uses_neutral_expectation_and_marks_source():
    own, opponent, source = resolve_expectation(None, None, None, None)
    assert (own, opponent, source) == (50, 50, "unknown")


def test_partial_ranking_fallback_is_explicit():
    own, opponent, source = resolve_expectation(None, None, None, 5)
    assert own == opponent == 50
    assert source == "partial_historical_ranking_fallback"


def test_rank_fallback_does_not_turn_top_vs_others_into_near_certainty():
    own, opponent, source = resolve_expectation(None, None, 1, 32)
    probability = PVE.expected_win_probability(own, opponent)
    assert source == "historical_ranking_fallback"
    assert .80 < probability < .95


def test_historical_team_strength_is_preferred_then_ranking_fallback():
    assert resolve_expectation(80, 70, 20, 30) == (
        80, 70, "historical_team_strength_v3")
    own, opponent, source = resolve_expectation(None, None, 20, 5)
    assert own is not None and opponent is not None
    assert source == "historical_ranking_fallback"


def test_as_of_is_strict_and_same_day_is_excluded():
    cutoff = date(2026, 5, 10)
    assert eligible_event(date(2026, 5, 9), cutoff, 1, None)
    assert not eligible_event(cutoff, cutoff, 1, None)
    assert not eligible_event(date(2026, 5, 11), cutoff, 1, None)


def test_analyzed_series_is_excluded():
    assert not eligible_event(date(2026, 5, 9), date(2026, 5, 10), 42, 42)


def test_one_series_produces_one_aggregate_event_not_one_per_map():
    value = aggregate_events([event("match:42", 6, maps=3)], recent=True)
    assert value["series"] == 1 and value["maps"] == 3


def test_incomplete_series_maps_cannot_mix_series_result_with_partial_rounds():
    assert series_data_complete(3, 3)
    assert not series_data_complete(1, 3)


def test_actual_series_result_comes_from_demo_maps_not_match_metadata():
    assert series_won(0, 1) is False
    assert series_won(2, 1) is True
    assert series_won(1, 1) is None


def test_series_aggregation_handles_team_side_swaps_between_maps():
    class Result:
        def __init__(self, team_a_id, team_b_id, team_a_score, team_b_score):
            self.team_a_id = team_a_id; self.team_b_id = team_b_id
            self.team_a_score = team_a_score; self.team_b_score = team_b_score

    maps = [Result(3, 11, 13, 8), Result(11, 3, 7, 13)]
    assert series_scores(3, maps) == (26, 15, 2, 0)


def test_bo1_has_less_aggregation_weight_than_bo3():
    bo1 = event("a", 5); bo1["format"] = "bo1"
    bo3 = event("b", 5); bo3["format"] = "bo3"
    value = aggregate_events([bo1, bo3], recent=True)
    weights = {x["series_key"]: x["aggregation_weight"] for x in value["events"]}
    assert weights["a"] < weights["b"]
