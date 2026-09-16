WIN_PROBABILITY_MODEL_VERSION = "v1"
MIN_HISTORICAL_MAPS_PER_TEAM = 3
MIN_PREDICTION_CONFIDENCE = .25

# Five columns from the original 17-feature (matchup_v1-era) schema are gone outright, not
# just excluded from the v3 pool -- keeping them in the list/registry while unreachable from
# both WIN_PROBABILITY_FEATURES_V3 and WIN_PROBABILITY_FEATURES_V3_CANDIDATES left no way to
# tell "forgotten junk" from "parked for later" (2026-09-15 cleanup):
#   - current_roster_advantage: AnalyticsAsOfService._matchup_v3 never emits a
#     current_roster_form factor at all (retired along with matchup_v1/matchup_v2_candidate
#     -- its signal already lives inside Team/Map Strength V3's own roster-applicability
#     weighting), so this is a constant zero for every v3-trained example, permanently.
#   - format_bo1_strength / format_bo3_strength / format_bo5_strength: each is just
#     team_strength_difference gated by format (0 elsewhere), so they are the same
#     signal split three ways rather than independent information -- corr >= 0.79
#     with team_strength_difference in the diagnostics run that first flagged this, and
#     format_bo1_strength's own bootstrap sign was unstable (57% -- close to a coin flip).
#   - leadership_advantage: always exactly 0 for every historical training row (see
#     AnalyticsAsOfService.features below), so its trained coefficient is provably
#     always 0 -- no historical signal to learn, ever.
# raw_matchup_centered was cut in the same original pass (corr == 1.00 with
# matchup_score_centered -- the pre- vs post- coverage/agreement-adjustment view of the
# identical score) but, unlike the four above, isn't structurally dead -- kept below and
# parked in WIN_PROBABILITY_FEATURES_V3_CANDIDATES in case a future v3 dataset shows it
# diverging from matchup_score_centered enough to be worth a second look.
WIN_PROBABILITY_FEATURES = [
    "matchup_score_centered", "raw_matchup_centered", "matchup_reliability_advantage",
    "team_strength_difference", "map_pool_advantage",
    "tactical_advantage", "h2h_advantage",
    "ranking_advantage",
    "tournament_form_advantage", "recent_60d_adjusted_form_advantage",
    "strength_of_schedule_advantage", "performance_vs_expectation_advantage",
]

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
    "raw_matchup_centered",
]

# WinProbabilityModel.train previously re-fit every column's standardization scale from
# its own empirical std on each retrain. That is fine for a feature whose spread is stable,
# but broke once _feature_vector/AnalyticsAsOfService.features started multiplying
# tactical_advantage and team_strength_difference by the matchup factor's own reliability
# (2026-09-16 fix for tactical getting muted by matchup but not by ML): most historical
# matches have chronically low tactical-matchup confidence, so nearly every training row
# gets pulled toward 0 and the column's empirical std collapsed 23x (v10 -> v11: 0.0934 ->
# 0.0040). Standardizing against that collapsed std then reads any moderately-confident
# live match as a 5+ sigma outlier, re-amplifying exactly the signal the reliability
# weighting was meant to suppress (see explain_prediction's per-factor impact on
# Spirit-vs-MOUZ, 2026-09-16: tactical_advantage's tiny raw value swung the prediction by
# nearly as much as team_strength_difference).
#
# Freezing each V3 feature's scale below removes that feedback loop -- "one unit of
# signal" no longer depends on how often a factor happened to be reliable in whichever
# training window produced the latest retrain. Values are each feature's own empirical std
# from v10 (2026-09-15, trained the day before the reliability-weighting fix shipped, same
# 4-feature set as v11) -- the natural historical spread of the *unweighted* signal, before
# it could be muted by low confidence:
#   - tactical_advantage / team_strength_difference: this is the specific fix -- v10's
#     pre-collapse std restores the original "unit of signal" for both (team_strength's
#     confidence is usually high, so its v10->v11 collapse was much milder, 0.0973 ->
#     0.0671, but freezing it removes the same drift risk for future retrains).
#   - matchup_score_centered: not touched by the reliability-weighting fix (matchup_score
#     is already dampened by matchup_engine's own coverage/agreement multiplier, a separate
#     mechanism) but shows the same narrow-spread-inflates-standardization risk; frozen at
#     its v10/v11 empirical value, which was already stable across both.
#   - ranking_advantage: stable, well-behaved spread; frozen anyway so every V3 feature
#     uses a fixed scale rather than a fragile mix of fixed and still-adaptive columns.
WIN_PROBABILITY_FEATURE_FIXED_SCALES = {
    "tactical_advantage": 0.0934, "team_strength_difference": 0.0973,
    "matchup_score_centered": 0.0183, "ranking_advantage": 0.2264,
}

# Explicit semantics: diagnostics must never infer direction or symmetry from a name.
WIN_PROBABILITY_FEATURE_REGISTRY = {
    "matchup_score_centered": {"group": "matchup", "expected_direction": "positive", "expected_symmetry": "antisymmetric"},
    "raw_matchup_centered": {"group": "matchup", "expected_direction": "positive", "expected_symmetry": "antisymmetric"},
    "matchup_reliability_advantage": {"group": "matchup", "expected_direction": "positive", "expected_symmetry": "antisymmetric"},
    "team_strength_difference": {"group": "team_strength", "expected_direction": "positive", "expected_symmetry": "antisymmetric"},
    "map_pool_advantage": {"group": "matchup", "expected_direction": "positive", "expected_symmetry": "antisymmetric"},
    "tactical_advantage": {"group": "matchup", "expected_direction": "positive", "expected_symmetry": "antisymmetric"},
    "h2h_advantage": {"group": "h2h", "expected_direction": "positive", "expected_symmetry": "antisymmetric"},
    "ranking_advantage": {"group": "ranking", "expected_direction": "positive", "expected_symmetry": "antisymmetric"},
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
