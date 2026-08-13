from cs2eye.services.demo_utility_service import _base, finalize


def test_utility_damage_and_per_round_formulas():
    value = _base(10)
    value.update(he_thrown=2, fire_thrown=1, flash_thrown=4, smoke_thrown=3,
                 he_damage=30, fire_damage=20)
    result = finalize(value)
    assert result["total_utility_thrown"] == 10
    assert result["utility_damage"] == 50
    assert result["utility_per_round"] == 1
    assert result["utility_damage_per_round"] == 5
    assert result["he_damage_per_he"] == 15
    assert result["fire_damage_per_grenade"] == 20


def test_missing_denominators_are_null_not_zero():
    result = finalize(_base(0))
    for key in ("utility_per_round", "utility_damage_per_round", "he_damage_per_he",
                "fire_damage_per_grenade", "enemies_flashed_per_flash", "flash_assists_per_round"):
        assert result[key] is None


def test_flash_enemy_team_and_duration_metrics():
    value = _base(5)
    value.update(flash_thrown=2, enemies_flashed=3, teammates_flashed=1,
                 enemy_flash_duration=4.5, teammate_flash_duration=1.0, flash_assists=1)
    result = finalize(value)
    assert result["enemies_flashed_per_flash"] == 1.5
    assert result["teammates_flashed_per_flash"] == .5
    assert result["enemy_flash_seconds_per_flash"] == 2.25
    assert result["flash_assists_per_round"] == .2


def test_decoy_does_not_affect_main_utility_total():
    value = _base(1)
    value.update(decoy_thrown=4, he_thrown=1)
    assert finalize(value)["total_utility_thrown"] == 1


def test_ct_t_split_uses_independent_round_denominators():
    value = _base(4)
    value["ct"].update(rounds_played=2, he_thrown=2, he_damage=20)
    value["t"].update(rounds_played=2, fire_thrown=1, fire_damage=10)
    result = finalize(value)
    assert result["ct"]["utility_per_round"] == 1
    assert result["ct"]["utility_damage_per_round"] == 10
    assert result["t"]["utility_per_round"] == .5
    assert result["t"]["utility_damage_per_round"] == 5
