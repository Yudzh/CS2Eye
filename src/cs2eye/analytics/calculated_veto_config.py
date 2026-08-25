CALCULATED_VETO_MODEL_VERSION = "v2.1"

MATCHUP_WEIGHTS = {
    "own_map_quality": .35, "relative_advantage": .25,
    "recent_roster_form": .15, "side_matchup": .10,
    "bomb_matchup": .05, "economy_combat_matchup": .05,
    "utility_teamplay_matchup": .05,
}
PICK_WEIGHTS = {
    "matchup_map_score": .45, "relative_advantage": .25,
    "historical_pick_preference": .20, "recent_veto_preference": .10,
}
BAN_WEIGHTS = {
    "own_weakness": .40, "opponent_map_threat": .35,
    "relative_disadvantage": .15, "historical_ban_preference": .10,
}
H2H_MAX_WEIGHT = .08
ROSTER_PRIOR_MAPS = 5.0
VETO_PRIOR_SERIES = 8.0

# V2 series-map probability.  V1 tactical/action scores intentionally remain
# configured above because they are still useful in the diagnostic breakdown.
VETO_ROSTER_PRIOR_SERIES = 8.0
VETO_RECENT_PRIOR_SERIES = 5.0
VETO_V2_WEIGHTS = {
    "historical_selection": .45,
    "ban_survival": .25,
    "pick_pressure": .20,
    "map_matchup_quality": .10,
}
VETO_CONFIDENCE_PRIOR_SERIES = 12.0
VETO_ACTOR_PRIOR_SERIES = 5.0
