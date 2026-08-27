WIN_PROBABILITY_MODEL_VERSION = "v1"
WIN_PROBABILITY_FEATURE_SCHEMA_VERSION = "matchup_features_v2"
MIN_HISTORICAL_MAPS_PER_TEAM = 3
MIN_PREDICTION_CONFIDENCE = .25

WIN_PROBABILITY_FEATURES = [
    "matchup_score_centered", "raw_matchup_centered", "matchup_reliability_advantage",
    "team_strength_difference", "map_pool_advantage", "current_roster_advantage",
    "tactical_advantage", "h2h_advantage", "leadership_advantage",
    "ranking_advantage", "format_bo1_strength", "format_bo3_strength", "format_bo5_strength",
    "tournament_form_advantage", "recent_60d_adjusted_form_advantage",
    "strength_of_schedule_advantage", "performance_vs_expectation_advantage",
]
