from copy import deepcopy

import pytest
from pydantic import ValidationError

from cs2eye.api.schemas.match_analysis_context import MatchAnalysisContext
from cs2eye.api.schemas.match_llm_analysis import MatchLLMAnalysis
from cs2eye.services.match_llm_analysis_validator import (
    MatchLLMAnalysisValidationError,
    MatchLLMAnalysisValidator,
)
from tests.test_match_analysis_context import full_context_payload, nullable_context_payload


def valid_analysis_payload() -> dict:
    return {
        "schema_version": "match_llm_analysis.v1",
        "context_schema_version": "match_analysis_context.v1",
        "analysis_status": "complete",
        "conclusion": {
            "favored_team": "team_a",
            "advantage": "small",
            "confidence": "medium",
            "reasoning_basis": "ml_prediction",
        },
        "key_advantages": [{
            "claim_id": "advantage:1",
            "side": "team_a",
            "category": "overall_strength",
            "importance": "high",
            "statement": "Team A has the stronger aggregate profile.",
            "evidence_refs": ["prediction", "team:1:strength"],
        }],
        "counter_arguments": [{
            "claim_id": "counter:1",
            "side": "team_b",
            "category": "recent_form",
            "importance": "medium",
            "statement": "A recent series supports the opposing side.",
            "evidence_refs": ["matchup:form", "series:123"],
        }],
        "contradictions": [{
            "contradiction_id": "contradiction:1",
            "importance": "medium",
            "description": "Recent form and the primary prediction point differently.",
            "evidence_refs": ["prediction", "matchup:form"],
        }],
        "risks": [{
            "risk_id": "risk:1",
            "severity": "low",
            "category": "h2h",
            "statement": "Current-roster H2H has a small sample.",
            "evidence_refs": ["h2h:current_rosters"],
        }],
        "data_limitations": [{
            "limitation_id": "limitation:1",
            "severity": "low",
            "statement": "Some per-series reliability is unavailable.",
            "evidence_refs": ["data_quality"],
        }],
        "summary": "Team A remains the small favorite; the evidence is not unanimous.",
    }


def validate(payload: dict, context_payload: dict | None = None) -> MatchLLMAnalysis:
    context = MatchAnalysisContext.model_validate(context_payload or full_context_payload())
    analysis = MatchLLMAnalysis.model_validate(payload)
    MatchLLMAnalysisValidator().validate(context, analysis)
    return analysis


def test_fully_valid_match_llm_analysis() -> None:
    analysis = validate(valid_analysis_payload())
    assert analysis.schema_version == "match_llm_analysis.v1"
    assert "probability" not in analysis.model_dump()


def test_insufficient_data_analysis_is_valid() -> None:
    payload = valid_analysis_payload()
    payload["analysis_status"] = "insufficient_data"
    payload["conclusion"] = {
        "favored_team": "none",
        "advantage": "none",
        "confidence": "insufficient",
        "reasoning_basis": "ml_prediction",
    }
    payload["key_advantages"] = []
    payload["counter_arguments"] = []
    payload["contradictions"] = []
    payload["risks"] = []
    validate(payload, nullable_context_payload())


@pytest.mark.parametrize(("path", "value"), [
    (("analysis_status",), "unknown"),
    (("conclusion", "advantage"), "huge"),
    (("key_advantages", 0, "category"), "aim"),
    (("risks", 0, "severity"), "critical"),
])
def test_unknown_enums_are_rejected(path: tuple, value: str) -> None:
    payload = valid_analysis_payload()
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValidationError):
        MatchLLMAnalysis.model_validate(payload)


def test_unknown_evidence_ref_is_rejected() -> None:
    payload = valid_analysis_payload()
    payload["key_advantages"][0]["evidence_refs"] = ["series:does-not-exist"]
    with pytest.raises(MatchLLMAnalysisValidationError, match="unknown evidence refs"):
        validate(payload)


def test_llm_cannot_reverse_team_a_ml_favorite() -> None:
    payload = valid_analysis_payload()
    payload["conclusion"]["favored_team"] = "team_b"
    with pytest.raises(MatchLLMAnalysisValidationError, match="must be team_a"):
        validate(payload)


def test_team_a_ml_favorite_passes() -> None:
    validate(valid_analysis_payload())


def test_team_b_ml_favorite_passes() -> None:
    context = full_context_payload()
    context["prediction"]["team_a_probability"] = 0.4
    context["prediction"]["team_b_probability"] = 0.6
    context["matchup"]["team_a_score"] = 45.0
    context["matchup"]["team_b_score"] = 55.0
    payload = valid_analysis_payload()
    payload["conclusion"]["favored_team"] = "team_b"
    validate(payload, context)


def test_unavailable_prediction_requires_no_favorite() -> None:
    context = full_context_payload()
    context["prediction"].update({
        "status": "not_available",
        "team_a_probability": None,
        "team_b_probability": None,
    })
    payload = valid_analysis_payload()
    payload["conclusion"].update({"favored_team": "none", "advantage": "none"})
    validate(payload, context)


