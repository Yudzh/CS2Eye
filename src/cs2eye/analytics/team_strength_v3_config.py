MODEL_VERSION = "team_strength.v3"
CALCULATION_REVISION = "team_strength.v3.3"

COMPONENT_WEIGHTS = {
    "roster_quality": 0.45,
    "team_execution": 0.25,
    "results_quality": 0.30,
}

ROSTER_WEIGHTS = {"average": 0.70, "top_2": 0.15, "bottom_2": 0.15}

EXECUTION_WEIGHTS = {
    "trading": 0.30,
    "utility": 0.30,
    "opening": 0.15,
    "entrying": 0.15,
    "clutching": 0.10,
}

RESULT_WEIGHTS = {"map_result": 0.70, "round_differential": 0.30}

# Roster applicability controls which historical evidence describes the selected
# five. It never changes Team Strength directly; it only selects/weights evidence.
ROSTER_APPLICABILITY_WEIGHTS = {"current": 1.0, "partial": 0.5, "old": 0.0, "unknown": 0.0}

RELIABILITY_TARGETS = {
    "current_roster_maps": 15,
    "current_roster_matches": 8,
    "rounds": 300,
    "results_maps": 20,
}

RELIABILITY_WEIGHTS = {
    "player_strength": 0.25,
    "current_roster_maps": 0.15,
    "current_roster_matches": 0.10,
    "rounds": 0.10,
    "team_performance_profile": 0.15,
    "opponent_rankings": 0.10,
    "results_coverage": 0.10,
    "roster_data_relevance": 0.05,
}
