import pytest

from cs2eye.analytics.calculated_veto_config import CALCULATED_VETO_MODEL_VERSION
from cs2eye.services.calculated_veto_service import MapSignals, _blend_rate, action_propensity, blend_signals, bounded_probabilities, calculate_map_pair, exact_veto_tree, mix_veto_trees, simulate, veto_raw_probability

def sig(strength=50, maps=10, recent=50, **kw):
    return MapSignals(strength=strength,strength_confidence=90,maps=maps,freshness=90,recent=recent,ct=50,t=50,**kw)

def score(a,b): return calculate_map_pair(a,b)

def test_strong_own_map_raises_pick_score():
    assert score(sig(85),sig(50))["team_a"]["calculated_pick_score"] > score(sig(55),sig(50))["team_a"]["calculated_pick_score"]

def test_strong_opponent_lowers_pick_and_raises_ban():
    weak=score(sig(70),sig(50))["team_a"];threat=score(sig(70),sig(90))["team_a"]
    assert threat["calculated_pick_score"]<weak["calculated_pick_score"]
    assert threat["calculated_ban_score"]>weak["calculated_ban_score"]

def test_own_weakness_raises_ban():
    assert score(sig(30),sig(60))["team_a"]["calculated_ban_score"]>score(sig(70),sig(60))["team_a"]["calculated_ban_score"]

def test_recent_form_affects_matchup():
    assert score(sig(60,recent=90),sig(60))["team_a"]["matchup_map_score"]>score(sig(60,recent=30),sig(60))["team_a"]["matchup_map_score"]

def test_roster_large_sample_has_priority():
    value=blend_signals(sig(40,maps=20),sig(90,maps=20));assert value.strength>70 and value.roster_share>.75

def test_small_roster_sample_blends_organization():
    value=blend_signals(sig(40,maps=20),sig(90,maps=2));assert 40<value.strength<60

def test_missing_metric_is_unavailable_not_zero():
    result=score(MapSignals(strength=60,maps=5,strength_confidence=60),sig(50));factor=next(x for x in result["team_a"]["matchup_factors"] if x["key"]=="bomb_matchup")
    assert factor["score"] is None and factor["effective_weight"]==0

def test_historical_pick_preference_affects_pick():
    low=sig(60,pick_preference=10,veto_series=20);high=sig(60,pick_preference=90,veto_series=20)
    assert score(high,sig())["team_a"]["calculated_pick_score"]>score(low,sig())["team_a"]["calculated_pick_score"]

def test_historical_ban_preference_affects_ban():
    low=sig(60,ban_preference=10,veto_series=20);high=sig(60,ban_preference=90,veto_series=20)
    assert score(high,sig())["team_a"]["calculated_ban_score"]>score(low,sig())["team_a"]["calculated_ban_score"]

def test_score_is_analytical_not_probability():
    result=score(sig(70),sig(50));assert "calculated_pick_score" in result["team_a"] and "probability" not in result["team_a"]

def test_small_h2h_cannot_dominate():
    a=sig(70,h2h_score=0,h2h_maps=1);assert score(a,sig(50))["team_a"]["matchup_map_score"]>50

def test_postplant_vs_retake_cross_matchup():
    good=sig(postplant=80,retake=60);bad=sig(postplant=40,retake=20)
    assert score(good,bad)["team_a"]["matchup_map_score"]>score(bad,good)["team_a"]["matchup_map_score"]

def test_ct_t_cross_matchup():
    good=sig();good.ct=80;good.t=80;bad=sig();bad.ct=30;bad.t=30
    assert score(good,bad)["team_a"]["matchup_map_score"]>score(bad,good)["team_a"]["matchup_map_score"]

def map_rows():
    return [{"map":name,"team_a":{"calculated_ban_score":ban,"calculated_pick_score":pick},"team_b":{"calculated_ban_score":100-ban,"calculated_pick_score":100-pick}} for name,ban,pick in [("a",99,90),("b",90,80),("c",80,70),("d",70,60),("e",60,50),("f",50,40),("g",40,30)]]

