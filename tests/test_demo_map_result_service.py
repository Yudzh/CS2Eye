from types import SimpleNamespace

import pytest

from cs2eye.services.demo_map_result_service import (
    ParsedMapResult, detect_overtime, normalize_map_name,
    normalize_parsed_map_result,
)
from cs2eye.services.demo_team_resolver import normalize_team_name, team_name_aliases


@pytest.mark.parametrize("raw, expected", [
    ("de_mirage", "mirage"), ("de_inferno", "inferno"),
    ("de_nuke", "nuke"), ("de_train", "train"),
    ("de_dust2", "dust2"), ("de_ancient", "ancient"),
    ("de_anubis", "anubis"), ("de_vertigo", "vertigo"),
    ("de_overpass", "overpass"),
    ("de_cache", "cache"),
])
def test_normalize_known_map(raw, expected):
    assert normalize_map_name(raw) == expected


def test_overtime_rules():
    assert detect_overtime(13, 11) is False
    assert detect_overtime(16, 13) is True
    assert detect_overtime(13, 12) is None
    assert detect_overtime(13, 9, 1) is True
    assert detect_overtime(16, 13, 0) is False


@pytest.mark.asyncio
async def test_split_demo_part_one_tied_score_is_partial(monkeypatch):
    async def resolved(_session, names):
        return [SimpleNamespace(
            team_id=i, raw_name=name, normalized_name=name.lower(),
            resolution_status="matched",
        ) for i, name in enumerate(names, 1)]

    monkeypatch.setattr(
        "cs2eye.services.demo_map_result_service.resolve_demo_teams", resolved,
    )
    result = await normalize_parsed_map_result(
        None,
        ParsedMapResult(
            raw_map_name="de_nuke", team_a_name="MOUZ", team_a_score=1,
            team_b_name="Legacy", team_b_score=1, parser_rounds_count=2,
        ),
        completed_map=False,
    )
    assert result.metadata_status == "partial"
    assert [issue.code for issue in result.issues] == ["incomplete_split_demo"]


def test_compact_cs2_team_suffix_is_an_exact_alias():
    assert "wildcard" in team_name_aliases("WILDCARDcs2")


@pytest.mark.parametrize(("demo_name", "team_name"), [
    ("MongolZ", "The MongolZ"),
    ("Team Vitality", "Vitality"),
    ("100T", "100 Thieves"),
    ("Aurora Gaming", "Aurora"),
    ("paiN Gaming", "paiN"),
    ("Team Spirit", "Spirit"),
    ("Team Falcons", "Falcons"),
    ("BetBoom Team", "BetBoom"),
    ("Team Liquid", "Liquid"),
    ("Lynn Vision Gaming", "Lynn Vision"),
    ("DENDELE", "DENDELE CS"),
    ("DENDELE", "Sharks"),
])
def test_known_demo_team_aliases(demo_name, team_name):
    assert normalize_team_name(demo_name) == normalize_team_name(team_name)


@pytest.mark.asyncio
async def test_score_winner_rounds_and_unknown_map(monkeypatch):
    async def resolved(_session, names):
        return [
            SimpleNamespace(team_id=10, raw_name=names[0], normalized_name="spirit", resolution_status="matched"),
            SimpleNamespace(team_id=20, raw_name=names[1], normalized_name="navi", resolution_status="matched"),
        ]
    monkeypatch.setattr("cs2eye.services.demo_map_result_service.resolve_demo_teams", resolved)
    result = await normalize_parsed_map_result(None, ParsedMapResult(
        raw_map_name="de_custom", team_a_name="Spirit", team_a_score=13,
        team_b_name="NAVI", team_b_score=9, parser_rounds_count=22,
    ))
    assert result.rounds_count == 22
    assert result.winner_team_id == 10
    assert result.winner_team_name == "Spirit"
    assert result.metadata_status == "needs_review"


@pytest.mark.asyncio
async def test_tied_score_is_invalid(monkeypatch):
    async def resolved(_session, names):
        return [SimpleNamespace(team_id=i, raw_name=n, normalized_name=n.lower(), resolution_status="matched") for i, n in enumerate(names, 1)]
    monkeypatch.setattr("cs2eye.services.demo_map_result_service.resolve_demo_teams", resolved)
    result = await normalize_parsed_map_result(None, ParsedMapResult(
        raw_map_name="de_mirage", team_a_name="A", team_a_score=12,
        team_b_name="B", team_b_score=12,
    ))
    assert result.metadata_status == "invalid"
