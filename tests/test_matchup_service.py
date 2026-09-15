from types import SimpleNamespace

import pytest

from cs2eye.analytics.matchup_config import MATCHUP_V3_CONFIG, MATCHUP_WEIGHTS, TACTICAL_WEIGHTS_V3
from cs2eye.analytics.scoring.core import FactorInput, score_factors
from cs2eye.services.matchup_service import advantage_level, aggregate_maps_v3, relevant_map_weights
from cs2eye.services.matchup_service import MatchupService


def calculated(a=65,b=35):
    def side(score):return {"matchup_map_score":score,"calculated_pick_score":score,"calculated_ban_score":100-score,"matchup_confidence":.8,"tactical_components":{"side":score,"bomb":score,"combat_swing":score,"economy":score,"utility":score,"trading":score}}
    probabilities=(.7,.6,.5,.4,.35,.25,.2)
    maps=[{"map":name,"series_map_probability":probabilities[index],"team_a":side(a if index<4 else b),"team_b":side(100-(a if index<4 else b))} for index,name in enumerate(("ancient","dust2","inferno","mirage","nuke","overpass","train"))]
    return {"team_a":{"id":1},"team_b":{"id":2},"maps":maps}


def test_matchup_weights_sum_to_one():
    assert sum(MATCHUP_WEIGHTS.values())==1
    assert sum(TACTICAL_WEIGHTS_V3.values())==1


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


def test_advantage_labels_are_centralized_and_not_probability_words():
    assert advantage_level(50)=="neutral" and advantage_level(58)=="slight" and advantage_level(65)=="moderate" and advantage_level(75)=="strong"

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
async def test_historical_request_delegates_to_v3_aware_reconstruction(monkeypatch):
    # AnalyticsAsOfService.calculate does its own V3-aware temporal reconstruction
    # (_matchup_v3); this only checks the wiring (the resulting payload is returned
    # as-is), since exercising _matchup_v3's real behavior needs full demo/roster
    # fixtures -- covered separately by the aggregate_maps_v3/MATCHUP_V3_CONFIG tests
    # above and by real-data scripts.
    import cs2eye.services.analytics_as_of_service as aaos
    captured={}
    async def fake_calculate(self,a,b,as_of,format,analysis_mode,series_id):
        captured["called"]=True
        return {"model_version":"matchup_v3","team_a":{"id":a,"score":60},"team_b":{"id":b,"score":40},"advantage":{}}
    monkeypatch.setattr(aaos.AnalyticsAsOfService,"calculate",fake_calculate)
    result=await MatchupService(object()).calculate(1,2,as_of=__import__("datetime").date(2020,1,1))
    assert captured["called"] is True
    assert result["model_version"]=="matchup_v3"


@pytest.mark.asyncio
async def test_historical_request_excludes_unsafe_current_snapshots():
    class Session:
        async def get(self,_model,team_id):return SimpleNamespace(id=team_id,name=f"T{team_id}")
    result=await MatchupService(Session())._historical_safe(1,2,"bo3","pre_veto",__import__("datetime").date(2020,1,1),None)
    assert result["reliability"]==0 and result["team_a"]["score"]==50
    assert all(not factor["available"] for factor in result["factors"])
    assert result["veto"]["basis"]=="unavailable"