def test_simulation_never_reuses_map():
    actions=simulate(map_rows(),"team_a")["actions"];assert len({x["map"] for x in actions})==len(actions)

def test_decider_is_last_remaining_map():
    actions=simulate(map_rows(),"team_a")["actions"];assert actions[-1]["action"]=="decider" and len(actions)==7

def test_scenarios_differ_by_first_actor():
    assert simulate(map_rows(),"team_a")["actions"]!=simulate(map_rows(),"team_b")["actions"]

def test_collision_uses_pick_vs_opponent_ban():
    result=score(sig(80,pick_preference=90,veto_series=20),sig(30,ban_preference=90,veto_series=20));assert result["collision_score"]>0 and result["collision"] in {"low","medium","high"}

def test_factor_weights_are_mathematical_breakdown():
    factors=score(sig(),sig())["team_a"]["pick_factors"];assert all("weight" in f and "impact" in f for f in factors)

def test_actual_veto_is_not_part_of_simulation_mutation():
    actual=[{"action":"ban","map":"x"}];simulate(map_rows(),"team_a");assert actual==[{"action":"ban","map":"x"}]

def test_inactive_pool_is_service_loader_responsibility():
    # Pure simulator receives the already-filtered active pool and preserves that boundary.
    rows=map_rows();assert all(a["map"] in {x["map"] for x in rows} for a in simulate(rows,"team_a")["actions"])

def test_default_active_pool_matches_premier_season_five():
    from cs2eye.services.calculated_veto_service import DEFAULT_ACTIVE_POOL
    assert DEFAULT_ACTIVE_POOL == {
        "ancient", "anubis", "cache", "dust2", "inferno", "mirage", "nuke",
    }

def test_round_swing_changes_existing_tactical_factor():
    low=sig(combat={"trade":{"trade_rate":50}},swing={"avg_score":25})
    high=sig(combat={"trade":{"trade_rate":50}},swing={"avg_score":75})
    opponent=sig(combat={"trade":{"trade_rate":50}},swing={"avg_score":50})
    low_factor=next(x for x in score(low,opponent)["team_a"]["matchup_factors"] if x["key"]=="economy_combat_matchup")
    high_factor=next(x for x in score(high,opponent)["team_a"]["matchup_factors"] if x["key"]=="economy_combat_matchup")
    assert high_factor["score"] > low_factor["score"]
    assert "Round Swing" in high_factor["reason"]

def test_missing_swing_renormalizes_without_zero_penalty():
    own=sig(combat={"trade":{"trade_rate":60}})
    opponent=sig(combat={"trade":{"trade_rate":50}})
    factor=next(x for x in score(own,opponent)["team_a"]["matchup_factors"] if x["key"]=="economy_combat_matchup")
    assert factor["score"] is not None
    assert "fallback" in factor["reason"]

def test_swing_does_not_create_extra_top_level_factor():
    factors=score(sig(swing={"avg_score":70}),sig(swing={"avg_score":50}))["team_a"]["matchup_factors"]
    assert [item["key"] for item in factors].count("economy_combat_matchup")==1
    assert not any(item["key"]=="round_swing" for item in factors)

def test_calculated_veto_model_version_is_v2():
    assert CALCULATED_VETO_MODEL_VERSION=="v2.1"

def test_bo3_marginals_sum_to_three_and_are_bounded():
    probabilities=bounded_probabilities([10,.9,.8,.7,.2,.1,0],3)
    assert all(0<=value<=1 for value in probabilities)
    assert sum(probabilities)==pytest.approx(3)

def test_uniform_inputs_produce_uniform_bo3_baseline():
    probabilities=bounded_probabilities([1]*7,3)
    assert probabilities==pytest.approx([3/7]*7)

def test_permaban_reduces_probability_and_pick_selection_raise_it():
    neutral=veto_raw_probability(.5,.5,.2,.2,.2,.2,.5)[0]
    permaban=veto_raw_probability(.5,.5,.2,.2,.95,.2,.5)[0]
    popular=veto_raw_probability(.8,.8,.6,.6,.2,.2,.5)[0]
    assert permaban<neutral<popular

