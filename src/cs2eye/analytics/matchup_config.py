from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class FactorConfig:
    weight: float
    reliability_mode: str = "none"
    min_reliability: float = 0.0
    max_effect: float = 50.0

@dataclass(frozen=True)
class MatchupModelConfig:
    version: str
    factors: dict[str, FactorConfig]
    redistribute_missing_weight: bool
    overall_mode: str
    coverage_floor: float = 0.0
    agreement_floor: float = 0.0

_WEIGHTS = {"map_veto": .30, "team_strength": .23, "form_context": .15,
            "current_roster_form": .12, "tactical_matchup": .08,
            "h2h": .08, "leadership_context": .04}
MATCHUP_V1_CONFIG = MatchupModelConfig("matchup_v1", {k: FactorConfig(v) for k,v in _WEIGHTS.items()}, True, "legacy")
MATCHUP_V2_CONFIG = MatchupModelConfig("matchup_v2_candidate", {
    "map_veto": FactorConfig(.30,"gated",.30,6), "team_strength": FactorConfig(.23,"linear",.10,5),
    "form_context": FactorConfig(.15,"linear",.15,4), "current_roster_form": FactorConfig(.12,"linear",.15,3),
    "tactical_matchup": FactorConfig(.08,"conservative",.25,2), "h2h": FactorConfig(.08,"thresholded",.30,2),
    "leadership_context": FactorConfig(.04,"conservative",.30,1)}, False, "coverage_agreement", .80, .85)
MATCHUP_CONFIGS = {x.version:x for x in (MATCHUP_V1_CONFIG,MATCHUP_V2_CONFIG)}
ACTIVE_MATCHUP_CONFIG = MATCHUP_V1_CONFIG
MATCHUP_MODEL_VERSION = ACTIVE_MATCHUP_CONFIG.version
MATCHUP_WEIGHTS = {k:v.weight for k,v in ACTIVE_MATCHUP_CONFIG.factors.items()}
TACTICAL_WEIGHTS = {"side":.25,"bomb":.20,"combat_swing":.20,"economy":.15,"utility":.10,"trading":.10}
