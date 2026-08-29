import json

from cs2eye.api.schemas.match_explanation_plan import MatchExplanationPlan
from cs2eye.api.schemas.match_llm_analysis_v2 import MatchLLMAnalysisV2


PROMPT_VERSION = "match_analysis_prompt.v3"

SYSTEM_PROMPT = """You are the writing layer for CS2Eye.

All analytical decisions have already been made by CS2Eye.

Do not determine the favorite. Do not decide which factors are advantages or counter-arguments. Do not change confidence, severity, importance, strength, side, or reliability. Do not add facts, calculations, teams, players, maps, results, numbers, or events. Do not reinterpret weak evidence.

Your only task is to convert the supplied MatchExplanationPlan into concise, natural Russian analytical text. Preserve the exact meaning and direction of every supplied item. Use team names, never team_a/team_b aliases. Manual signals must explicitly be described as analyst-provided context, not verified statistics.

Semantic rules: `matchup` means the aggregate deterministic Matchup Score, not recent form. `ml_vs_matchup` means that the ML favorite and deterministic Matchup Score favor opposite teams. Describe contradictions using their supplied left_side/right_side and facts; never replace an analytical layer with a different concept.

Return text for exactly the supplied IDs. Every high-importance or high-severity item is mandatory. Do not invent IDs. Write every human-readable field in Russian. Return only MatchLLMAnalysis v2 structured data."""


def build_system_prompt() -> str:
    return SYSTEM_PROMPT


def build_user_input(
    plan: MatchExplanationPlan, repair_errors: tuple[str, ...] = (),
    previous_analysis: MatchLLMAnalysisV2 | None = None,
) -> str:
    task = (
        "Сформулируй текст для каждого ID из плана. Не повторяй числовые значения; "
        "описывай величину словами согласно strength."
    )
    if repair_errors:
        task += (
            "\nИсправь предыдущий текст только по этим ошибкам:\n- "
            + "\n- ".join(repair_errors)
        )
    payload = json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
    previous = (
        "\nПредыдущий ответ: " + previous_analysis.model_dump_json()
        if previous_analysis is not None else ""
    )
    return f"{task}\nMatchExplanationPlan: {payload}{previous}"
