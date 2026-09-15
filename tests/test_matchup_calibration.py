from cs2eye.analytics.matchup_config import ACTIVE_MATCHUP_CONFIG,MATCHUP_V3_CONFIG,FactorConfig,MatchupModelConfig
from cs2eye.analytics.matchup_engine import reliability_multiplier
from cs2eye.analytics.matchup_engine import calculate_matchup
from cs2eye.analytics.scoring.core import FactorInput
from types import SimpleNamespace
from cs2eye.services.matchup_calibration_evaluator import MatchupCalibrationEvaluator


def factor(key,score,reliability=1,available=True):
    return FactorInput(key,key,None,score,MATCHUP_V3_CONFIG.factors[key].weight,confidence=reliability,available=available)


# A synthetic "no reliability shrinkage" config -- same factors as production, but every
# factor uses overall_mode="legacy" semantics (via reliability_multiplier's "none" mode),
# so calculate_matchup's per-factor reliability gating can be contrasted against a config
# that ignores reliability entirely, without depending on a removed production config.
NO_GATING_CONFIG=MatchupModelConfig("no_gating_test",{k:FactorConfig(v.weight,"none",0,v.max_effect) for k,v in MATCHUP_V3_CONFIG.factors.items()},MATCHUP_V3_CONFIG.redistribute_missing_weight,MATCHUP_V3_CONFIG.overall_mode,MATCHUP_V3_CONFIG.coverage_floor,MATCHUP_V3_CONFIG.agreement_floor)


def test_active_config_is_v3():
    inputs=[factor("map_veto",70,.8),factor("team_strength",40,.9)]
    assert calculate_matchup(inputs,.85,MATCHUP_V3_CONFIG).model_version=="matchup_v3"
    assert ACTIVE_MATCHUP_CONFIG is MATCHUP_V3_CONFIG


def test_low_reliability_shrinks_more_when_gated_but_high_reliability_survives():
    low=[factor("map_veto",70,.2)];high=[factor("map_veto",70,.95)]
    assert abs(calculate_matchup(low,1,MATCHUP_V3_CONFIG).factors[0].impact)<abs(calculate_matchup(low,1,NO_GATING_CONFIG).factors[0].impact)
    assert abs(calculate_matchup(high,1,MATCHUP_V3_CONFIG).factors[0].impact)>4


def test_gated_reliability_preserves_signal_after_threshold():
    threshold=MATCHUP_V3_CONFIG.factors["map_veto"].min_reliability
    assert reliability_multiplier("gated",threshold)==1
    assert reliability_multiplier("gated",.95)==1


def test_min_reliability_max_effect_and_missing_weight():
    gated=calculate_matchup([factor("h2h",90,.2)],1,MATCHUP_V3_CONFIG)
    assert gated.factors[0].impact==0
    capped=calculate_matchup([factor("map_veto",100,1)],1,MATCHUP_V3_CONFIG)
    assert capped.factors[0].impact==MATCHUP_V3_CONFIG.factors["map_veto"].max_effect
    complete=calculate_matchup([factor("team_strength",70,1),factor("h2h",70,1)],1,MATCHUP_V3_CONFIG)
    missing=calculate_matchup([factor("team_strength",70,1),factor("h2h",None,0,False)],1,MATCHUP_V3_CONFIG)
    assert missing.effective_coverage<complete.effective_coverage
    assert missing.factors[0].effective_weight==MATCHUP_V3_CONFIG.factors["team_strength"].weight


def test_factor_disagreement_shrinks_same_raw_advantage_closer_to_neutral():
    agreed=calculate_matchup([factor("team_strength",60,1),factor("form_context",60,1)],1,MATCHUP_V3_CONFIG)
    # Same contribution sum, but a larger positive and an opposing signal.
    disputed=calculate_matchup([factor("team_strength",70,1),factor("form_context",45.88235294117647,1)],1,MATCHUP_V3_CONFIG)
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
    # All factors strongly favor team A (score 80) except h2h, which strongly favors team B
    # (score 10). The balanced baseline config (production weights) is dominated by the other
    # 5 factors and picks team A; a candidate reweighted to h2h-only picks team B instead.
    values=[("map_veto",80,1),("team_strength",80,1),("form_context",80,1),("tactical_matchup",80,1),("h2h",10,1),("leadership_context",80,1)]
    class Temporal:
        def __init__(self,session):pass
        async def build_dataset_v3(self,mode):
            calls.append(mode)
            payload={"team_a":{"id":1,"name":"A","score":80},"team_b":{"id":2,"name":"B","score":20},"reliability":.7,"advantage":{"team_id":1},"factors":[{"key":k,"label":k,"score":score,"weight":MATCHUP_V3_CONFIG.factors[k].weight,"confidence":rel,"available":True} for k,score,rel in values]}
            return [SimpleNamespace(series_id=x.id,matchup=payload) for x in matches],{"cutoff_policy":"strictly_before_match_date"}
    monkeypatch.setattr("cs2eye.services.matchup_calibration_evaluator.AnalyticsAsOfService",Temporal)
    # max_effect raised to 50 for h2h so its full weight can actually swing the score --
    # v3's own max_effect=2 for h2h assumes h2h keeps its small production weight (.09);
    # at weight=1.0 that clamp would cap every prediction in a narrow neutral band.
    h2h_only=MatchupModelConfig("h2h_only_candidate",{k:FactorConfig(1.0 if k=="h2h" else 0.0,v.reliability_mode,v.min_reliability,50 if k=="h2h" else v.max_effect) for k,v in MATCHUP_V3_CONFIG.factors.items()},MATCHUP_V3_CONFIG.redistribute_missing_weight,MATCHUP_V3_CONFIG.overall_mode,MATCHUP_V3_CONFIG.coverage_floor,MATCHUP_V3_CONFIG.agreement_floor)
    report=await MatchupCalibrationEvaluator(Session(),minimum_sample=1).evaluate(limit=2,baseline=MATCHUP_V3_CONFIG,candidate=h2h_only)
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
