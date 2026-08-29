from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from cs2eye.api.schemas.match_analysis_context import MatchAnalysisContext


def full_context_payload() -> dict:
    team = {
        "id": 1,
        "name": "Spirit",
        "rank": 1,
        "roster": {
            "roster_id": 101,
            "players": [{"id": 11, "name": "donk", "role": "rifler"}],
            "coach": {"id": 20, "name": "coach"},
            "stability_score": 88.0,
            "reliability": 0.91,
            "sample_maps": 24,
        },
        "team_strength": {
            "score": 86.0,
            "reliability": 0.92,
            "sample_size": 24,
            "key_factors": [{
                "factor_id": "strength:roster",
                "key": "roster_quality",
                "score": 91.0,
                "reliability": 0.94,
            }],
        },
        "form": {
            "tournament_form_score": 72.0,
            "tournament_matches": 4,
            "tournament_reliability": 0.78,
            "recent_60d_score": 81.0,
            "recent_60d_matches": 12,
            "recent_60d_reliability": 0.9,
            "strength_of_schedule_score": 84.0,
            "performance_vs_expectation_score": 7.0,
            "matches_vs_top_5": 3,
            "matches_vs_top_10": 6,
            "matches_vs_top_30": 11,
        },
        "leadership": {
            "igl_score": 84.0,
            "coach_score": 80.0,
            "reliability": 0.83,
            "sample_size": 18,
        },
    }
    team_b = {**team, "id": 2, "name": "Falcons", "rank": 3}
    return {
        "schema_version": "match_analysis_context.v1",
        "generated_at": "2026-08-27T08:00:00Z",
        "as_of": "2026-08-26T23:59:59Z",
        "analysis_mode": "pre_match",
        "match": {
            "id": 123,
            "date": "2026-08-28",
            "format": "bo3",
            "environment": "lan",
            "stage": "semifinal",
            "is_playoff": True,
            "is_elimination": True,
            "tournament": {"id": 9, "name": "Tournament name", "tier": "S"},
            "round_number": 3,
            "round_label": "Semifinal",
            "section": "main",
        },
        "teams": {"team_a": team, "team_b": team_b},
        "recent_series_evidence": {
            "team_a": [{
                "evidence_id": "series:123",
                "date": "2026-08-25",
                "tournament": "Tournament name",
                "opponent": {"id": 2, "name": "Falcons", "rank": 3},
                "result": "win",
                "series_score": "2-1",
                "expected_win_probability": 0.34,
                "performance_vs_expectation": 0.27,
                "current_tournament": True,
                "reliability": 0.9,
            }],
            "team_b": [],
        },
        "prediction": {
            "source_type": "ml_prediction",
            "status": "available",
            "model_version": "win-probability.v1",
            "quality_gate_passed": True,
            "team_a_probability": 0.58,
            "team_b_probability": 0.42,
            "confidence": 0.81,
            "top_model_drivers": [{
                "driver_id": "ml:team_strength",
                "key": "team_strength",
                "favored_team": "team_a",
                "importance": 0.24,
                "reliability": 0.9,
            }],
        },
        "matchup": {
            "source_type": "deterministic_analytics",
            "model_version": "matchup.v2",
            "team_a_score": 55.0,
            "team_b_score": 45.0,
            "reliability": 0.82,
            "factors": [{
                "factor_id": "matchup:form",
                "key": "form_context",
                "team_a_score": 45.0,
                "team_b_score": 55.0,
                "reliability": 0.82,
                "sample_size": 8,
            }],
        },
        "veto": {
            "source_type": "deterministic_analytics",
            "basis": "calculated_veto",
            "model_version": "calculated-veto.v1",
            "likely_maps": [{
                "map": "mirage",
                "series_probability": 0.86,
                "confidence": 0.81,
                "likely_role": "team_a_pick",
            }],
        },
        "map_matchups": [{
            "map": "mirage",
            "relevance": 0.86,
            "team_a": {"map_strength": 74.0, "reliability": 0.84, "sample_maps": 9},
            "team_b": {"map_strength": 68.0, "reliability": 0.8, "sample_maps": 8},
            "matchup_score_team_a": 56.0,
            "key_edges": [{
                "evidence_id": "map:mirage:ct_side",
                "metric": "ct_side",
                "favored_team": "team_a",
                "strength": "moderate",
                "reliability": 0.81,
            }],
        }],
        "h2h": {
            "preferred_scope": "current_rosters",
            "history_applicability": "medium",
            "organizations": {
                "status": "available",
                "series_played": 5,
                "maps_played": 12,
                "team_a_series_won": 3,
                "team_b_series_won": 2,
                "team_a_maps_won": 7,
                "team_b_maps_won": 5,
                "team_a_rating": 54.0,
                "team_b_rating": 46.0,
                "team_a_score": 55.0,
                "team_b_score": 45.0,
                "confidence": 0.72,
            },
            "current_rosters": {
                "status": "available",
                "series_played": 1,
                "maps_played": 3,
                "team_a_series_won": 1,
                "team_b_series_won": 0,
                "team_a_maps_won": 2,
                "team_b_maps_won": 1,
                "team_a_rating": 58.0,
                "team_b_rating": 42.0,
                "team_a_score": 60.0,
                "team_b_score": 40.0,
                "confidence": 0.45,
            },
        },
        "manual_context": {
            "source_type": "manual_analyst_note",
            "team_a": [{
                "note_id": "note:1",
                "polarity": "positive",
                "category": "roster",
                "players": ["donk"],
                "coach": None,
                "map": None,
                "environment": "lan",
                "text": "Stable roster at this event.",
            }],
            "team_b": [],
        },
        "data_quality": {
            "overall_status": "available",
            "limitations": [],
            "missing_sections": [],
            "warnings": [],
        },
    }


