from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from cs2eye.services.opponent_adjusted_results_service import (
    adjusted_map_quality, eligible_historical_event, opponent_rank_strength,
    roster_applicability,
)
from cs2eye.services.performance_profile_service import rank_group_v3
from cs2eye.services.team_strength_v3_service import (
    compose_score, execution_quality, reliability_score, roster_quality,
)


def players(scores, reliability=1):
    return [{"id": i, "nickname": str(i), "player_strength_v3": score,
             "mechanical_strength": score, "supporting_strength": score,
             "reliability": reliability} for i, score in enumerate(scores)]


def test_even_strong_five():
    assert roster_quality(players([90]*5))["score"] == 90


def test_two_stars_and_weak_bottom_are_visible():
    value = roster_quality(players([99, 95, 88, 72, 65]))
    assert value["avg_top_2"] == 97 and value["avg_bottom_2"] == 68.5


def test_supporting_is_carried_only_inside_player_strength():
    value = roster_quality(players([80]*5))
    assert value["players"][0]["supporting_strength"] == 80


def profile(**scores):
    defaults = {"trading": 50, "utility": 50, "opening": 50, "entrying": 50, "clutching": 50}
    defaults.update(scores)
    metrics = {key: {"score": value, "reliability": 80, "sample_size": 100} for key, value in defaults.items()}
    metrics.update({"firepower": {"score": 100, "reliability": 100, "sample_size": 100},
                    "sniping": {"score": 0, "reliability": 100, "sample_size": 100}})
    return {"scopes": {"overall": metrics}}


def test_high_trading_and_utility_raise_execution():
    assert execution_quality(profile(trading=90, utility=90))["score"] > 70


def test_firepower_does_not_rescue_bad_execution():
    assert execution_quality(profile(trading=20, utility=20, opening=20, entrying=20, clutching=20))["score"] == 20


def test_top5_win_is_more_valuable_than_outside30_win():
    assert adjusted_map_quality(won=True, round_diff=3, opponent_rank=5)["score"] > adjusted_map_quality(won=True, round_diff=3, opponent_rank=50)["score"]


def test_top5_loss_is_less_bad_than_outside30_loss():
    assert adjusted_map_quality(won=False, round_diff=-3, opponent_rank=5)["score"] > adjusted_map_quality(won=False, round_diff=-3, opponent_rank=50)["score"]


def test_round_differential_changes_quality_but_not_more_than_result():
    assert adjusted_map_quality(won=True, round_diff=10, opponent_rank=10)["score"] > adjusted_map_quality(won=True, round_diff=1, opponent_rank=10)["score"]


def test_unknown_ranking_is_supported_without_fake_strength():
    value = adjusted_map_quality(won=True, round_diff=2, opponent_rank=None)
    assert value["score"] is not None and value["opponent_strength"] is None


def test_ranking_boundaries():
    assert [rank_group_v3(x) for x in (10,11,20,21,30,31,None)] == ["top_1_10","top_11_20","top_11_20","top_21_30","top_21_30","others","unknown"]


def test_missing_performance_metric_renormalizes_without_inventing_value():
    value = profile(); value["scopes"]["overall"]["utility"]["score"] = None
    result = execution_quality(value)
    assert result["coverage"] == .7 and result["score"] == 50


def test_roster_count_reliability_is_separate_from_score():
    five = roster_quality(players([84]*5)); three = roster_quality(players([84]*3))
    assert five["score"] == three["score"] == 84
    assert five["reliability"] > three["reliability"]


def test_opponent_strength_monotonic():
    assert opponent_rank_strength(1) > opponent_rank_strength(30) > opponent_rank_strength(60)


def test_as_of_excludes_future_and_same_day_events():
    cutoff = date(2026, 9, 2)
    assert eligible_historical_event(date(2026, 9, 1), cutoff, 1)
    assert not eligible_historical_event(cutoff, cutoff, 2)
    assert not eligible_historical_event(date(2026, 9, 3), cutoff, 3)


def test_analyzed_series_is_excluded():
    assert not eligible_historical_event(date(2026, 9, 1), date(2026, 9, 2), 42, 42)


