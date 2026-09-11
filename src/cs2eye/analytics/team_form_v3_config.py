MODEL_VERSION = "team_form.v3"
CALCULATION_REVISION = "team_form.v3.4"
PLAYER_MODEL_VERSION = "player_form.v3"
# Independent Player Form draft compatibility. Team Form V3 never consumes
# these constants or the Player Form result.
DELTA_LIMIT = 25.0
PLAYER_WEIGHTS = {"kills_per_round": 0.25, "adr": 0.20,
                  "survival_rate": 0.15, "opening": 0.15,
                  "trading": 0.15, "utility": 0.10}
WINDOW_DAYS = 60
FORM_DELTA_LIMIT = 20.0
FORM_SCORE_POINTS_PER_DELTA = 2.5
ACTUAL_PERFORMANCE_WEIGHTS = {"result": 0.70, "rounds": 0.30}
EXPECTATION_LOGISTIC_SCALE = 12.0
EVENT_CONTRIBUTION_SCALE = 30.0
# Ranking is only a fallback for historical Team Strength.  Keep its 0..100
# proxy deliberately compressed: rank gaps must not imply near-certainty.
RANK_STRENGTH_BASE = 75.0
RANK_STRENGTH_POINTS_PER_PLACE = 0.8
RANK_STRENGTH_FLOOR = 27.0
# Expected round share moves less than win probability. Even a heavy favourite
# is not expected to win every round of a series.
EXPECTED_ROUND_PERFORMANCE_RANGE = 0.25

# Deliberately moderate piecewise-linear decay: two weeks are not near-zero.
FRESHNESS_WEIGHT_POINTS = ((0, 1.00), (14, 1.00), (30, 0.75), (60, 0.45))
BO_FORMAT_WEIGHTS = {"bo1": 0.75, "bo3": 1.00, "bo5": 1.15, "unknown": 0.90}

TOURNAMENT_MAX_WEIGHTS = {0: 0.00, 1: 0.25, 2: 0.45, 3: 0.55}
TOURNAMENT_ABSOLUTE_MAX_WEIGHT = 0.60

RELIABILITY_TARGETS = {"series": 8, "maps": 16, "rounds": 350,
                       "tournament_series": 3, "recent_series": 6}
RELIABILITY_WEIGHTS = {"series": 0.25, "maps": 0.15, "rounds": 0.15,
                       "roster_applicability": 0.15,
                       "expectation_coverage": 0.15, "data_coverage": 0.15}
