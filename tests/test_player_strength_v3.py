from types import SimpleNamespace

import pytest

from cs2eye.services.player_strength_v3_service import (
    MECHANICAL_WEIGHTS,SUPPORTING_WEIGHTS,_aggregate,_block,opponent_rank_group_v3,
)


@pytest.mark.parametrize(("rank","expected"),[(10,"top_1_10"),(11,"top_11_20"),(20,"top_11_20"),(21,"top_21_30"),(30,"top_21_30"),(31,"others"),(None,"unknown")])
def test_v3_rank_group_boundaries(rank,expected):
    assert opponent_rank_group_v3(rank)==expected


def row(*,kills=20,deaths=10,rounds=24,utility=None,combat=None):
    return SimpleNamespace(kills=kills,deaths=deaths,rounds_played=rounds,total_damage=1800,utility_data=utility,combat_data=combat)


def test_supporting_separates_equal_mechanical_players_and_penalizes_team_flashes():
    good={"flash_assists":6,"flash_thrown":10,"enemies_flashed":14,"enemy_flash_duration":25,"utility_damage":240,"teammates_flashed":1}
    poor={"flash_assists":1,"flash_thrown":10,"enemies_flashed":3,"enemy_flash_duration":4,"utility_damage":72,"teammates_flashed":8}
    a=_aggregate([row(utility=good,combat={"trade_kills":7,"trade_opportunities":10})])
    b=_aggregate([row(utility=poor,combat={"trade_kills":3,"trade_opportunities":10})])
    refs={key:[a[key],b[key]] for key in MECHANICAL_WEIGHTS|SUPPORTING_WEIGHTS}
    mechanical_a=_block(a,MECHANICAL_WEIGHTS,refs,reliability=.2)
    mechanical_b=_block(b,MECHANICAL_WEIGHTS,refs,reliability=1.)
    support_a=_block(a,SUPPORTING_WEIGHTS,refs,inverse={"teammates_flashed_per_flash"},reliability=.2)
    support_b=_block(b,SUPPORTING_WEIGHTS,refs,inverse={"teammates_flashed_per_flash"},reliability=1.)
    assert mechanical_a["score"]==mechanical_b["score"]
    assert support_a["score"]>support_b["score"]
    # Reliability is reported separately and never shrinks the score.
    assert mechanical_a["score"]==_block(a,MECHANICAL_WEIGHTS,refs,reliability=1.)["score"]


def test_missing_support_is_not_zero():
    metrics=_aggregate([row()]);refs={key:[metrics[key]] for key in MECHANICAL_WEIGHTS if metrics[key] is not None}
    supporting=_block(metrics,SUPPORTING_WEIGHTS,refs,reliability=0.)
    assert supporting["score"] is None
    assert all(not factor["available"] for factor in supporting["factors"])


def test_distribution_normalization_preserves_elite_distance():
    from cs2eye.services.player_strength_v3_service import _normalize
    population=[.40,.45,.50,.55,.60,.65,.70,.72,.75,.90]
    assert _normalize(.90,population)>_normalize(.72,population)


def test_flash_efficiency_is_weighted_by_flashes_not_maps_or_rounds():
    many=row(rounds=20,utility={"flash_thrown":100,"enemies_flashed":100,"flash_assists":0,"enemy_flash_duration":0,"utility_damage":0,"teammates_flashed":0})
    few=row(rounds=20,utility={"flash_thrown":1,"enemies_flashed":0,"flash_assists":0,"enemy_flash_duration":0,"utility_damage":0,"teammates_flashed":0})
    assert _aggregate([many,few])["enemies_flashed_per_flash"]==pytest.approx(100/101)


def test_trading_is_weighted_by_opportunities():
    many=row(combat={"trade_kills":50,"trade_opportunities":100})
    few=row(combat={"trade_kills":1,"trade_opportunities":1})
    assert _aggregate([many,few])["trade_success_rate"]==pytest.approx(51/101)
