from dataclasses import dataclass

OPPONENT_CONTEXT_VERSION="opponent_context_v1"
ADJUSTED_FORM_VERSION="opponent_adjusted_form_v1_candidate"

@dataclass(frozen=True)
class OpponentContextConfig:
    component_weights:dict[str,float]
    window_days:int=60
    decay_days:float=28.0
    tournament_multiplier:float=1.25
    target_sample:int=6
    margin_modifier:float=.05

OPPONENT_CONTEXT_CONFIG=OpponentContextConfig({
    "base_team_strength":.35,"ranking_strength":.15,"recent_form":.20,
    "tournament_form":.15,"strength_of_schedule":.10,"performance_expectation":.05,
})
