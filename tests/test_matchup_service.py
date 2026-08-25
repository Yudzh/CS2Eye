from types import SimpleNamespace

import pytest

from cs2eye.analytics.matchup_config import MATCHUP_WEIGHTS, TACTICAL_WEIGHTS
from cs2eye.analytics.scoring.core import FactorInput, score_factors
from cs2eye.services.matchup_service import advantage_level, aggregate_maps, relevant_map_weights
from cs2eye.services.matchup_service import MatchupService


def calculated(a=65,b=35):
    def side(score):return {"matchup_map_score":score,"calculated_pick_score":score,"calculated_ban_score":100-score,"matchup_confidence":.8,"tactical_components":{"side":score,"bomb":score,"combat_swing":score,"economy":score,"utility":score,"trading":score}}
    probabilities=(.7,.6,.5,.4,.35,.25,.2)
    maps=[{"map":name,"series_map_probability":probabilities[index],"team_a":side(a if index<4 else b),"team_b":side(100-(a if index<4 else b))} for index,name in enumerate(("ancient","dust2","inferno","mirage","nuke","overpass","train"))]
    return {"team_a":{"id":1},"team_b":{"id":2},"maps":maps}


def test_matchup_weights_sum_to_one():
    assert sum(MATCHUP_WEIGHTS.values())==1
    assert sum(TACTICAL_WEIGHTS.values())==1


def test_equal_available_factors_are_neutral_and_symmetric():
    result=score_factors([FactorInput("x","x",None,50,1)],1)
    assert result.final_score==50 and 100-result.final_score==50


def test_stronger_a_and_low_reliability_shrink():
    high=score_factors([FactorInput("x","x",None,80,1)],1)
    low=score_factors([FactorInput("x","x",None,80,1)],.25)
    assert high.final_score>low.final_score>50


def test_missing_factor_is_reweighted_not_zero():
    result=score_factors([FactorInput("x","x",None,60,.5),FactorInput("missing","missing",None,None,.5,available=False)],1)
    assert result.final_score==60 and sum(x.effective_weight for x in result.factors)==1


def test_bo3_uses_series_map_probabilities():
    weights=relevant_map_weights(calculated(),"bo3")
    assert all(role=="probability" for _,role in weights.values())
    assert weights["ancient"][0]>weights["nuke"][0]


def test_bo1_and_bo5_use_different_pool_sizes():
    one=relevant_map_weights(calculated(),"bo1");five=relevant_map_weights(calculated(),"bo5")
    assert sum(weight>.05 for weight,_ in one.values()) < sum(weight>.05 for weight,_ in five.values())


def test_post_veto_uses_actual_actions():
    actual=[SimpleNamespace(action="pick",team_id=1,map_name="nuke"),SimpleNamespace(action="decider",team_id=None,map_name="mirage")]
    weights=relevant_map_weights(calculated(),"bo3",actual)
    assert set(weights)=={"nuke","mirage"} and weights["nuke"][1]=="team_a_pick"


def test_map_and_tactical_breakdowns_are_mathematical():
    data=calculated();weights=relevant_map_weights(data,"bo3");score,maps,tactical=aggregate_maps(data,weights)
    assert score>50 and tactical["score"]>50
    assert round(sum(row["playability_weight"] for row in maps),5)==1
    assert round(50+sum(row["contribution"] for row in maps),2)==score

def test_asymmetric_source_sides_are_pairwise_symmetrized():
    data=calculated();data["maps"][0]["team_a"]["matchup_map_score"]=70;data["maps"][0]["team_b"]["matchup_map_score"]=40
    weights={"ancient":(1.0,"remaining")};score,_,_=aggregate_maps(data,weights)
    assert score==65


def test_advantage_labels_are_centralized_and_not_probability_words():
    assert advantage_level(50)=="neutral" and advantage_level(58)=="slight" and advantage_level(65)=="moderate" and advantage_level(75)=="strong"

def test_each_tactical_component_can_move_score_and_missing_is_not_zero():
    data=calculated(50,50);weights={"ancient":(1.0,"remaining")}
    baseline=aggregate_maps(data,weights)[2]["score"]
    data["maps"][0]["team_a"]["tactical_components"]["side"]=90
    assert aggregate_maps(data,weights)[2]["score"]>baseline
    data["maps"][0]["team_a"]["tactical_components"]["utility"]=None
    data["maps"][0]["team_b"]["tactical_components"]["utility"]=None
    tactical=aggregate_maps(data,weights)[2]
    assert tactical["utility"]["available"] is False and tactical["score"] is not None

def test_opening_and_clutch_are_not_separate_tactical_factors():
    _,_,tactical=aggregate_maps(calculated(),{"ancient":(1.0,"remaining")})
    assert set(tactical)=={"side","bomb","combat_swing","economy","utility","trading","score"}

@pytest.mark.asyncio
async def test_historical_request_excludes_unsafe_current_snapshots():
    class Session:
        async def get(self,_model,team_id):return SimpleNamespace(id=team_id,name=f"T{team_id}")
    result=await MatchupService(Session())._historical_safe(1,2,"bo3","pre_veto",__import__("datetime").date(2020,1,1),None)
    assert result["reliability"]==0 and result["team_a"]["score"]==50
    assert all(not factor["available"] for factor in result["factors"])
    assert result["veto"]["basis"]=="unavailable"
