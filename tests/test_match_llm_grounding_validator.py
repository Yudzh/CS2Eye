from cs2eye.api.schemas.match_analysis_context import MatchAnalysisContext
from cs2eye.api.schemas.match_llm_analysis import MatchLLMAnalysis
from cs2eye.services.match_llm_grounding_validator import MatchLLMGroundingValidator
from tests.test_match_analysis_context import full_context_payload
from tests.test_match_llm_analysis import valid_analysis_payload


def grounded(payload=None, context_payload=None):
    context = MatchAnalysisContext.model_validate(context_payload or full_context_payload())
    analysis = MatchLLMAnalysis.model_validate(payload or valid_analysis_payload())
    return MatchLLMGroundingValidator().validate(context, analysis)


def codes(result):
    return {error.code for error in result.errors}


def test_grounded_analysis_passes_and_registry_contains_fact_payloads():
    context = MatchAnalysisContext.model_validate(full_context_payload())
    registry = MatchLLMGroundingValidator.build_evidence_registry(context)
    assert grounded().valid
    assert registry["prediction"].facts["team_a_probability"] == 0.58
    assert registry["series:123"].facts["opponent"]["name"] == "Falcons"
    assert registry["map:mirage:ct_side"].type == "map_edge"


def test_unsupported_probability_is_rejected_but_rounding_passes():
    payload = valid_analysis_payload()
    payload["key_advantages"][0].update({
        "category": "ml_prediction", "evidence_refs": ["prediction"],
        "statement": "Spirit has a 64% chance to win.",
    })
    assert "probability_hallucination" in codes(grounded(payload))
    payload["key_advantages"][0]["statement"] = "Spirit has about 58% according to ML."
    assert grounded(payload).valid


def test_unsupported_statistic_and_derived_number_are_rejected():
    payload = valid_analysis_payload()
    payload["key_advantages"][0]["statement"] = "The strength score is 63.5."
    assert "unsupported_number" in codes(grounded(payload))
    payload["key_advantages"][0].update({
        "category": "ml_prediction", "evidence_refs": ["prediction"],
        "statement": "The advantage is 16 percentage points.",
    })
    assert "unsupported_number" in codes(grounded(payload))


def test_invented_map_is_rejected_when_map_data_is_empty():
    context = full_context_payload()
    context["veto"]["likely_maps"] = []
    context["map_matchups"] = []
    payload = valid_analysis_payload()
    payload["key_advantages"][0].update({
        "category": "map_pool", "evidence_refs": ["prediction"],
        "statement": "Spirit is stronger on Nuke.",
    })
    result = grounded(payload, context)
    assert {"unknown_map", "incompatible_evidence"} <= codes(result)


def test_invented_recent_opponent_is_rejected_and_valid_opponent_passes():
    payload = valid_analysis_payload()
    payload["counter_arguments"][0].update({
        "category": "recent_form", "evidence_refs": ["series:123"],
        "statement": "Spirit recently defeated Vitality.",
    })
    assert "unknown_team" in codes(grounded(payload))
    payload["counter_arguments"][0]["statement"] = "Spirit recently defeated Falcons."
    assert grounded(payload).valid


def test_invented_player_is_rejected():
    payload = valid_analysis_payload()
    payload["key_advantages"][0].update({
        "category": "roster", "evidence_refs": ["team:1:roster"],
        "statement": "Player m0NESY improves the roster.",
    })
    assert "unknown_player" in codes(grounded(payload))


def test_evidence_type_mismatch_is_rejected():
    payload = valid_analysis_payload()
    payload["key_advantages"][0].update({
        "category": "ct_side", "evidence_refs": ["series:123"],
    })
    assert "incompatible_evidence" in codes(grounded(payload))


def test_manual_only_kind_and_manual_statistical_misuse():
    payload = valid_analysis_payload()
    payload["key_advantages"][0].update({
        "category": "manual_context", "evidence_refs": ["note:1"],
        "statement": "Analyst-provided context describes a stable roster.",
    })
    result = grounded(payload)
    assert result.valid
    assert result.evidence_kinds["advantage:1"] == "manual"
    payload["key_advantages"][0]["statement"] = "Statistics confirm the stable roster."
    assert "manual_note_misuse" in codes(grounded(payload))


def test_summary_rejects_new_number_and_map():
    payload = valid_analysis_payload()
    payload["summary"] = "Spirit has a 64% chance and is stronger on Nuke."
    result = grounded(payload)
    assert "summary_unsupported_fact" in codes(result)
    assert "unknown_map" in codes(result)


def test_summary_rejects_opposite_favorite():
    payload = valid_analysis_payload()
    payload["summary"] = "Falcons are the favorite despite the arguments above."
    assert "summary_unsupported_fact" in codes(grounded(payload))


def test_missing_evidence_is_reported_for_constructed_analysis():
    # min_length normally stops this at the schema boundary; model_construct verifies
    # the grounding layer remains defensive when called internally.
    analysis = MatchLLMAnalysis.model_validate(valid_analysis_payload())
    claim = analysis.key_advantages[0].model_copy(update={"evidence_refs": []})
    analysis = analysis.model_copy(update={"key_advantages": [claim]})
    context = MatchAnalysisContext.model_validate(full_context_payload())
    result = MatchLLMGroundingValidator().validate(context, analysis)
    assert "missing_evidence" in codes(result)
