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

# matchup_v3 (see analytics.matchup_config.MATCHUP_V3_CONFIG) scores only 6 factors:
# map_veto, team_strength, form_context, tactical_matchup, h2h, leadership_context.
# scripts/train_v3_candidate_model.py's diagnostics (bootstrap sign stability, VIF,
# pairwise correlation) on the full 17-feature schema found the v1 schema carries dead
# weight and near-duplicate columns that a 6-factor model doesn't need and that were
# contributing to failed quality gates and sign instability:
#   - current_roster_advantage: AnalyticsAsOfService._matchup_v3 never emits a
#     current_roster_form factor (retired -- its signal already lives inside Team/Map
#     Strength V3's own roster-applicability weighting), so this was a constant zero
#     for every v3-trained example.
#   - format_bo1_strength / format_bo3_strength / format_bo5_strength: each is just
#     team_strength_difference gated by format (0 elsewhere), so they are the same
#     signal split three ways rather than independent information -- corr >= 0.79
#     with team_strength_difference in that diagnostics run, and format_bo1_strength's
#     own bootstrap sign was unstable (57% -- close to a coin flip).
#   - raw_matchup_centered: corr == 1.00 with matchup_score_centered in that run (the
#     pre- vs post- coverage/agreement-adjustment view of the identical score) -- one
#     version of "the matchup score" is enough; matchup_score_centered (the actual,
#     adjusted score shown everywhere else) is the one kept.
#   - leadership_advantage: always exactly 0 for every historical training row (see
#     AnalyticsAsOfService.features below), so its trained coefficient is provably
#     always 0 (see win_probability_service.explain_prediction /
#     tests/test_win_probability_feature_parity.py) -- no historical signal to learn.
# What's left (11 features) each maps to one of the 6 factors, an external signal
# (ranking_advantage), or a deliberate reliability-weighted interaction -- no column
# whose purpose can't be stated in one sentence.
#
# Forward-selection restart (2026-09-15): training the full 11 still failed the quality
# gate, and diagnostics on that run found the same kind of duplication that got the v1
# schema trimmed to begin with -- matchup_reliability_advantage is matchup_score_centered
# times a reliability factor with near-zero variance in this dataset (corr == 1.00, VIF in
# the thousands), team_strength_difference is one of the weighted inputs matchup_score_centered
# is itself built from (corr ~0.89-0.90, VIF ~22), and the three "recent form" columns
# overlap each other (pairwise corr 0.76-0.92) with unstable/flipped bootstrap signs.
# Rather than keep guessing which duplicate to drop, WIN_PROBABILITY_FEATURES_V3 now holds
# only a minimal, mutually-uncorrelated starting set and grows by moving one name at a time
# from WIN_PROBABILITY_FEATURES_V3_CANDIDATES once it's shown to earn its place (better
# validation brier/log_loss, stable bootstrap sign) -- nothing below is deleted, just parked.
WIN_PROBABILITY_FEATURE_SCHEMA_VERSION_V3 = "matchup_features_v3"
# team_strength_difference added back 2026-09-15: as a standalone single-feature model
# (v8's "team_strength" baseline) it scored brier=0.1892, better than the 3-feature v9
# candidate's own test brier of 0.2031 -- worth testing as an addition despite its known
# correlation with matchup_score_centered (corr ~0.89-0.90); not yet tested combined with
# the other 3 on the same split, only as a standalone baseline.
WIN_PROBABILITY_FEATURES_V3 = [
    "matchup_score_centered", "tactical_advantage", "ranking_advantage", "team_strength_difference",
]
WIN_PROBABILITY_FEATURES_V3_CANDIDATES = [
    "matchup_reliability_advantage", "map_pool_advantage",
    "h2h_advantage", "tournament_form_advantage", "recent_60d_adjusted_form_advantage",
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
