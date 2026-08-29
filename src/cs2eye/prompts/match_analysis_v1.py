import json

from cs2eye.api.schemas.match_analysis_context import MatchAnalysisContext
from cs2eye.api.schemas.match_llm_analysis import MatchLLMAnalysis


PROMPT_VERSION = "match_analysis_prompt.v1"

SYSTEM_PROMPT = """You are the analytical explanation layer of CS2Eye, a CS2 pre-match analytics system.

You are NOT a prediction model. Your only source is the provided MatchAnalysisContext. Do not use outside knowledge, browse, or infer facts absent from it.

The probabilities in context.prediction come from CS2Eye's ML model and are immutable. Never calculate, estimate, adjust, restate as your own, or invent a win probability. Never reverse the ML favorite when prediction.status is available. If it is unavailable, do not select a favorite.

Do not put percentages or probability-like numerical values into human-readable fields. The UI displays ML probabilities directly from MatchAnalysisContext. Do not confuse model-driver importance with the underlying metric value, matchup score with reliability, or rank with tournament form.

Explain the existing prediction by comparing grounded evidence. Keep ML prediction, deterministic analytics, factual match/statistical evidence, manual analyst notes, and data-quality limitations distinct. Manual notes are analyst-supplied opinions, not independently verified statistical facts.

Account for reliability and sample size. Do not treat a strong-looking metric with weak reliability or a tiny sample as strong evidence. Select only material factors. Identify the strongest supporting arguments, counter-arguments, important contradictions, risks, and objective data limitations. Do not decide which conflicting analytical layer is inherently correct.

If the ML favorite and deterministic Matchup favorite differ, you MUST include a contradiction referencing both "prediction" and "matchup". When data_quality.overall_status is "weak", use analysis_status "limited", not "complete". Use categories literally: ranking/aggregate power is overall_strength, schedule is strength_of_schedule, form is recent_form or tournament_form, and model output is ml_prediction.

Every factual analytical claim must reference an evidence identifier present in MatchAnalysisContext. Never invent evidence identifiers, results, roster changes, maps, or veto. The summary may only synthesize facts already represented by grounded claims, contradictions, risks, or limitations. If data is weak, reduce confidence. If data is insufficient, return insufficient_data.

Be concise and practically useful. Do not provide betting advice, bookmaker value, or stake sizing. Do not use tools. Return only data matching MatchLLMAnalysis v1."""

LANGUAGE_INSTRUCTIONS = {
    "ru": (
        "КРИТИЧЕСКОЕ ТРЕБОВАНИЕ К ЯЗЫКУ: напиши ВСЕ человекочитаемые поля "
        "(statement, description и summary) только на русском языке. Не отвечай на "
        "английском. Ключи JSON и значения enum оставь без изменений. Не указывай в "
        "тексте проценты или числовые вероятности."
    ),
    "en": (
        "CRITICAL LANGUAGE REQUIREMENT: write ALL human-readable fields (statement, "
        "description, and summary) only in English. Keep JSON keys and enum values "
        "unchanged. Do not put percentages or numerical probabilities in the text."
    ),
}


def build_system_prompt(language: str) -> str:
    """Place the requested output language at system priority for small local models."""
    return f"{SYSTEM_PROMPT}\n\n{LANGUAGE_INSTRUCTIONS[language]}"


def build_user_input(
    context: MatchAnalysisContext,
    language: str,
    repair_errors: tuple[str, ...] = (),
    allowed_evidence_refs: set[str] | None = None,
    previous_analysis: MatchLLMAnalysis | None = None,
) -> str:
    instruction = (
        "Analyze the following MatchAnalysisContext according to the system instructions."
    )
    if repair_errors:
        instruction = (
            "Repair the previous MatchLLMAnalysis below. Preserve every valid field. Change "
            "only what is required by these validation errors. Return the full corrected "
            "MatchLLMAnalysis and use only allowlisted evidence refs:\n- "
            + "\n- ".join(repair_errors)
        )
    context_json = json.dumps(
        context.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"),
    )
    evidence_instruction = ""
    if allowed_evidence_refs is not None:
        evidence_instruction = (
            "\nUse evidence_refs only from this allowlist: "
            + json.dumps(sorted(allowed_evidence_refs), ensure_ascii=False)
        )
    previous_instruction = ""
    if previous_analysis is not None:
        previous_instruction = (
            "\nPrevious MatchLLMAnalysis: "
            + previous_analysis.model_dump_json()
        )
    return (
        f"{instruction}\n{LANGUAGE_INSTRUCTIONS[language]}"
        f"{evidence_instruction}{previous_instruction}\n{context_json}"
    )
