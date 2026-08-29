"""Declarative constraints for a future MatchAnalysisContext interpreter."""


MATCHUP_NEUTRAL_MIN = 47.0
MATCHUP_NEUTRAL_MAX = 53.0


def matchup_favorite(team_a_score: float | None) -> str | None:
    """Apply the same neutral band used by MatchupService."""
    if team_a_score is None:
        return None
    if team_a_score > MATCHUP_NEUTRAL_MAX:
        return "team_a"
    if team_a_score < MATCHUP_NEUTRAL_MIN:
        return "team_b"
    return None

MATCH_LLM_ANALYSIS_LIMITS = {
    "key_advantages": 5,
    "counter_arguments": 5,
    "contradictions": 3,
    "risks": 5,
    "summary_characters": 1500,
}

MATCH_LLM_MUST = (
    "use_only_match_analysis_context",
    "treat_ml_probability_as_immutable",
    "explain_the_primary_ml_prediction",
    "account_for_reliability",
    "account_for_sample_size",
    "account_for_data_quality",
    "separate_ml_deterministic_and_manual_sources",
    "surface_material_contradictions",
    "state_data_limitations",
    "allow_insufficient_data",
    "ground_every_claim_in_evidence",
)

MATCH_LLM_MUST_NOT = (
    "calculate_win_probability",
    "change_ml_probability",
    "reverse_an_available_ml_favorite",
    "use_external_or_implicit_team_knowledge",
    "invent_match_results",
    "invent_roster_changes",
    "invent_maps_or_veto",
    "present_manual_notes_as_statistical_facts",
    "hide_weak_reliability",
    "make_a_confident_conclusion_when_data_is_insufficient",
)