def nullable_context_payload() -> dict:
    empty_team = {
        "id": None,
        "name": None,
        "rank": None,
        "roster": {
            "roster_id": None,
            "players": [],
            "coach": None,
            "stability_score": None,
            "reliability": None,
            "sample_maps": 0,
        },
        "team_strength": {
            "score": None,
            "reliability": None,
            "sample_size": 0,
            "key_factors": [],
        },
        "form": {
            "tournament_form_score": None,
            "tournament_matches": 0,
            "tournament_reliability": None,
            "recent_60d_score": None,
            "recent_60d_matches": 0,
            "recent_60d_reliability": None,
            "strength_of_schedule_score": None,
            "performance_vs_expectation_score": None,
            "matches_vs_top_5": 0,
            "matches_vs_top_10": 0,
            "matches_vs_top_30": 0,
        },
        "leadership": {
            "igl_score": None,
            "coach_score": None,
            "reliability": None,
            "sample_size": 0,
        },
    }
    empty_h2h = {
        "status": "no_meetings",
        "series_played": 0,
        "maps_played": 0,
        "team_a_series_won": 0,
        "team_b_series_won": 0,
        "team_a_maps_won": 0,
        "team_b_maps_won": 0,
        "team_a_rating": None,
        "team_b_rating": None,
        "team_a_score": None,
        "team_b_score": None,
        "confidence": None,
    }
    return {
        "generated_at": datetime(2026, 8, 27, tzinfo=timezone.utc),
        "as_of": datetime(2026, 8, 27, tzinfo=timezone.utc),
        "analysis_mode": "pre_match",
        "match": {
            "id": None,
            "date": None,
            "format": None,
            "environment": None,
            "stage": None,
            "is_playoff": None,
            "is_elimination": None,
            "tournament": {"id": None, "name": None, "tier": None},
            "round_number": None,
            "round_label": None,
            "section": None,
        },
        "teams": {"team_a": empty_team, "team_b": empty_team},
        "recent_series_evidence": {"team_a": [], "team_b": []},
        "prediction": {
            "status": "not_available",
            "model_version": None,
            "quality_gate_passed": None,
            "team_a_probability": None,
            "team_b_probability": None,
            "confidence": None,
            "top_model_drivers": [],
        },
        "matchup": {
            "model_version": None,
            "team_a_score": None,
            "team_b_score": None,
            "reliability": None,
            "factors": [],
        },
        "veto": {
            "source_type": "deterministic_analytics",
            "basis": "calculated_veto",
            "model_version": None,
            "likely_maps": [],
        },
        "map_matchups": [],
        "h2h": {
            "preferred_scope": "organizations",
            "history_applicability": "none",
            "organizations": empty_h2h,
            "current_rosters": {**empty_h2h, "status": "roster_unavailable"},
        },
        "manual_context": {"team_a": [], "team_b": []},
        "data_quality": {
            "overall_status": "insufficient",
            "limitations": ["No source data."],
            "missing_sections": ["prediction", "matchup"],
            "warnings": [],
        },
    }


