from types import SimpleNamespace

import pytest

from cs2eye.services.betting_restriction_service import (
    GROUP_STAGE_MESSAGE, GROUP_STAGE_RULE, NAVI_MESSAGE, NAVI_RULE,
    betting_restrictions_for_teams,
)


def team(*, bo3_id: int, slug: str, name: str = "Display name") -> SimpleNamespace:
    return SimpleNamespace(bo3_id=bo3_id, bo3_slug=slug, name=name)


@pytest.mark.parametrize("teams", [
    [team(bo3_id=787, slug="renamed"), team(bo3_id=2, slug="opponent")],
    [team(bo3_id=2, slug="opponent"), team(bo3_id=787, slug="renamed")],
    [team(bo3_id=999, slug="natus-vincere"), team(bo3_id=2, slug="opponent")],
])
def test_navi_is_restricted_by_canonical_identity_on_either_side(teams) -> None:
    result = betting_restrictions_for_teams(teams)
    assert result == {"restricted": True, "rule": NAVI_RULE, "message": NAVI_MESSAGE,
                      "restrictions": [{"rule": NAVI_RULE, "message": NAVI_MESSAGE}]}


def test_display_name_alone_does_not_activate_rule() -> None:
    result = betting_restrictions_for_teams([
        team(bo3_id=1, slug="not-navi", name="NAVI"),
        team(bo3_id=2, slug="opponent"),
    ])
    assert result == {"restricted": False, "rule": None, "message": None, "restrictions": []}


@pytest.mark.parametrize("stage", ["group", "swiss", "opening", "elimination"])
def test_every_non_playoff_stage_uses_backend_flag(stage) -> None:
    # The stage label is deliberately ignored; only the normalized flag matters.
    result = betting_restrictions_for_teams(
        [team(bo3_id=1, slug="spirit"), team(bo3_id=2, slug="vitality")],
        is_playoff=False,
    )
    assert result["restrictions"] == [{"rule": GROUP_STAGE_RULE, "message": GROUP_STAGE_MESSAGE}]


@pytest.mark.parametrize("stage", ["quarterfinal", "semifinal", "final"])
def test_playoff_and_final_do_not_activate_group_rule(stage) -> None:
    result = betting_restrictions_for_teams(
        [team(bo3_id=1, slug="spirit"), team(bo3_id=2, slug="vitality")],
        is_playoff=True,
    )
    assert result["restrictions"] == []


def test_navi_group_rules_are_independent_and_ordered() -> None:
    result = betting_restrictions_for_teams(
        [team(bo3_id=787, slug="natus-vincere"), team(bo3_id=2, slug="vitality")],
        is_playoff=False,
    )
    assert [item["rule"] for item in result["restrictions"]] == [NAVI_RULE, GROUP_STAGE_RULE]


def test_navi_playoff_keeps_only_navi_rule() -> None:
    result = betting_restrictions_for_teams(
        [team(bo3_id=787, slug="natus-vincere"), team(bo3_id=2, slug="vitality")],
        is_playoff=True,
    )
    assert [item["rule"] for item in result["restrictions"]] == [NAVI_RULE]
