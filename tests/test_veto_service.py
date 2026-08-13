from datetime import date
from types import SimpleNamespace

import pytest

from cs2eye.services.veto_service import VetoError, parse_veto_text, rate, validate_actions

def match(): return SimpleNamespace(team_a_id=1, team_b_id=2, format="bo3")
def action(order, team, kind, map_name): return {"order_index":order,"team_id":team,"action":kind,"map_name":map_name}

def test_valid_ban_pick_decider_and_order():
    status, issues=validate_actions(match(),[action(1,1,"ban","inferno"),action(2,2,"pick","nuke"),action(3,None,"decider","mirage")])
    assert status=="complete" and issues==[]

def test_duplicate_order_is_invalid():
    status,_=validate_actions(match(),[action(1,1,"ban","inferno"),action(1,2,"pick","nuke")])
    assert status=="invalid"

def test_banned_map_cannot_later_be_picked():
    status,issues=validate_actions(match(),[action(1,1,"ban","inferno"),action(2,2,"pick","inferno")])
    assert status=="invalid" and "duplicate_map:inferno" in issues

def test_two_deciders_and_action_after_decider_invalid():
    status,issues=validate_actions(match(),[action(1,None,"decider","nuke"),action(2,None,"decider","mirage")])
    assert status=="invalid" and "multiple_deciders" in issues and "action_after_decider" in issues

def test_unknown_map_needs_review():
    status,issues=validate_actions(match(),[action(1,1,"ban","new_map")])
    assert status=="needs_review" and issues==["unknown_map:new_map"]

def test_empty_sample_rate_is_null(): assert rate(0,0) is None
def test_rate_uses_eligible_series(): assert rate(2,5)==40

def teams(): return SimpleNamespace(id=1,name="Spirit"),SimpleNamespace(id=2,name="MOUZ")

def test_human_readable_veto_format_is_parsed():
    spirit,mouz=teams()
    actions=parse_veto_text(match(),spirit,mouz,"""1. Spirit removed Inferno
2. MOUZ removed Anubis
3. Spirit picked Dust2
4. MOUZ picked Mirage
5. Spirit picked Ancient
6. MOUZ picked Nuke
7. Cache was left over""")
    assert [(x["team_id"],x["action"],x["map_name"]) for x in actions]==[(1,"ban","inferno"),(2,"ban","anubis"),(1,"pick","dust2"),(2,"pick","mirage"),(1,"pick","ancient"),(2,"pick","nuke"),(None,"decider","cache")]

def test_human_readable_veto_rejects_team_not_in_series():
    spirit,mouz=teams()
    with pytest.raises(VetoError,match="не участвует в серии"):
        parse_veto_text(match(),spirit,mouz,"NAVI removed Inferno")

def test_human_readable_veto_accepts_rebranded_team_alias():
    heroic=SimpleNamespace(id=1,name="HEROIC")
    dendele=SimpleNamespace(id=2,name="DENDELE")
    actions=parse_veto_text(match(),heroic,dendele,"""HEROIC removed Inferno
Sharks picked Nuke
Mirage was left over""")
    assert [(x["team_id"],x["action"],x["map_name"]) for x in actions] == [
        (1,"ban","inferno"),(2,"pick","nuke"),(None,"decider","mirage"),
    ]

def test_human_readable_unknown_map_cannot_be_complete():
    spirit,mouz=teams();actions=parse_veto_text(match(),spirit,mouz,"Spirit removed Infernno")
    status,issues=validate_actions(match(),actions)
    assert status=="needs_review" and issues==["unknown_map:infernno"]

def test_map_outside_known_series_pool_needs_review():
    status,issues=validate_actions(match(),[action(1,1,"ban","cache")],{"inferno","mirage","nuke"})
    assert status=="needs_review" and issues==["map_outside_pool:cache"]
