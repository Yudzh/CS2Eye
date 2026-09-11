from cs2eye.services.performance_normalization_service import PerformanceNormalizationService
from cs2eye.services.performance_profile_service import _raw_profile, rank_group_v3


def profile(**overrides):
    values = dict(rounds=500, kills=350, deaths=300, damage=40000, awp_kills=0,
                  combat={"opening_kills": 30, "opening_deaths": 20, "opening_attempts": 50,
                          "trade_kills": 30, "trade_opportunities": 100, "deaths_traded": 80,
                          "deaths_not_traded": 220, "clutch_opportunities": 10, "clutch_wins": 3,
                          "clutch_1v1_attempts": 6, "clutch_1v1_wins": 2,
                          "clutch_1v3_attempts": 4, "clutch_1v3_wins": 1},
                  utility={"rounds": 500, "flash_assists_per_round": .05,
                           "enemies_flashed_per_flash": 1.1, "enemy_flash_seconds_per_flash": 2.5,
                           "utility_damage_per_round": 4., "teammates_flashed_per_flash": .5},
                  scope="overall", maps=20)
    values.update(overrides)
    return _raw_profile(**values)


def test_rifler_sniping_is_zero_metric_without_affecting_firepower():
    value = profile(awp_kills=0)
    assert value["sniping"]["metrics"]["awp_kills_per_round"] == 0
    assert value["firepower"]["metrics"]["kills_per_round"] == .7


def test_awper_has_high_raw_sniping():
    assert profile(awp_kills=250)["sniping"]["metrics"]["awp_kills_per_round"] == .5


def test_high_firepower_keeps_raw_components():
    value = profile(kills=500, damage=60000, deaths=200)["firepower"]["metrics"]
    assert value == {"kills_per_round": 1., "adr": 120., "survival_rate": .6}


def test_high_utility_is_independent_from_firepower():
    low = profile(utility={"rounds": 500, "flash_assists_per_round": .01})
    high = profile(utility={"rounds": 500, "flash_assists_per_round": .2})
    assert low["firepower"] == high["firepower"]
    assert high["utility"]["metrics"]["flash_assists_per_round"] > low["utility"]["metrics"]["flash_assists_per_round"]


def test_entry_is_t_opening_based_and_documents_limitation():
    value = profile(scope="t")
    assert value["entrying"]["weights"]["t_opening_attempts_per_round"] == .55
    assert "opening contacts" in value["entrying"]["limitation"]


def test_opening_score_is_raw_and_sample_only_affects_reliability():
    tiny = profile(combat={"opening_kills": 2, "opening_deaths": 0, "opening_attempts": 2})
    assert tiny["opening"]["metrics"]["opening_success"] == 1.0


def test_trading_is_based_on_opportunities():
    assert profile()["trading"]["metrics"]["trade_success_rate"] == .3


def test_friendly_flash_is_inverse_factor():
    assert "teammates_flashed_per_flash" in profile()["utility"]["inverse"]


def test_clutch_1v1_is_recorded():
    assert profile()["clutching"]["situations"]["1v1"] == {"attempts": 6, "wins": 2}


def test_clutch_1v3_has_larger_difficulty_weight():
    only_1v1 = profile(combat={"clutch_opportunities": 1, "clutch_1v1_attempts": 1, "clutch_1v1_wins": 1})
    only_1v3 = profile(combat={"clutch_opportunities": 1, "clutch_1v3_attempts": 1, "clutch_1v3_wins": 1})
    assert only_1v3["clutching"]["metrics"]["difficulty_weighted_clutch_rate"] > only_1v1["clutching"]["metrics"]["difficulty_weighted_clutch_rate"]


def test_side_trading_and_clutch_use_side_combat_counters():
    combat = {"available": True, "trade_kills": 3, "trade_opportunities": 10,
              "deaths_traded": 4, "deaths_not_traded": 6, "clutch_opportunities": 2,
              "clutch_1v1_attempts": 1, "clutch_1v1_wins": 1,
              "clutch_1v3_attempts": 1, "clutch_1v3_wins": 0}
    value = profile(scope="ct", combat=combat)
    assert value["trading"]["metrics"]["trade_success_rate"] == .3
    assert value["clutching"]["sample"] == 2


def test_missing_utility_stays_unavailable():
    assert all(value is None for value in profile(utility={"rounds": 0})["utility"]["metrics"].values())


def test_missing_combat_does_not_invent_trading():
    assert profile(combat={})["trading"]["metrics"]["trade_success_rate"] is None


def test_score_and_reliability_are_not_coupled():
    assert PerformanceNormalizationService.score(90, [10, 50, 90]) == PerformanceNormalizationService.score(90, [10, 50, 90])


def test_normalizer_separates_high_and_low_values():
    assert PerformanceNormalizationService.score(90, [10, 50, 90]) > PerformanceNormalizationService.score(10, [10, 50, 90])


def test_v3_rank_boundaries():
    assert [(x, rank_group_v3(x)) for x in (10, 11, 20, 21, 30, 31, None)] == [
        (10, "top_1_10"), (11, "top_11_20"), (20, "top_11_20"),
        (21, "top_21_30"), (30, "top_21_30"), (31, "others"), (None, "unknown")]
