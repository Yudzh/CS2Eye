CALCULATED_VETO_MODEL_VERSION = "v1"

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