def test_strength_formula_has_no_opponent_input():
    # Roster quality is identical regardless of which comparison page consumes it.
    first = roster_quality(players([80, 81, 82, 83, 84]))
    second = roster_quality(players([80, 81, 82, 83, 84]))
    assert first == second


def test_old_organisation_history_does_not_penalize_selected_current_roster_rows():
    assert roster_applicability(10, 10, 5) == "current"
    assert roster_applicability(9, 10, 3) == "partial"
    assert roster_applicability(8, 10, 2) == "old"


def result_sample(*, maps=20, matches=8, rounds=300, ranking=100, latest=date(2026, 9, 1)):
    return {"sample": {"current_roster_maps": maps, "current_roster_matches": matches,
            "selected_rounds": rounds, "selected_maps": maps, "effective_maps": maps,
            "effective_rounds": rounds, "ranking_coverage": ranking,
            "latest_current_roster_map_date": latest}}


def test_new_roster_changes_reliability_not_score():
    components = {"roster_quality": {"score": 88}, "team_execution": {"score": 80},
                  "results_quality": {"score": 82}}
    score, _ = compose_score(components)
    stable, _ = reliability_score(roster={"reliability": 90}, execution={"coverage": 1, "reliability": 90},
                                  results=result_sample(), cutoff=date(2026, 9, 2))
    new, _ = reliability_score(roster={"reliability": 90}, execution={"coverage": .4, "reliability": 40},
                               results=result_sample(maps=4, matches=2, rounds=80), cutoff=date(2026, 9, 2))
    assert score == 84.2
    assert stable > new


def test_missing_team_performance_profile_does_not_invent_execution_score():
    missing = profile()
    for metric in missing["scopes"]["overall"].values(): metric["score"] = None
    execution = execution_quality(missing)
    assert execution["score"] is None and execution["reliability"] == 0
    score, coverage = compose_score({"roster_quality": {"score": 80},
                                     "team_execution": execution,
                                     "results_quality": {"score": 80}})
    assert score == 80 and coverage == .75


def test_stable_roster_has_high_reliability_when_all_sources_are_covered():
    reliability, breakdown = reliability_score(
        roster={"reliability": 100}, execution={"coverage": 1, "reliability": 100},
        results=result_sample(), cutoff=date(2026, 9, 2))
    assert reliability > 99
    assert set(breakdown) == {"player_strength", "current_roster_maps", "current_roster_matches",
        "rounds", "team_performance_profile", "opponent_rankings", "results_coverage",
        "roster_data_relevance"}


def test_compare_opponent_cannot_change_team_strength_v3():
    components = {"roster_quality": {"score": 87}, "team_execution": {"score": 81},
                  "results_quality": {"score": 79}}
    versus_vitality = compose_score(components)[0]
    versus_spirit = compose_score(components)[0]
    assert versus_vitality == versus_spirit


def test_more_than_five_players_also_reduces_roster_reliability():
    five = roster_quality(players([80] * 5))
    six = roster_quality(players([80] * 6))
    assert five["score"] == six["score"] == 80
    assert six["reliability"] < five["reliability"]


def test_partial_roster_evidence_has_half_reliability_coverage():
    full = result_sample(maps=10, rounds=200)
    partial = result_sample(maps=10, rounds=200)
    partial["sample"].update(effective_maps=5, effective_rounds=100)
    full_rel, _ = reliability_score(roster={"reliability": 80},
        execution={"coverage": .8, "reliability": 80}, results=full,
        cutoff=date(2026, 9, 2))
    partial_rel, _ = reliability_score(roster={"reliability": 80},
        execution={"coverage": .8, "reliability": 80}, results=partial,
        cutoff=date(2026, 9, 2))
    assert partial_rel < full_rel


def test_snapshot_repair_migration_works_after_0046_and_is_idempotent():
    path = Path(__file__).parents[1] / "alembic/versions/0047_team_strength_v3_snapshot_repair.py"
    spec = spec_from_file_location("migration_0047_team_strength", path)
    migration = module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE teams (id INTEGER PRIMARY KEY)"))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        migration.upgrade()
        assert "team_strength_v3_snapshots" in inspect(connection).get_table_names()
