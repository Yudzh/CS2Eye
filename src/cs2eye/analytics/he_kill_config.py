"""Configuration for the deterministic HE-kill-by-map estimate."""

HE_KILL_MODEL_VERSION = "he-kill-by-map.v1"
HE_KILL_CONFIDENCE_MODEL_VERSION = "he-kill-confidence.v2"
HE_KILL_WINDOW_DAYS = 60

# Beta prior for the all-map, all-team probability of scoring an HE kill.
GLOBAL_BASELINE_RATE = 0.20
GLOBAL_BASELINE_PRIOR_MAPS = 10.0

# Hierarchical shrinkage: global -> map -> team-map.
MAP_BASELINE_PRIOR_MAPS = 12.0
TEAM_MAP_PRIOR_MAPS = 6.0

# Data-sufficiency tiers for this specific team-map pair. A missing side stays
# low; high requires meaningful two-sided history without demanding 10/10 maps.
CONFIDENCE_MIN_COMBINED_MAPS = 3
CONFIDENCE_HIGH_MIN_MAPS_PER_TEAM = 3
CONFIDENCE_HIGH_MIN_COMBINED_MAPS = 8
