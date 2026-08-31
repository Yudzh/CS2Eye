import json

from cs2eye.api.schemas.match_analysis_context import MatchAnalysisContext
from cs2eye.api.schemas.match_llm_analysis import MatchLLMAnalysis
from cs2eye.services.match_llm_grounding_validator import (
    CATEGORY_TYPES,
    MatchLLMGroundingValidator,
)
from cs2eye.services.match_llm_analysis_rules import matchup_favorite


PROMPT_VERSION = "match_analysis_prompt.v2"

SYSTEM_PROMPT = """Ты — слой аналитического объяснения CS2Eye, системы предматчевой аналитики CS2.

MatchAnalysisContext — твой единственный источник. Ты можешь интерпретировать переданные данные, но не можешь создавать факты. Никогда не используй внешние знания.

ML-прогноз неизменяем. Не меняй его фаворита, не оценивай, не корректируй и не создавай вероятность. Разрешено привести явно переданную вероятность с обычным округлением. Никогда не рассчитывай новые разницы, средние значения, тенденции, проценты, вероятности или другие производные числа. Если CS2Eye явно не передал значение, опиши отношение качественно.

Каждое конкретное фактическое утверждение должно подтверждаться evidence_refs. Не прикрепляй несвязанные доказательства только ради соответствия схеме. Не упоминай команду, игрока, тренера, карту, результат, счёт или число, если этого нет в указанном доказательстве. Используй тип доказательства, соответствующий категории тезиса. Разделяй ML, детерминированную аналитику, статистику, ручные заметки и качество данных.

Если тезис основан только на ручной заметке аналитика, явно называй его контекстом от аналитика, а не проверенным статистическим фактом. Учитывай надёжность и размер выборки. Не превращай отсутствие данных о вето, карте, составе или H2H в аналитический тезис.

Если фавориты ML и Matchup Score различаются, добавь противоречие со ссылками одновременно на "prediction" и "matchup". Слабые данные требуют статуса limited и пониженной уверенности. Недостаточные данные требуют insufficient_data и отсутствия фаворита. Итог может только обобщать заключение и уже подтверждённые тезисы, противоречия, риски и ограничения; он не должен добавлять числа, сущности, вероятности, результаты или другие факты.

Не давай советов по ставкам, не оценивай выгоду коэффициентов и размер ставки. Не используй инструменты. Верни только структурированные данные MatchLLMAnalysis v1."""

LANGUAGE_INSTRUCTIONS = {
    "ru": "Напиши ВСЕ человекочитаемые поля только на русском. Ключи JSON и enum не переводи.",
    "en": "Напиши ВСЕ человекочитаемые поля только на английском. Ключи JSON и значения enum не переводи.",
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
        f"\nОбязательные backend-инварианты для этого контекста:\n"
        f"- conclusion.favored_team ОБЯЗАН иметь значение {favorite}.\n"
        f"- analysis_status ОБЯЗАН иметь значение "
        f"{'limited' if context.data_quality.overall_status == 'weak' else 'insufficient_data' if context.data_quality.overall_status == 'insufficient' else 'complete or limited'}."
    )
    if matchup_conflict:
        invariants += (
            "\n- ML и Matchup Score отдают преимущество разным командам. contradictions "
            "ОБЯЗАН содержать пункт, где evidence_refs одновременно включает prediction и matchup."
        )
    if repair_errors:
        instruction = (
            "Предыдущий анализ содержит конкретные некорректные или неподтверждённые поля.\n\n- "
            + "\n- ".join(repair_errors)
            + "\n\nИсправь предыдущий анализ на месте. Сохрани каждый тезис, контраргумент, "
              "риск, ограничение и противоречие, не названные в ошибках. Для каждого "
              "некорректного пункта исправь текст или evidence_refs по MatchAnalysisContext; "
              "удаляй пункт только тогда, когда его невозможно подтвердить. Сохрани "
              "объяснение подробным и полезным. Пересобери итог из исправленных "
              "подтверждённых пунктов. Не добавляй новые факты."
        )
    else:
        instruction = "Проанализируй MatchAnalysisContext по системным инструкциям."
    context_json = json.dumps(
        context.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"),
    )
    allowlist = ""
    if allowed_evidence_refs is not None:
        allowlist = "\nИспользуй evidence_refs только из этого разрешённого списка: " + json.dumps(
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
            "\nРазрешённые evidence_refs для каждой категории тезиса или риска "
            "(используй только список выбранной категории): "
            + json.dumps(compatibility, ensure_ascii=False, separators=(",", ":"))
            + '\nКаждый data_limitation должен использовать только evidence_refs ["data_quality"].'
        )
    previous = ""
    if previous_analysis is not None:
        previous = "\nПредыдущий MatchLLMAnalysis: " + previous_analysis.model_dump_json()
    return f"{instruction}{invariants}\n{LANGUAGE_INSTRUCTIONS[language]}{allowlist}{previous}\n{context_json}"
