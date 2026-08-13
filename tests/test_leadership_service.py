from cs2eye.analytics.leadership_config import COACH_WEIGHTS,IGL_WEIGHTS
from cs2eye.services.leadership_service import calculate_coach,calculate_igl,expected_performance

def igl(**kw):
    data=dict(actual=60,expected=50,maps=20,t_side=55,full_buy=55,force_vs_full=50,anti_eco=60,opening_conversion=55,opening_recovery=50,postplant=55,trade=50,strong=55);data.update(kw);return calculate_igl(**data)
def coach(**kw):
    data=dict(actual=60,expected=50,maps=30,veto_quality=55,map_development=55,opponent_prep=55,player_development=None,consistency=55);data.update(kw);return calculate_coach(**data)

def test_igl_weights_sum_to_one():assert sum(IGL_WEIGHTS.values())==1
def test_coach_weights_sum_to_one():assert sum(COACH_WEIGHTS.values())==1
def test_player_strength_is_not_igl_input():assert "player_strength" not in igl()
def test_strong_player_does_not_guarantee_igl():assert igl(actual=40,expected=70)["score"]<igl(actual=60,expected=50)["score"]
def test_t_side_quality_influences_igl():assert igl(t_side=80)["score"]>igl(t_side=20)["score"]
def test_opening_conversion_influences_igl():assert igl(opening_conversion=90)["score"]>igl(opening_conversion=20)["score"]
def test_opening_recovery_influences_igl():assert igl(opening_recovery=90)["score"]>igl(opening_recovery=20)["score"]
def test_full_buy_influences_igl():assert igl(full_buy=90)["score"]>igl(full_buy=20)["score"]
def test_postplant_influences_igl():assert igl(postplant=90)["score"]>igl(postplant=20)["score"]
def test_missing_igl_factor_is_not_zero():
    result=igl(postplant=None);f=next(x for x in result["factors"] if x["key"]=="postplant");assert not f["available"] and f["effective_weight"]==0
def test_small_igl_sample_reduces_reliability():assert igl(maps=2)["reliability"]<igl(maps=30)["reliability"]
def test_expected_performance_excludes_management():assert expected_performance([60]*5,[70],50)==61.5
def test_overperformance_raises_coach():assert coach(actual=65,expected=45)["score"]>coach(actual=45,expected=65)["score"]
def test_raw_winrate_is_not_coach_impact():assert coach(actual=70,expected=75)["score"]<coach(actual=60,expected=45)["score"]
def test_veto_quality_influences_coach():assert coach(veto_quality=90)["score"]>coach(veto_quality=20)["score"]
def test_missing_veto_does_not_penalize_coach():
    result=coach(veto_quality=None);f=next(x for x in result["factors"] if x["key"]=="veto_quality");assert not f["available"] and f["effective_weight"]==0
def test_map_development_influences_coach():assert coach(map_development=90)["score"]>coach(map_development=20)["score"]
def test_roster_change_reduces_attribution_confidence():assert coach(roster_change_penalty=.4)["reliability"]<coach(roster_change_penalty=1)["reliability"]
def test_small_coach_sample_low_reliability():assert coach(maps=3)["reliability"]<coach(maps=40)["reliability"]
def test_timeout_is_explicitly_unavailable():assert coach()["timeout_effectiveness"]["status"]=="not_available"
def test_management_residual_is_actual_minus_expected():assert igl(actual=58,expected=52)["management_residual"]==6
