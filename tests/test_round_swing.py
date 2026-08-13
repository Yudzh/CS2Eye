from cs2eye.analytics.round_swing.core import (
    RoundState, RoundWinProbabilityModel, TrainingExample, attribution_v1,
    calibration_metrics, robust_swing_score, temporal_group_split,
)
from datetime import date
from types import SimpleNamespace

import pytest

from cs2eye.services.round_swing_service import (
    assemble_training_examples, build_training_examples, compose_roster_swing_profile,
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

def dataset_fixture(round_count=2):
    rows=[];kills=[];bombs=[]
    for index in range(round_count):
        rid=index+1
        rnd=SimpleNamespace(id=rid,started_at_tick=1000,ended_at_tick=2000,duration_seconds=100,
            team_a_side="T",team_b_side="CT",team_a_equipment_value=20000,
            team_b_equipment_value=19000,winner_side="T" if index%2==0 else "CT")
        result=SimpleNamespace(map_name="mirage")
        demo=SimpleNamespace(id=rid,match_id=10+index,match_date=date(2026,1,index+1))
        kill=SimpleNamespace(id=rid,round_id=rid,tick=1500,attacker_side="T",victim_side="CT",
            is_teamkill=False,is_suicide=False,is_opening_kill=True,is_trade_kill=False)
        rows.append((rnd,result,demo));kills.append(kill)
    return rows,kills,bombs

def test_bulk_and_reference_dataset_semantics_are_identical():
    rows,kills,bombs=dataset_fixture(3)
    bulk=assemble_training_examples(rows,kills,bombs)
    reference=[]
    for row in rows:
        reference.extend(assemble_training_examples([row],[k for k in kills if k.round_id==row[0].id],[]))
    assert bulk == reference

def test_match_and_standalone_demo_id_namespaces_do_not_collide():
    rows,kills,bombs=dataset_fixture(2)
    rows[0][2].match_id=2
    rows[1][2].match_id=None
    rows[1][2].id=2
    examples=assemble_training_examples(rows,kills,bombs)
    assert {item.match_key for item in examples} == {"match:2","demo:2"}

@pytest.mark.asyncio
async def test_dataset_builder_query_count_is_bounded_not_per_round():
    rows,kills,bombs=dataset_fixture(25)
    class Result:
        def __init__(self,value):self.value=value
        def all(self):return self.value
        def scalars(self):return self
        def __iter__(self):return iter(self.value)
    class Session:
        def __init__(self):self.calls=0
        async def execute(self,_query):
            values=(rows,kills,bombs)[self.calls];self.calls+=1;return Result(values)
    session=Session()
    examples=await build_training_examples(session)
    assert session.calls == 3
    assert len(examples) == 50

def test_roster_profile_uses_selected_map_scope_and_own_reliability():
    players=[
        {"player_id":1,"overall":{"adjusted_per_round":2,"score":70,"rounds":200,"confidence":.8,"ct":1,"t":3,"opening":4,"clutch":5},
         "maps":{"nuke":{"adjusted_per_round":4,"score":85,"rounds":40,"confidence":.3,"ct":3,"t":5,"opening":6,"clutch":7}}},
        {"player_id":2,"overall":{"adjusted_per_round":0,"score":50,"rounds":200,"confidence":.8,"ct":0,"t":0,"opening":1,"clutch":2},
         "maps":{}},
    ]
    overall=compose_roster_swing_profile(players)
    nuke=compose_roster_swing_profile(players,"nuke")
    assert overall["avg_swing"]==1 and overall["sample"]=={"players":2,"rounds":400}
    assert nuke["avg_swing"]==4 and nuke["sample"]=={"players":1,"rounds":40}
    assert nuke["confidence"]==.3 and nuke["status"]=="low_confidence"

def test_missing_map_scope_is_unavailable_not_zero():
    profile=compose_roster_swing_profile([{"player_id":1,"overall":None,"maps":{}}],"mirage")
    assert profile["status"]=="not_calculated"
    assert "avg_swing" not in profile