def test_map_quality_cannot_dominate_veto_history():
    strong_veto=veto_raw_probability(.8,.8,.5,.5,.1,.1,0)[0]
    weak_veto=veto_raw_probability(.1,.1,.05,.05,.8,.8,1)[0]
    assert strong_veto>weak_veto

def test_roster_and_recent_rates_use_shrinkage():
    org={"eligible_series":30,"selected":{"rate":40}}
    tiny={"eligible_series":2,"selected":{"rate":100}}
    large={"eligible_series":40,"selected":{"rate":100}}
    tiny_value=_blend_rate(org,tiny,None,"selected.rate",3/7)
    large_value=_blend_rate(org,large,None,"selected.rate",3/7)
    recent_value=_blend_rate(org,None,{"eligible_series":5,"selected":{"rate":80}},"selected.rate",3/7)
    assert .4<tiny_value<large_value<1
    assert recent_value>.4

def tree_props(opening:dict[str,float]|None=None,pick:dict[str,float]|None=None):
    names=set("abcdefg");opening=opening or {};pick=pick or {}
    return {side:{role:{name:(opening.get(name,1) if role=="opening_ban" else pick.get(name,1) if role=="pick" else 1) for name in names} for role in ("opening_ban","pick","closing_ban")} for side in ("team_a","team_b")}

def test_exact_tree_probability_invariants():
    result=exact_veto_tree(set("abcdefg"),tree_props(),"team_a")
    rows=result["maps"].values()
    assert result["branch_probability_sum"]==pytest.approx(1)
    assert sum(x["opening_ban_probability"] for x in rows)==pytest.approx(2)
    assert sum(x["pick_probability"] for x in result["maps"].values())==pytest.approx(2)
    assert sum(x["closing_ban_probability"] for x in result["maps"].values())==pytest.approx(2)
    assert sum(x["decider_probability"] for x in result["maps"].values())==pytest.approx(1)
    assert sum(x["series_map_probability"] for x in result["maps"].values())==pytest.approx(3)
    assert all(x["series_map_probability"]+x["any_ban_probability"]==pytest.approx(1) for x in result["maps"].values())

def test_opening_ban_removes_map_from_later_roles():
    props=tree_props(opening={"a":1e12})
    result=exact_veto_tree(set("abcdefg"),props,"team_a")["maps"]["a"]
    assert result["opening_ban_probability"]>.999
    assert result["pick_probability"]+result["closing_ban_probability"]+result["decider_probability"]<.001

def test_pick_propensity_only_applies_after_opening_survival():
    picked=exact_veto_tree(set("abcdefg"),tree_props(pick={"a":1e6}),"team_a")["maps"]["a"]
    banned=exact_veto_tree(set("abcdefg"),tree_props(opening={"a":1e9},pick={"a":1e9}),"team_a")["maps"]["a"]
    assert picked["pick_probability"]>banned["pick_probability"]
    assert banned["series_map_probability"]<.01

def test_unknown_actor_is_equal_tree_mixture():
    props=tree_props(opening={"a":20})
    a=exact_veto_tree(set("abcdefg"),props,"team_a");b=exact_veto_tree(set("abcdefg"),props,"team_b")
    mixed=mix_veto_trees([(.5,a),(.5,b)])
    assert mixed["branch_probability_sum"]==pytest.approx(1)
    assert sum(x["series_map_probability"] for x in mixed["maps"].values())==pytest.approx(3)

def test_actor_specific_small_sample_shrinks_to_fallback():
    org={"eligible_series":30,"opening_ban":{"rate":20},"when_first_actor":{"eligible_series":1,"opening_ban":{"rate":100}}}
    small,_=action_propensity(org,None,None,"opening_ban","when_first_actor",.2)
    org["when_first_actor"]={"eligible_series":30,"opening_ban":{"rate":100}}
    large,_=action_propensity(org,None,None,"opening_ban","when_first_actor",.2)
    assert .2<small<large<1
