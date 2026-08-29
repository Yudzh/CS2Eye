import json

from cs2eye.api.schemas.match_analysis_context import MatchAnalysisContext
from cs2eye.api.schemas.match_llm_analysis import MatchLLMAnalysis
from cs2eye.services.match_llm_grounding_validator import (
    CATEGORY_TYPES,
    MatchLLMGroundingValidator,
)
from cs2eye.services.match_llm_analysis_rules import matchup_favorite


PROMPT_VERSION = "match_analysis_prompt.v2"

SYSTEM_PROMPT = """You are the analytical explanation layer of CS2Eye, a CS2 pre-match analytics system.

MatchAnalysisContext is your only source. You may interpret supplied data; you may not create facts. Never use outside knowledge.

The ML prediction is immutable. Never reverse its favorite or estimate, adjust, or create a probability. You may quote an explicitly supplied probability with ordinary rounding. Never calculate new differences, averages, trends, percentages, probabilities, or other derived numerical values. If CS2Eye did not explicitly supply a value, describe the relationship qualitatively.

Every concrete factual statement must be supported by evidence_refs. Do not attach unrelated evidence merely to satisfy the schema. Never mention a team, player, coach, map, result, score, or numerical value unless it exists in the referenced evidence. Use evidence types appropriate to the claim category. Keep ML, deterministic analytics, statistics, manual notes, and data quality distinct.

When relying only on a manual analyst note, explicitly describe it as analyst-provided context, not verified statistical fact. Account for reliability and sample size. Do not turn missing veto, map, roster, or H2H data into a claim.

If ML and Matchup favorites differ, include a contradiction referencing both "prediction" and "matchup". Weak data requires limited status and lower confidence. Insufficient data requires insufficient_data and no favorite. Summary may only synthesize the conclusion and already-grounded claims, contradictions, risks, and limitations; it must add no number, entity, probability, result, or other fact.

Do not provide betting advice, bookmaker value, or stake sizing. Do not use tools. Return only MatchLLMAnalysis v1 structured data."""

LANGUAGE_INSTRUCTIONS = {
    "ru": "Напиши ВСЕ человекочитаемые поля только на русском. Ключи JSON и enum не переводи.",
    "en": "Write ALL human-readable fields only in English. Keep JSON keys and enum values unchanged.",
}


def build_system_prompt(language: str) -> str:
    return f"{SYSTEM_PROMPT}\n\n{LANGUAGE_INSTRUCTIONS[language]}"


def build_user_input(
    context: MatchAnalysisContext,
    language: str,
    repair_errors: tuple[str, ...] = (),
    allowed_evidence_refs: set[str] | None = None,
    previous_analysis: MatchLLMAnalysis | None = None,
) -> str:
    prediction = context.prediction
    favorite = "none"
    if (
        prediction.status == "available"
        and prediction.team_a_probability is not None
        and prediction.team_b_probability is not None
        and prediction.team_a_probability != prediction.team_b_probability
    ):
        favorite = (
            "team_a" if prediction.team_a_probability > prediction.team_b_probability
            else "team_b"
        )
    deterministic_favorite = matchup_favorite(context.matchup.team_a_score)
    matchup_conflict = (
        favorite in {"team_a", "team_b"}
        and deterministic_favorite is not None
        and deterministic_favorite != favorite
    )
    invariants = (
        f"\nMandatory backend invariants for this exact context:\n"
        f"- conclusion.favored_team MUST be {favorite}.\n"
        f"- analysis_status MUST be "
        f"{'limited' if context.data_quality.overall_status == 'weak' else 'insufficient_data' if context.data_quality.overall_status == 'insufficient' else 'complete or limited'}."
    )
    if matchup_conflict:
        invariants += (
            "\n- ML and Matchup favor opposite teams. contradictions MUST contain an "
            "item whose evidence_refs include BOTH prediction and matchup."
        )
    if repair_errors:
        instruction = (
            "Your previous analysis contains specific invalid or unsupported fields.\n\n- "
            + "\n- ".join(repair_errors)
            + "\n\nRepair the previous analysis in place. Preserve every claim, "
              "counter-argument, risk, limitation, and contradiction that is not named "
              "by an error. For each invalid item, correct its text or evidence_refs "
              "using MatchAnalysisContext; remove only that item if it cannot be "
              "supported. Keep the explanation detailed and useful. Rebuild the "
              "summary from the repaired grounded items. Do not introduce new facts."
        )
    else:
        instruction = "Analyze MatchAnalysisContext according to the system instructions."
    context_json = json.dumps(
        context.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"),
    )
    allowlist = ""
    if allowed_evidence_refs is not None:
        allowlist = "\nUse evidence_refs only from this allowlist: " + json.dumps(
            sorted(allowed_evidence_refs), ensure_ascii=False,
        )
        registry = MatchLLMGroundingValidator.build_evidence_registry(context)
        compatibility = {
            category: sorted(
                ref for ref in allowed_evidence_refs
                if ref in registry and registry[ref].type in evidence_types
            )
            for category, evidence_types in CATEGORY_TYPES.items()
        }
        allowlist += (
            "\nEvidence refs allowed for each claim/risk category (use only the list "
            "for the selected category): "
            + json.dumps(compatibility, ensure_ascii=False, separators=(",", ":"))
            + '\nEvery data_limitation must use only evidence_refs ["data_quality"].'
        )
    previous = ""
    if previous_analysis is not None:
        previous = "\nPrevious MatchLLMAnalysis: " + previous_analysis.model_dump_json()
    return f"{instruction}{invariants}\n{LANGUAGE_INSTRUCTIONS[language]}{allowlist}{previous}\n{context_json}"