def test_full_match_analysis_context_is_valid() -> None:
    context = MatchAnalysisContext.model_validate(full_context_payload())
    assert context.schema_version == "match_analysis_context.v1"
    assert context.prediction.team_a_probability == 0.58
    assert context.h2h.organizations.series_played == 5


def test_ml_prediction_is_immutable_input() -> None:
    context = MatchAnalysisContext.model_validate(full_context_payload())
    with pytest.raises(ValidationError):
        context.prediction.team_a_probability = 0.5


def test_nullable_match_analysis_context_is_valid_and_preserves_real_zeroes() -> None:
    context = MatchAnalysisContext.model_validate(nullable_context_payload())
    assert context.match.id is None
    assert context.teams.team_a.roster.sample_maps == 0
    assert context.h2h.organizations.series_played == 0


@pytest.mark.parametrize("field,value", [
    ("team_a_probability", -0.01),
    ("team_b_probability", 1.01),
    ("confidence", 1.01),
])
def test_prediction_probabilities_and_reliability_are_bounded(field: str, value: float) -> None:
    payload = full_context_payload()
    payload["prediction"][field] = value
    with pytest.raises(ValidationError):
        MatchAnalysisContext.model_validate(payload)


def test_nested_reliability_is_bounded() -> None:
    payload = full_context_payload()
    payload["map_matchups"][0]["key_edges"][0]["reliability"] = -0.01
    with pytest.raises(ValidationError):
        MatchAnalysisContext.model_validate(payload)


def test_sample_size_must_not_be_negative() -> None:
    payload = full_context_payload()
    payload["matchup"]["factors"][0]["sample_size"] = -1
    with pytest.raises(ValidationError):
        MatchAnalysisContext.model_validate(payload)


@pytest.mark.parametrize(("path", "invalid_value"), [
    (("analysis_mode",), "live"),
    (("prediction", "status"), "ready"),
    (("map_matchups", 0, "key_edges", 0, "strength"), "strong"),
    (("h2h", "history_applicability"), "unknown"),
    (("manual_context", "team_a", 0, "polarity"), "upside"),
])
def test_enum_validation(path: tuple, invalid_value: str) -> None:
    payload = full_context_payload()
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = invalid_value
    with pytest.raises(ValidationError):
        MatchAnalysisContext.model_validate(payload)


@pytest.mark.parametrize("section", [
    "match",
    "teams",
    "recent_series_evidence",
    "prediction",
    "matchup",
    "veto",
    "map_matchups",
    "h2h",
    "manual_context",
    "data_quality",
])
def test_root_sections_are_required(section: str) -> None:
    payload = full_context_payload()
    del payload[section]
    with pytest.raises(ValidationError):
        MatchAnalysisContext.model_validate(payload)


def test_schema_version_is_fixed() -> None:
    payload = full_context_payload()
    payload["schema_version"] = "match_analysis_context.v2"
    with pytest.raises(ValidationError):
        MatchAnalysisContext.model_validate(payload)


def test_json_serialization() -> None:
    context = MatchAnalysisContext.model_validate(full_context_payload())
    serialized = context.model_dump(mode="json")
    assert serialized["generated_at"] == "2026-08-27T08:00:00Z"
    assert serialized["match"]["date"] == date(2026, 8, 28).isoformat()
    assert serialized["prediction"]["source_type"] == "ml_prediction"
    assert MatchAnalysisContext.model_validate_json(context.model_dump_json()) == context
