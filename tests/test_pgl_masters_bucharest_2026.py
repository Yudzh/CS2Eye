"""Check Swiss capacities and progression independently of database IDs."""
import importlib.util
from collections import Counter
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'pgl_seed', Path(__file__).parents[1] / 'scripts/add_pgl_masters_bucharest_2026.py')
pgl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pgl)


def test_swiss_has_33_matches_without_fixed_advancement():
    teams = {name: i for i, name in enumerate(pgl.PARTICIPANTS, 1)}
    rows = pgl.build_matches(42, teams)
    swiss = [m for m in rows.values() if m.stage == 'swiss']
    assert Counter(m.round_number for m in swiss) == {1: 8, 2: 8, 3: 8, 4: 6, 5: 3}
    opening = [m for m in swiss if m.round_number == 1]
    assert {t for m in opening for t in (m.team_a_id, m.team_b_id)} == set(teams.values())
    assert Counter(m.starts_at.hour for m in opening) == {7: 2, 10: 2, 13: 2, 16: 2}
    assert all(m.team_a_id is None and m.team_b_id is None for m in swiss if m.round_number > 1)
    assert all(m.next_match_id is None and m.loser_next_match_id is None for m in swiss)
    assert sum(m.is_elimination for m in swiss) == 8


def test_playoff_links_and_formats():
    rows = pgl.build_matches(42, {name: i for i, name in enumerate(pgl.PARTICIPANTS, 1)})
    for i, row in enumerate(rows.values(), 1):
        row.id = i
    pgl.link_bracket(rows)
    assert len(rows) == 41
    assert rows['final'].format == 'bo5'
    assert rows['third'].format == 'bo3'
    assert rows['final'].match_date.day == rows['third'].match_date.day == 31
    assert rows['s1'].next_match_id == rows['s2'].next_match_id == rows['final'].id
    assert rows['s1'].loser_next_match_id == rows['s2'].loser_next_match_id == rows['third'].id
    targets = [(m.next_match_id, m.next_match_slot) for m in rows.values() if m.next_match_id]
    assert len(targets) == len(set(targets)) == 6
    assert all(m.starts_at is None or m.starts_at.date() == m.match_date for m in rows.values())
