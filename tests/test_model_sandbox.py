import pytest
from pydantic import ValidationError

from cs2eye.analytics.matchup_config import ACTIVE_MATCHUP_CONFIG, MATCHUP_V3_CONFIG
from cs2eye.analytics.matchup_engine import calculate_matchup
from cs2eye.analytics.scoring.core import FactorInput
from cs2eye.api.routers.model_sandbox import MLTrainBody
from cs2eye.services.model_sandbox_service import sandbox_config


def factor(key,score,reliability=1):
    return FactorInput(key,key,None,score,0,confidence=reliability,available=True)


def test_sandbox_normalizes_effective_weights_without_mutating_raw_or_production():
    before=ACTIVE_MATCHUP_CONFIG.factors
    config,meta=sandbox_config({"normalize_weights":True,"factors":{
        "map_veto":{"weight":.4},"team_strength":{"weight":.4},"form_context":{"weight":.4},
        "current_roster_form":{"weight":0},"tactical_matchup":{"weight":0},"h2h":{"weight":0},"leadership_context":{"weight":0},
    }})
    assert list(meta["raw_weights"].values())[:3]==[.4,.4,.4]
    assert list(meta["effective_weights"].values())[:3]==pytest.approx([1/3]*3)
    assert ACTIVE_MATCHUP_CONFIG.factors is before
    assert config.factors["map_veto"].weight==pytest.approx(1/3)


def test_sandbox_threshold_zero_weight_and_max_effect():
    config,_=sandbox_config({"normalize_weights":False,"overall_mode":"coverage_agreement","coverage_floor":1,"agreement_floor":1,"factors":{
        "h2h":{"weight":.1,"min_reliability":.4,"reliability_mode":"linear"},
        "map_veto":{"weight":.5,"max_effect":1.5,"reliability_mode":"none"},
    }})
    result=calculate_matchup([factor("h2h",90,.2),factor("map_veto",100)],1,config)
    values={x.key:x.impact for x in result.factors}
    assert values["h2h"]==0
    assert values["map_veto"]==1.5
    zero,_=sandbox_config({"normalize_weights":False,"overall_mode":"coverage_agreement","coverage_floor":1,"agreement_floor":1,"factors":{"h2h":{"weight":0}}})
    assert calculate_matchup([factor("h2h",90)],1,zero).factors[0].impact==0


def test_ml_api_rejects_manual_coefficients():
    with pytest.raises(ValidationError):MLTrainBody.model_validate({"enabled_features":["h2h_advantage"],"manual_coefficients":{"h2h_advantage":2}})


def test_sandbox_can_express_v3_factor_set_without_current_roster_form():
    """The sandbox must be able to model any registered matchup config, not just v1.

    Regression: sandbox_config used to always validate/iterate against
    ACTIVE_MATCHUP_CONFIG's own factor set (v1, which still has
    current_roster_form), so a v3-shaped candidate — which retires that factor
    — could never be expressed: it was silently reintroduced with v1's default
    weight on every sandbox edit.
    """
    config,meta=sandbox_config({"version":"matchup_v3","normalize_weights":False})
    assert meta["base_version"]=="matchup_v3"
    assert set(config.factors)==set(MATCHUP_V3_CONFIG.factors)
    assert "current_roster_form" not in config.factors
    assert config.overall_mode=="coverage_agreement"
    assert config.coverage_floor==pytest.approx(.80)
    result=calculate_matchup([factor("current_roster_form",90)],1,config)
    assert result.factors==[]


def test_sandbox_rejects_v1_only_factor_under_v3_base():
    with pytest.raises(ValueError, match="Unknown matchup factors"):
        sandbox_config({"version":"matchup_v3","factors":{"current_roster_form":{"weight":.1}}})


def test_sandbox_defaults_to_active_config_when_version_is_omitted():
    config,meta=sandbox_config({"factors":{"map_veto":{"weight":.4}}})
    assert meta["base_version"]==ACTIVE_MATCHUP_CONFIG.version
    assert set(config.factors)==set(ACTIVE_MATCHUP_CONFIG.factors)
