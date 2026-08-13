from cs2eye.analytics.round_swing.core import (
    RoundState, RoundWinProbabilityModel, TrainingExample, attribution_v1,
    calibration_metrics, robust_swing_score, temporal_group_split,
)

def state(t=5, ct=5, bomb="not_planted", time=90, et=20000, ec=20000):
    return RoundState("mirage", t, ct, bomb, et, ec, time)

def trained_model():
    examples=[]
    for match in range(10):
        examples += [TrainingExample(str(match), match, state(5,5), match%2),
                     TrainingExample(str(match), match, state(5,4), 1),
                     TrainingExample(str(match), match, state(1,5), 0)]
    return RoundWinProbabilityModel.train(examples, epochs=250)[0]

def test_probability_is_bounded_and_alive_advantage_matters():
    model=trained_model(); neutral,t_adv,cleanup=model.predict_batch([state(),state(5,4),state(5,1)])
    assert 0 <= neutral <= 1 and 0 <= t_adv <= 1
    assert t_adv > neutral and cleanup > t_adv
    assert (cleanup-t_adv) < (t_adv-neutral)

def test_swing_is_after_minus_before_with_side_inversion():
    model=trained_model(); before,after=model.predict_batch([state(),state(5,4)])
    assert after-before > 0
    assert -(after-before) < 0

def test_bomb_economy_and_time_are_in_state_vector():
    a=RoundWinProbabilityModel.vector(state(),["mirage"])
    b=RoundWinProbabilityModel.vector(state(bomb="planted",time=10,et=24000),["mirage"])
    assert a != b and b[3] == 1 and b[4] != a[4] and b[7] != a[7]

def test_attribution_damage_flash_and_no_team_double_count():
    credits=attribution_v1(.2,"killer","victim",damage_by_player={"helper":80,"killer":20},flash_assister_key="flasher")
    additive=[x for x in credits if x.role!="victim_non_additive"]
    assert round(sum(x.share for x in additive),8)==1
    assert round(sum(x.credited_swing for x in additive),8)==.2
    assert next(x for x in credits if x.identity_key=="victim").credited_swing==-.2

def test_group_temporal_split_never_mixes_match():
    examples=[TrainingExample(str(m),m,state(),m%2) for m in range(10) for _ in range(3)]
    train,validation=temporal_group_split(examples)
    assert {x.match_key for x in train}.isdisjoint({x.match_key for x in validation})
    assert max(x.chronology for x in train) < min(x.chronology for x in validation)

def test_metrics_and_robust_normalization():
    metrics=calibration_metrics([.1,.7,.9],[0,1,1])
    assert set(metrics)>={"brier_score","log_loss","calibration_error"}
    assert robust_swing_score(0,[ -2,-1,0,1,2])==50
