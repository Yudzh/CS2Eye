from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


Text = Annotated[str, Field(min_length=1, max_length=1000)]


class MatchLLMAnalysisV2(BaseModel):
    """Text-only provider output. All analytical metadata lives in the plan."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["match_llm_analysis.v2"] = "match_llm_analysis.v2"
    explanation_plan_version: Literal["match_explanation_plan.v1"] = (
        "match_explanation_plan.v1"
    )
    summary: Annotated[str, Field(min_length=1, max_length=1500)]
    advantage_texts: dict[str, Text]
    counter_argument_texts: dict[str, Text]
    contradiction_texts: dict[str, Text]
    risk_texts: dict[str, Text]
    limitation_texts: dict[str, Text]
