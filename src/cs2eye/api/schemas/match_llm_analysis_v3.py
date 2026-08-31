from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MatchLLMAnalysisV3(BaseModel):
    """Russian wording for five immutable backend-owned sections."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["match_llm_analysis.v3"] = "match_llm_analysis.v3"
    explanation_plan_version: Literal["match_explanation_plan.v2"] = "match_explanation_plan.v2"
    # Optional only so already persisted v3 runs remain readable.
    expected_winner_text: str | None = Field(default=None, min_length=1, max_length=500)
    conclusion_text: str = Field(min_length=1, max_length=1800)
    form_text: str = Field(min_length=1, max_length=2400)
    maps_text: str = Field(min_length=1, max_length=2400)
    teamplay_text: str = Field(min_length=1, max_length=2400)
    manual_text: str = Field(min_length=1, max_length=2400)
