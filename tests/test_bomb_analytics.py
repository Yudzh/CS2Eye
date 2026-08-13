from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from cs2eye.models.demo import DemoTeamBombStat
from cs2eye.services.team_map_aggregate_service import SourceMap, _aggregate_model


def source(*, plants=0, postplant_wins=0, retake_opportunities=0, retake_wins=0,
           explosions=0, defuses=0, t_rounds=12, demo_id=1):
    side = SimpleNamespace(
        total_rounds_played=24, total_rounds_won=13,
        ct_rounds_played=12, ct_rounds_won=7,
        t_rounds_played=12, t_rounds_won=6,
        overtime_rounds_played=0, overtime_rounds_won=0,
    )
    bomb = DemoTeamBombStat(
        demo_file_id=demo_id, demo_map_result_id=demo_id, team_id=1, team_name="Spirit",
        t_rounds_played=t_rounds, bomb_plants=plants,
        postplant_rounds=plants, postplant_wins=postplant_wins,
        postplant_losses=plants-postplant_wins,
        retake_opportunities=retake_opportunities, retake_wins=retake_wins,
        retake_losses=retake_opportunities-retake_wins,
        bomb_explosions=explosions, bomb_defuses=defuses,
    )
    return SourceMap(demo_id, date(2026, 8, demo_id), True, False, side, bomb, None)


def test_bomb_aggregate_formulas_include_elimination_postplant_and_retake():
    result = _aggregate_model(
        1, "nuke", "all", "all",
        [source(plants=4, postplant_wins=3, retake_opportunities=5, retake_wins=2,
                explosions=2, defuses=2)], date(2026, 8, 9),
    )
    assert result.plant_rate == Decimal(100) / 3
    assert result.postplant_win_rate == Decimal(75)
    assert result.retake_win_rate == Decimal(40)
    assert (result.postplant_wins, result.postplant_losses) == (3, 1)
    assert (result.retake_wins, result.retake_losses) == (2, 3)
    assert (result.bomb_explosions, result.bomb_defuses) == (2, 2)


def test_not_parsed_map_does_not_become_zero_bomb_rate():
    item = source()
    item = SourceMap(item.demo_file_id, item.match_date, item.won,
                     item.went_to_overtime, item.side, None, item.opponent_context)
    result = _aggregate_model(1, "nuke", "all", "all", [item], date(2026, 8, 9))
    assert result.bomb_plants == 0
    assert result.plant_rate is None
    assert result.postplant_win_rate is None
    assert result.retake_win_rate is None


def test_recent_or_rank_scope_uses_only_its_selected_bomb_maps():
    result = _aggregate_model(
        1, "nuke", "recent", "recent:5",
        [source(plants=6, postplant_wins=3, demo_id=1),
         source(plants=3, postplant_wins=3, demo_id=2)],
        date(2026, 8, 9), window_size=5,
    )
    assert result.maps_played == 2
    assert result.bomb_plants == 9
    assert result.postplant_win_rate == Decimal(200) / 3
