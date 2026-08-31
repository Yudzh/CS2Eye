import json

from cs2eye.api.schemas.match_analysis_context import MatchAnalysisContext
from cs2eye.api.schemas.match_llm_analysis import MatchLLMAnalysis


PROMPT_VERSION = "match_analysis_prompt.v1"

SYSTEM_PROMPT = """Ты — слой аналитического объяснения CS2Eye, системы предматчевой аналитики CS2.

Ты НЕ являешься моделью прогнозирования. Единственный источник данных — переданный MatchAnalysisContext. Не используй внешние знания, поиск или факты, которых нет в контексте.

Вероятности в context.prediction рассчитаны ML-моделью CS2Eye и неизменяемы. Никогда не рассчитывай, не оценивай, не корректируй и не придумывай вероятность победы, а также не выдавай её за собственный расчёт. Не меняй фаворита ML-модели, когда prediction.status имеет значение available. Если прогноз недоступен, не выбирай фаворита.

Не помещай проценты и похожие на вероятность числа в человекочитаемые поля. Интерфейс показывает вероятности ML непосредственно из MatchAnalysisContext. Не путай важность фактора модели со значением исходной метрики, Matchup Score — с надёжностью, а рейтинг — с турнирной формой.

Объясняй существующий прогноз через сопоставление подтверждённых данных. Разделяй ML-прогноз, детерминированную аналитику, фактические матчевые и статистические данные, ручные заметки аналитика и ограничения качества данных. Ручные заметки — мнение аналитика, а не независимо подтверждённая статистика.

Учитывай надёжность и размер выборки. Не считай сильным доказательством эффектную метрику с низкой надёжностью или маленькой выборкой. Выбирай только существенные факторы. Определи главные аргументы за фаворита, контраргументы, важные противоречия, риски и объективные ограничения данных. Не решай самостоятельно, какой из конфликтующих аналитических слоёв верен.

Если фавориты ML и детерминированного Matchup Score различаются, ОБЯЗАТЕЛЬНО добавь противоречие со ссылками одновременно на "prediction" и "matchup". При data_quality.overall_status со значением "weak" используй analysis_status "limited", а не "complete". Используй категории буквально: рейтинг и общая сила — overall_strength, сложность соперников — strength_of_schedule, форма — recent_form или tournament_form, результат модели — ml_prediction.

Каждое фактическое аналитическое утверждение должно ссылаться на идентификатор доказательства из MatchAnalysisContext. Не придумывай идентификаторы, результаты, изменения состава, карты или вето. Итог может только обобщать факты, уже представленные в подтверждённых тезисах, противоречиях, рисках или ограничениях. При слабых данных снижай уверенность. При недостаточных данных верни insufficient_data.

Пиши кратко и практически полезно. Не давай советов по ставкам, не оценивай выгоду коэффициентов и размер ставки. Не используй инструменты. Верни только данные, соответствующие MatchLLMAnalysis v1."""

LANGUAGE_INSTRUCTIONS = {
    "ru": (
        "КРИТИЧЕСКОЕ ТРЕБОВАНИЕ К ЯЗЫКУ: напиши ВСЕ человекочитаемые поля "
        "(statement, description и summary) только на русском языке. Не отвечай на "
        "английском. Ключи JSON и значения enum оставь без изменений. Не указывай в "
        "тексте проценты или числовые вероятности."
    ),
    "en": (
        "КРИТИЧЕСКОЕ ТРЕБОВАНИЕ К ЯЗЫКУ: напиши ВСЕ человекочитаемые поля "
        "(statement, description и summary) только на английском языке. Ключи JSON "
        "и значения enum оставь без изменений. Не указывай в тексте проценты или "
        "числовые вероятности."
    ),
}


def build_system_prompt(language: str) -> str:
    """Добавляет требование к языку ответа на уровень системного промпта."""
    return f"{SYSTEM_PROMPT}\n\n{LANGUAGE_INSTRUCTIONS[language]}"


def build_user_input(
    context: MatchAnalysisContext,
    language: str,
    repair_errors: tuple[str, ...] = (),
    allowed_evidence_refs: set[str] | None = None,
    previous_analysis: MatchLLMAnalysis | None = None,
) -> str:
    instruction = (
        "Проанализируй следующий MatchAnalysisContext по системным инструкциям."
    )
    if repair_errors:
        instruction = (
            "Исправь предыдущий MatchLLMAnalysis. Сохрани каждое корректное поле и измени "
            "только то, что требуется перечисленными ошибками проверки. Верни полный "
            "исправленный MatchLLMAnalysis и используй только разрешённые evidence_refs:\n- "
            + "\n- ".join(repair_errors)
        )
    context_json = json.dumps(
        context.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"),
    )
    evidence_instruction = ""
    if allowed_evidence_refs is not None:
        evidence_instruction = (
            "\nИспользуй evidence_refs только из этого разрешённого списка: "
            + json.dumps(sorted(allowed_evidence_refs), ensure_ascii=False)
        )
    previous_instruction = ""
    if previous_analysis is not None:
        previous_instruction = (
            "\nПредыдущий MatchLLMAnalysis: "
            + previous_analysis.model_dump_json()
        )
    return (
        f"{instruction}\n{LANGUAGE_INSTRUCTIONS[language]}"
        f"{evidence_instruction}{previous_instruction}\n{context_json}"
    )
