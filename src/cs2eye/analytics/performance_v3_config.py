"""Single source of truth for Player Strength/Profile V3 formulas."""

PLAYER_STRENGTH_MODEL_VERSION = "player_strength.v3"
PERFORMANCE_PROFILE_MODEL_VERSION = "performance_profile.v3"

PLAYER_STRENGTH_WEIGHTS = {"mechanical": 0.65, "supporting": 0.35}
MECHANICAL_WEIGHTS = {
    "kills_per_round": 0.45,
    "adr": 0.35,
    "survival_rate": 0.20,
}
SUPPORTING_WEIGHTS = {
    "flash_assists_per_round": 0.30,
    "enemies_flashed_per_flash": 0.20,
    "enemy_flash_seconds_per_flash": 0.15,
    "utility_damage_per_round": 0.15,
    "trade_success_rate": 0.15,
    "teammates_flashed_per_flash": 0.05,
}

PROFILE_WEIGHTS = {
    "firepower": MECHANICAL_WEIGHTS,
    "opening": {"opening_success": 0.70, "opening_attempts_per_round": 0.30},
    "entrying": {"t_opening_attempts_per_round": 0.55, "t_opening_success": 0.45},
    "trading": {"trade_success_rate": 0.60, "death_trade_rate": 0.40},
    "clutching": {"difficulty_weighted_clutch_rate": 1.0},
    "sniping": {"awp_kills_per_round": 0.65, "awp_kill_share": 0.35},
    "utility": {
        "flash_assists_per_round": 0.30,
        "enemies_flashed_per_flash": 0.20,
        "enemy_flash_seconds_per_flash": 0.15,
        "utility_damage_per_round": 0.30,
        "teammates_flashed_per_flash": 0.05,
    },
}

CLUTCH_DIFFICULTY_WEIGHTS = {1: 1.0, 2: 1.5, 3: 2.25, 4: 3.0, 5: 4.0}
PROFILE_SAMPLE_TARGETS = {
    "firepower": 400, "entrying": 40, "trading": 40, "opening": 40,
    "clutching": 40, "sniping": 400, "utility": 400,
}