def test_insufficient_quality_requires_matching_status_and_confidence() -> None:
    context = full_context_payload()
    context["data_quality"]["overall_status"] = "insufficient"
    with pytest.raises(MatchLLMAnalysisValidationError, match="insufficient data quality"):
        validate(valid_analysis_payload(), context)


@pytest.mark.parametrize(("collection", "limit"), [
    ("key_advantages", 5),
    ("counter_arguments", 5),
    ("contradictions", 3),
    ("risks", 5),
])
def test_collection_limits(collection: str, limit: int) -> None:
    payload = valid_analysis_payload()
    seed = payload[collection][0]
    payload[collection] = []
    for index in range(limit + 1):
        item = deepcopy(seed)
        identity_key = "contradiction_id" if collection == "contradictions" else (
            "risk_id" if collection == "risks" else "claim_id"
        )
        item[identity_key] = f"{collection}:{index}"
        payload[collection].append(item)
    with pytest.raises(ValidationError):
        MatchLLMAnalysis.model_validate(payload)


def test_summary_character_limit() -> None:
    payload = valid_analysis_payload()
    payload["summary"] = "x" * 1501
    with pytest.raises(ValidationError):
        MatchLLMAnalysis.model_validate(payload)


def test_manual_note_claim_with_real_evidence_passes() -> None:
    payload = valid_analysis_payload()
    payload["key_advantages"][0].update({
        "category": "manual_context",
        "evidence_refs": ["note:1"],
    })
    validate(payload)


def test_manual_context_claim_requires_manual_note_ref() -> None:
    payload = valid_analysis_payload()
    payload["key_advantages"][0].update({
        "category": "manual_context",
        "evidence_refs": ["manual_context"],
    })
    with pytest.raises(MatchLLMAnalysisValidationError, match="manual analyst note"):
        validate(payload)


def test_context_v1_and_analysis_v1_are_compatible_and_json_serializable() -> None:
    context = MatchAnalysisContext.model_validate(full_context_payload())
    analysis = MatchLLMAnalysis.model_validate_json(
        MatchLLMAnalysis.model_validate(valid_analysis_payload()).model_dump_json()
    )
    MatchLLMAnalysisValidator().validate(context, analysis)
    assert analysis.context_schema_version == context.schema_version


def test_weak_data_quality_requires_limited_status() -> None:
    context_payload = full_context_payload()
    context_payload["data_quality"]["overall_status"] = "weak"
    with pytest.raises(MatchLLMAnalysisValidationError, match="requires analysis_status=limited"):
        validate(valid_analysis_payload(), context_payload)


def test_partial_data_quality_cannot_be_reported_as_insufficient() -> None:
    context_payload = full_context_payload()
    context_payload["data_quality"]["overall_status"] = "partial"
    payload = valid_analysis_payload()
    payload["analysis_status"] = "insufficient_data"
    with pytest.raises(
        MatchLLMAnalysisValidationError,
        match="requires insufficient data quality",
    ):
        validate(payload, context_payload)


def test_ml_matchup_conflict_requires_grounded_contradiction() -> None:
    context_payload = full_context_payload()
    context_payload["prediction"]["team_a_probability"] = 0.4
    context_payload["prediction"]["team_b_probability"] = 0.6
    payload = valid_analysis_payload()
    payload["conclusion"]["favored_team"] = "team_b"
    payload["contradictions"] = []
    with pytest.raises(MatchLLMAnalysisValidationError, match="opposing ML and Matchup"):
        validate(payload, context_payload)

    payload["contradictions"] = [{
        "contradiction_id": "contradiction:ml_matchup",
        "importance": "high",
        "description": "ML and deterministic matchup favor different sides.",
        "evidence_refs": ["prediction", "matchup"],
    }]
    validate(payload, context_payload)


@pytest.mark.parametrize("team_a_score", [47.0, 49.9, 50.0, 50.1, 53.0])
def test_neutral_matchup_does_not_conflict_with_ml(team_a_score: float) -> None:
    context_payload = full_context_payload()
    context_payload["matchup"]["team_a_score"] = team_a_score
    context_payload["matchup"]["team_b_score"] = 100 - team_a_score
    context_payload["prediction"]["team_a_probability"] = 0.4
    context_payload["prediction"]["team_b_probability"] = 0.6
    payload = valid_analysis_payload()
    payload["conclusion"]["favored_team"] = "team_b"
    payload["contradictions"] = []
    validate(payload, context_payload)


def test_business_validation_errors_have_safe_codes() -> None:
    payload = valid_analysis_payload()
    payload["conclusion"]["favored_team"] = "team_b"
    with pytest.raises(MatchLLMAnalysisValidationError) as caught:
        validate(payload)
    assert caught.value.codes == ("favorite_mismatch",)
