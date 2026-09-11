"""Independent map baseline. Reliability never adjusts strength scores."""
MODEL_VERSION = "map_strength.v3"
CALCULATION_REVISION = "v3.5.1"
COMPONENT_WEIGHTS = {"results_quality": .45, "side_performance": .25, "map_execution": .30}
EXECUTION_WEIGHTS = {"trading": .20, "utility": .20, "opening": .15, "entrying": .10,
                     "economy": .15, "postplant": .10, "retake": .10}
SIDE_WEIGHTS = {
    "ct": {"round_winrate": .35, "opening": .20, "economy": .15, "retake": .15, "conversion_recovery": .15},
    "t": {"round_winrate": .30, "opening": .20, "economy": .15, "postplant": .20, "conversion_recovery": .15},
}
ECONOMY_WEIGHTS = {"full_buy": .50, "force_buy": .15, "anti_eco": .20, "pistol_conversion": .15}
# Rare economy observations are unavailable until this many applicable rounds.
# This is an availability threshold, never a confidence multiplier on a score.
ECONOMY_MIN_SAMPLE = {"full_buy": 1, "force_buy": 5, "anti_eco": 5, "pistol_conversion": 5}
ROSTER_WEIGHTS = {5: 1., 4: .8, 3: .6, 2: .2, 1: 0., 0: 0.}
UNKNOWN_ROSTER_WEIGHT = .1
OLD_HISTORY_CAP = .25
HISTORY_DAYS = 730
LOW_SAMPLE_THRESHOLD = 40.
STATUS_THRESHOLDS = {"VERY_STRONG": 8., "STRONG": 3., "WEAK": -3., "VERY_WEAK": -8.}
RANK_GROUPS = ("top_1_10", "top_11_20", "top_21_30", "others", "unknown")
