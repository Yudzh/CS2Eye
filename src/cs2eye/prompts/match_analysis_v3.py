import json

from cs2eye.api.schemas.match_explanation_plan import MatchExplanationPlan
from cs2eye.api.schemas.match_llm_analysis_v2 import MatchLLMAnalysisV2


PROMPT_VERSION = "match_analysis_prompt.v3"

_LANGUAGE_REPAIR_MARKERS = (
    "human-readable text must be Russian",
    "English prose is not allowed",
)

SYSTEM_PROMPT = """Ты — слой текстового объяснения CS2Eye.

Все аналитические решения уже приняты системой CS2Eye.

Не определяй фаворита и не решай, какие факторы являются преимуществами или контраргументами. Не изменяй уверенность, серьёзность, важность, силу, сторону или надёжность. Не добавляй факты, расчёты, команды, игроков, карты, результаты, числа или события. Не переосмысливай слабые данные.

Твоя единственная задача — преобразовать переданный MatchExplanationPlan в краткий и естественный аналитический текст на русском языке. Сохраняй точный смысл и направление каждого пункта. Используй названия команд, а не обозначения team_a/team_b. Ручные сигналы обязательно описывай как контекст от аналитика, а не как проверенную статистику.

Семантические правила: `matchup` означает общую детерминированную оценку Matchup Score, а не текущую форму. `ml_vs_matchup` означает, что ML-модель и детерминированная оценка матчапа отдают преимущество разным командам. Описывай противоречия по переданным left_side/right_side и facts; не заменяй один аналитический слой другим.

Верни текст строго для переданных ID. Каждый пункт с высокой важностью или серьёзностью обязателен. Не придумывай ID. Все человекочитаемые поля пиши на русском языке. Верни только структурированные данные MatchLLMAnalysis v2."""


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
        language_repair_required = any(
            marker in error
            for error in repair_errors
            for marker in _LANGUAGE_REPAIR_MARKERS
        )
        displayed_errors = tuple(
            (
                "Текст должен быть на русском языке; английская проза запрещена. "
                f"Удали или переведи указанные валидатором слова: {error.partition(':')[2].strip()}."
                if error.startswith("English prose is not allowed:")
                else "Текст должен быть на русском языке; английская проза запрещена."
            )
            if any(marker in error for marker in _LANGUAGE_REPAIR_MARKERS)
            else error
            for error in repair_errors
        )
        task += (
            "\nИсправь предыдущий текст только по этим ошибкам:\n- "
            + "\n- ".join(displayed_errors)
        )
        if language_repair_required:
            task += (
                "\nКритически важно: полностью перепиши summary и все значения "
                "в секциях *_texts на русском языке. Каждое текстовое поле должно "
                "содержать осмысленное предложение кириллицей. Не оставляй "
                "английские предложения. Латиницей допустимы только точные названия "
                "команд, игроков, карт и продуктов, присутствующие в плане."
            )
    payload = json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
    previous = (
        "\nПредыдущий ответ: " + previous_analysis.model_dump_json()
        if previous_analysis is not None else ""
    )
    return f"{task}\nMatchExplanationPlan: {payload}{previous}"
