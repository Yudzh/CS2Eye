from dataclasses import replace
from decimal import Decimal
from cs2eye.services.demo_parser_service import ParsedDemoPlayerStat, PlayerRef, DeathEvent
from cs2eye.services.demo_parse_service import reconcile_split_player_teams


def test_split_reconciliation_uses_gameplay_team_and_preserves_statistics():
    row = ParsedDemoPlayerStat(steam_id='1', nickname='Player', team_name='Wrong',
        rounds_played=23, kills=18, deaths=12, assists=3, total_damage=1800,
        adr=Decimal('78.26'), kast_rounds=17, kast_percent=Decimal('73.9'),
        internal_rating=Decimal('1.1'))
    player = PlayerRef('1', 'Player', 'Correct', 2)
    kills = [DeathEvent(1, player, None, None, 100)]
    result = reconcile_split_player_teams([row], kills)
    assert result == [replace(row, team_name='Correct')]
    assert row.team_name == 'Wrong'
    assert reconcile_split_player_teams([row], []) == [row]
