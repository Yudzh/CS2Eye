import json

from cs2eye.api.schemas.match_explanation_plan_v2 import MatchExplanationPlanV2
from cs2eye.api.schemas.match_llm_analysis_v3 import MatchLLMAnalysisV3


PROMPT_VERSION = "match_analysis_prompt.v5"

SYSTEM_PROMPT = """Ты — только русскоязычный слой формулировки CS2Eye.

CS2Eye уже выполнила весь анализ и передала фиксированный MatchExplanationPlan: expected_winner и пять разделов conclusion, form, maps, teamplay, manual_context.

Не перемещай факты между разделами. Не создавай новые аналитические выводы. Не добавляй команды, игроков, карты, результаты, статистику или числа. Ничего не рассчитывай. Не меняй фаворита, величину преимущества или уверенность. Пиши кратко и естественно на русском языке.

Переводи технические значения на естественный русский: strong/good/mixed/weak, small/moderate/clear, ct_side/t_side, anti_eco, force_buy и другие enum нельзя оставлять как английские служебные слова.

Структура ответа всегда одинакова и содержит ровно шесть текстовых полей.

EXPECTED_WINNER: если expected_winner передан, дословно сохрани команду и вероятность и сформулируй: «По расчётам должна выиграть TEAM — N%.» Не определяй победителя самостоятельно. Если expected_winner=null, напиши: «Расчёт победителя недоступен.»

CONCLUSION: объясни только готовое deterministic-заключение. Явно укажи, что преимущество основано на внутренней статистике CS2Eye, а форма текущего турнира рассматривается отдельно.

FORM: описывай только переданный турнирный контекст. При state=not_started обязательно скажи, что турнир только начинается и команды ещё не сформировали турнирную форму. Используй previous_tournament только когда он передан как fallback. Не упоминай карты или teamplay.

MAPS: назови только переданные сильные и слабые карты обеих команд и объясни только переданные key_map_edges и reasons. Не добавляй неизвестные карты. Если status=insufficient, честно сообщи о недостатке надёжных данных.

TEAMPLAY: описывай только переданные signals. Не переноси сюда форму, карты целиком или ручные заметки. Если signals пуст, используй переданную context_notes.

MANUAL: явно называй заметки ручными комментариями аналитика. Не выдавай их за статистику. Если заметок нет, используй empty_message.

Не добавляй заголовки: сайт и Telegram формируют их сами. Не давай рекомендаций по ставкам. Верни только MatchLLMAnalysis v3."""


def build_system_prompt() -> str:
    return SYSTEM_PROMPT


def build_user_input(
    plan: MatchExplanationPlanV2,
    repair_errors: tuple[str, ...] = (),
    previous_analysis: MatchLLMAnalysisV3 | None = None,
) -> str:
    task = "Сформулируй пять фиксированных секций строго по MatchExplanationPlanV2."
    if repair_errors:
        task += "\nИсправь предыдущий ответ по ошибкам, не меняя корректные секции:\n- " + "\n- ".join(repair_errors)
    previous = "\nПредыдущий ответ: " + previous_analysis.model_dump_json() if previous_analysis else ""
    payload = json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
    return f"{task}\nMatchExplanationPlanV2: {payload}{previous}"
