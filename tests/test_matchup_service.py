from types import SimpleNamespace

import pytest

from cs2eye.analytics.matchup_config import MATCHUP_V3_CONFIG, MATCHUP_WEIGHTS, TACTICAL_WEIGHTS
from cs2eye.analytics.scoring.core import FactorInput, score_factors
from cs2eye.services.matchup_service import advantage_level, aggregate_maps, aggregate_maps_v3, relevant_map_weights
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

def map_v3(delta,reliability=80,ct=60,t=60,postplant=60,retake=60):
    return {"delta_vs_team":delta,"reliability":reliability,
            "sides":{"ct":{"score":ct},"t":{"score":t}},
            "components":{"map_execution":{"metrics":{"postplant":{"score":postplant},"retake":{"score":retake}}}}}


def test_matchup_v3_weights_sum_to_one():
    assert round(sum(f.weight for f in MATCHUP_V3_CONFIG.factors.values()),6)==1
    assert "current_roster_form" not in MATCHUP_V3_CONFIG.factors


def test_v3_map_score_is_delta_based_not_raw_score():
    # A's own map quality is far below B's, but A's delta is 0 (exactly its own baseline)
    # while B's delta is -20 (this map is a weakness relative to B's own baseline). The
    # map_veto factor must reward A here since it isolates the map-specific edge, not
    # absolute map strength (which is already covered by the separate team_strength factor).
    weights={"ancient":(1.0,"remaining")}
    maps_v3={(1,"ancient"):map_v3(delta=0),(2,"ancient"):map_v3(delta=-20)}
    score,breakdown,_=aggregate_maps_v3(1,2,weights,maps_v3)
    assert score==70  # clamp(50 + (delta_a - delta_b)) = clamp(50 + (0 - -20))
    assert breakdown[0]["delta_a"]==0 and breakdown[0]["delta_b"]==-20


def test_v3_maps_without_delta_are_excluded_and_renormalized():
    weights={"ancient":(.5,"remaining"),"dust2":(.5,"remaining")}
    maps_v3={(1,"ancient"):map_v3(delta=10),(2,"ancient"):map_v3(delta=0),
              (1,"dust2"):{**map_v3(delta=0),"delta_vs_team":None},(2,"dust2"):map_v3(delta=0)}
    score,breakdown,_=aggregate_maps_v3(1,2,weights,maps_v3)
    assert len(breakdown)==1 and breakdown[0]["map"]=="ancient"
    assert breakdown[0]["playability_weight"]==1.0


def test_v3_tactical_has_only_side_and_bomb():
    weights={"ancient":(1.0,"remaining")}
    maps_v3={(1,"ancient"):map_v3(delta=0,ct=70,t=50,postplant=70,retake=40),
              (2,"ancient"):map_v3(delta=0,ct=40,t=60,postplant=30,retake=60)}
    _,_,tactical=aggregate_maps_v3(1,2,weights,maps_v3)
    assert set(tactical)=={"side","bomb","score"}
    assert tactical["side"]["score"]>50 and tactical["bomb"]["score"]>50


def test_v3_tactical_missing_bomb_data_is_reweighted_not_zero():
    weights={"ancient":(1.0,"remaining")}
    a=map_v3(delta=0);b=map_v3(delta=0)
    a["components"]["map_execution"]["metrics"]["postplant"]["score"]=None
    b["components"]["map_execution"]["metrics"]["postplant"]["score"]=None
    _,_,tactical=aggregate_maps_v3(1,2,weights,{(1,"ancient"):a,(2,"ancient"):b})
    assert tactical["bomb"]["available"] is False
    assert tactical["side"]["available"] is True
    assert tactical["score"]==tactical["side"]["score"]


@pytest.mark.asyncio
async def test_historical_matchup_v3_is_rejected_explicitly():
    class Session:
        async def get(self,_model,team_id):return SimpleNamespace(id=team_id,name=f"T{team_id}")
    with pytest.raises(ValueError,match="matchup_v3"):
        await MatchupService(Session()).calculate(1,2,as_of=__import__("datetime").date(2020,1,1),model_version="matchup_v3")


@pytest.mark.asyncio
async def test_historical_request_excludes_unsafe_current_snapshots():
    class Session:
        async def get(self,_model,team_id):return SimpleNamespace(id=team_id,name=f"T{team_id}")
    result=await MatchupService(Session())._historical_safe(1,2,"bo3","pre_veto",__import__("datetime").date(2020,1,1),None)
    assert result["reliability"]==0 and result["team_a"]["score"]==50
    assert all(not factor["available"] for factor in result["factors"])
    assert result["veto"]["basis"]=="unavailable"
