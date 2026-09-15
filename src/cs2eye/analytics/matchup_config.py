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

# matchup_v3 sources map_veto/team_strength/tactical_matchup from Team/Map Strength V3.
# current_roster_form is retired: V3 already down-weights stale-roster evidence internally
# (roster applicability in Team/Map Strength V3), so a separate upper factor for it would
# double-count. map_veto compares each team's Map Strength V3 delta_vs_team (map score minus
# that team's own Team Strength V3 baseline) instead of raw map scores, so it does not
# re-include the baseline already carried by the team_strength factor. matchup_v1 and
# matchup_v2_candidate (the legacy 7-factor engine this superseded) were removed once
# AnalyticsAsOfService gained V3-aware historical reconstruction and backtesting confirmed v3.
MATCHUP_V3_CONFIG = MatchupModelConfig("matchup_v3", {
    "map_veto": FactorConfig(.34,"gated",.30,6), "team_strength": FactorConfig(.26,"linear",.10,5),
    "form_context": FactorConfig(.17,"linear",.15,4),
    "tactical_matchup": FactorConfig(.09,"conservative",.25,2), "h2h": FactorConfig(.09,"thresholded",.30,2),
    "leadership_context": FactorConfig(.05,"conservative",.30,1)}, False, "coverage_agreement", .80, .85)
MATCHUP_CONFIGS = {MATCHUP_V3_CONFIG.version: MATCHUP_V3_CONFIG}
ACTIVE_MATCHUP_CONFIG = MATCHUP_V3_CONFIG
MATCHUP_MODEL_VERSION = ACTIVE_MATCHUP_CONFIG.version
MATCHUP_WEIGHTS = {k:v.weight for k,v in ACTIVE_MATCHUP_CONFIG.factors.items()}
# tactical_matchup under matchup_v3 only keeps components that are genuinely pairwise/directional
# (T vs opponent CT, postplant vs opponent retake) and not already folded into Map Strength V3's
# own map_execution component (which already covers economy/utility/trading/opening).
TACTICAL_WEIGHTS_V3 = {"side": .6, "bomb": .4}
