from cs2eye.api.schemas.match_explanation_plan import MatchExplanationPlan
from cs2eye.api.schemas.match_llm_analysis_v2 import MatchLLMAnalysisV2
from cs2eye.api.schemas.match_llm_runtime import (
    RenderedExplanationItem, RenderedMatchExplanation,
)


def assemble_match_explanation(
    plan: MatchExplanationPlan, wording: MatchLLMAnalysisV2,
) -> RenderedMatchExplanation:
    def items(rows, texts, identifier):
        result = []
        for row in rows:
            item_id = getattr(row, identifier)
            if item_id not in texts:
                continue
            result.append(RenderedExplanationItem(
                id=item_id, text=texts[item_id],
                metadata=row.model_dump(mode="json"),
            ))
        return result
    return RenderedMatchExplanation(
        conclusion=plan.conclusion.model_dump(mode="json"), summary=wording.summary,
        advantages=items(plan.advantages, wording.advantage_texts, "signal_id"),
        counter_arguments=items(
            plan.counter_arguments, wording.counter_argument_texts, "signal_id",
        ),
        contradictions=items(
            plan.contradictions, wording.contradiction_texts, "contradiction_id",
        ),
        risks=items(plan.risks, wording.risk_texts, "risk_id"),
        limitations=items(plan.limitations, wording.limitation_texts, "limitation_id"),
    )
