from cs2eye.analytics.matchup_config import ACTIVE_MATCHUP_CONFIG,MATCHUP_V1_CONFIG,MATCHUP_V2_CONFIG
from cs2eye.analytics.matchup_engine import reliability_multiplier
from cs2eye.analytics.matchup_engine import calculate_matchup
from cs2eye.analytics.scoring.core import FactorInput
from types import SimpleNamespace
from cs2eye.services.matchup_calibration_evaluator import MatchupCalibrationEvaluator


def factor(key,score,reliability=1,available=True):
    return FactorInput(key,key,None,score,MATCHUP_V1_CONFIG.factors[key].weight,confidence=reliability,available=available)


def test_configs_share_engine_and_production_remains_v1():
    inputs=[factor("map_veto",70,.8),factor("team_strength",40,.9)]
    assert calculate_matchup(inputs,.85,MATCHUP_V1_CONFIG).model_version=="matchup_v1"
    assert calculate_matchup(inputs,.85,MATCHUP_V2_CONFIG).model_version=="matchup_v2_candidate"
    assert ACTIVE_MATCHUP_CONFIG.version=="matchup_v1"


def test_low_reliability_shrinks_more_than_v1_but_high_reliability_survives():
    low=[factor("map_veto",70,.2)];high=[factor("map_veto",70,.95)]
    assert abs(calculate_matchup(low,1,MATCHUP_V2_CONFIG).factors[0].impact)<abs(calculate_matchup(low,1,MATCHUP_V1_CONFIG).factors[0].impact)
    assert abs(calculate_matchup(high,1,MATCHUP_V2_CONFIG).factors[0].impact)>4


def test_gated_reliability_preserves_signal_after_threshold():
    threshold=MATCHUP_V2_CONFIG.factors["map_veto"].min_reliability
    assert reliability_multiplier("gated",threshold)==1
    assert reliability_multiplier("gated",.95)==1


def test_min_reliability_max_effect_and_missing_weight():
    gated=calculate_matchup([factor("h2h",90,.2)],1,MATCHUP_V2_CONFIG)
    assert gated.factors[0].impact==0
    capped=calculate_matchup([factor("map_veto",100,1)],1,MATCHUP_V2_CONFIG)
    assert capped.factors[0].impact==MATCHUP_V2_CONFIG.factors["map_veto"].max_effect
    complete=calculate_matchup([factor("team_strength",70,1),factor("h2h",70,1)],1,MATCHUP_V2_CONFIG)
    missing=calculate_matchup([factor("team_strength",70,1),factor("h2h",None,0,False)],1,MATCHUP_V2_CONFIG)
    assert missing.effective_coverage<complete.effective_coverage
    assert missing.factors[0].effective_weight==MATCHUP_V2_CONFIG.factors["team_strength"].weight


def test_factor_disagreement_shrinks_same_raw_advantage_closer_to_neutral():
    agreed=calculate_matchup([factor("team_strength",60,1),factor("form_context",60,1)],1,MATCHUP_V2_CONFIG)
    # Same contribution sum, but a larger positive and an opposing signal.
    disputed=calculate_matchup([factor("team_strength",70,1),factor("form_context",44.6666667,1)],1,MATCHUP_V2_CONFIG)
    assert abs(agreed.raw_score-50)==abs(disputed.raw_score-50)
    assert disputed.factor_agreement_score<agreed.factor_agreement_score
    assert abs(disputed.final_score-50)<abs(agreed.final_score-50)


async def test_temporal_evaluator_excludes_target_match_and_counts_both_flip_directions(monkeypatch):
    matches=[SimpleNamespace(id=10,team_a_id=1,team_b_id=2,winner_team_id=2,match_date=SimpleNamespace(),format="bo3"),SimpleNamespace(id=11,team_a_id=1,team_b_id=2,winner_team_id=1,match_date=SimpleNamespace(),format="bo3")]
    class Scalars:
        def all(self):return matches
    class Session:
        async def scalars(self,query):return Scalars()
    calls=[]
    values=[("map_veto",94,.2),("team_strength",32,1),("form_context",32,.5),("current_roster_form",36,1),("tactical_matchup",79,.5),("h2h",17,.8),("leadership_context",74,.8)]
    class Temporal:
        def __init__(self,session):pass
        async def build_dataset(self,mode):
            calls.append(mode)
            payload={"team_a":{"id":1,"name":"A","score":53.72},"team_b":{"id":2,"name":"B","score":46.28},"reliability":.7,"advantage":{"team_id":1},"factors":[{"key":k,"label":k,"score":score,"weight":MATCHUP_V1_CONFIG.factors[k].weight,"confidence":rel,"available":True} for k,score,rel in values]}
            return [SimpleNamespace(series_id=x.id,matchup=payload) for x in matches],{"cutoff_policy":"strictly_before_match_date"}
    monkeypatch.setattr("cs2eye.services.matchup_calibration_evaluator.AnalyticsAsOfService",Temporal)
    report=await MatchupCalibrationEvaluator(Session(),minimum_sample=1).evaluate(limit=2)
    assert calls==["pre_veto"]
    assert report["dataset"]["cutoff_policy"]=="strictly_before_match_date"
    assert report["flips"]["v2_fixed_v1_error"]==1
    assert report["flips"]["v2_broke_v1_correct"]==1
    assert report["flips"]["net_improvement"]==0
    assert report["baseline"]["coverage"]==1
    assert report["candidate"]["coverage"]==1
    assert report["baseline"]["accuracy"]==.5


def test_gate_rejects_candidate_that_abstains_too_often():
    evaluator=MatchupCalibrationEvaluator(None,minimum_sample=10)
    buckets={name:{"samples":10,"accuracy":.7} for name in ("0-5","5-10","10-20","20+")}
    baseline={"matches":100,"predictions":80,"coverage":.8,"accuracy":.7,"high_margin_accuracy":.7,"margin_buckets":buckets}
    candidate={"matches":100,"predictions":10,"coverage":.1,"accuracy":.9,"high_margin_accuracy":.9,"margin_buckets":buckets}
    status,checks=evaluator._gate(baseline,candidate)
    assert status=="failed"
    assert checks["coverage_not_collapsed"] is False
