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

# Explicit semantics: diagnostics must never infer direction or symmetry from a name.
WIN_PROBABILITY_FEATURE_REGISTRY = {
    "matchup_score_centered": {"group": "matchup", "expected_direction": "positive", "expected_symmetry": "antisymmetric"},
    "raw_matchup_centered": {"group": "matchup", "expected_direction": "positive", "expected_symmetry": "antisymmetric"},
    "matchup_reliability_advantage": {"group": "matchup", "expected_direction": "positive", "expected_symmetry": "antisymmetric"},
    "team_strength_difference": {"group": "team_strength", "expected_direction": "positive", "expected_symmetry": "antisymmetric"},
    "map_pool_advantage": {"group": "matchup", "expected_direction": "positive", "expected_symmetry": "antisymmetric"},
    "current_roster_advantage": {"group": "form", "expected_direction": "positive", "expected_symmetry": "antisymmetric"},
    "tactical_advantage": {"group": "matchup", "expected_direction": "positive", "expected_symmetry": "antisymmetric"},
    "h2h_advantage": {"group": "h2h", "expected_direction": "positive", "expected_symmetry": "antisymmetric"},
    "leadership_advantage": {"group": "matchup", "expected_direction": "positive", "expected_symmetry": "antisymmetric"},
    "ranking_advantage": {"group": "ranking", "expected_direction": "positive", "expected_symmetry": "antisymmetric"},
    "format_bo1_strength": {"group": "format", "expected_direction": "positive", "expected_symmetry": "antisymmetric"},
    "format_bo3_strength": {"group": "format", "expected_direction": "positive", "expected_symmetry": "antisymmetric"},
    "format_bo5_strength": {"group": "format", "expected_direction": "positive", "expected_symmetry": "antisymmetric"},
    "tournament_form_advantage": {"group": "form", "expected_direction": "positive", "expected_symmetry": "antisymmetric"},
    "recent_60d_adjusted_form_advantage": {"group": "form", "expected_direction": "positive", "expected_symmetry": "antisymmetric"},
    "strength_of_schedule_advantage": {"group": "form", "expected_direction": "positive", "expected_symmetry": "antisymmetric"},
    "performance_vs_expectation_advantage": {"group": "form", "expected_direction": "positive", "expected_symmetry": "antisymmetric"},
}

FEATURE_DIAGNOSTICS_BOOTSTRAP_RUNS = 100
FEATURE_DIAGNOSTICS_SEED = 42
FEATURE_DIAGNOSTICS_MIN_SAMPLES = 50
FEATURE_DIAGNOSTICS_HIGH_CORRELATION = .70
FEATURE_DIAGNOSTICS_VERY_HIGH_CORRELATION = .85
FEATURE_DIAGNOSTICS_STABLE_SIGN_RATE = .90
FEATURE_DIAGNOSTICS_MODERATE_SIGN_RATE = .70
FEATURE_DIAGNOSTICS_NEAR_CONSTANT_STD = 1e-8
