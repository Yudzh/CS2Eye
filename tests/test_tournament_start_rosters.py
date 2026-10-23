from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from tests.test_tournament_roster_override import roster_db
from cs2eye.models.match import Tournament, TournamentRosterCheck, TournamentRosterOverride
from cs2eye.models.team import Team, TeamRosterMember
from cs2eye.services.effective_roster_service import EffectiveRosterService
from cs2eye.services.tournament_lineup_monitor import (
    Bo3LineupSourceAdapter, LineupResult, TournamentLineupMonitor, select_roster_players,
)
from cs2eye.services.team_strength_v3_service import TeamStrengthV3Service
from cs2eye.services.map_strength_v3_service import MapStrengthV3Service


async def start_today(s):
    event = await s.get(Tournament, 1)
    event.start_date = date.today()
    event.end_date = date.today() + timedelta(days=2)
    await s.commit()


def adapter(ids):
    return SimpleNamespace(get_tournament_lineup=AsyncMock(return_value=LineupResult("available", ids)))


@pytest.mark.parametrize("ids,added,missing", [
    ([1,2,3,4,5], [], []), ([1,2,3,4,6], [6], [5]), ([1,2,3,6,7], [6,7], [4,5]),
])
async def test_capture_and_idempotence(roster_db, ids, added, missing):
    async with roster_db() as s:
        await start_today(s)
        source = adapter(ids)
        monitor = TournamentLineupMonitor(s, source)
        result = await monitor.check(1, 1)
        await s.commit()
        assert result["status"] == ("changed" if added else "unchanged")
        row = await s.scalar(select(TournamentRosterCheck))
        assert row.baseline_ids == [1,2,3,4,5]
        assert row.roster_ids == ids and row.added_ids == added and row.missing_ids == missing
        await monitor.check(1,1)
        assert source.get_tournament_lineup.await_count == 1
        assert await s.scalar(select(func.count()).select_from(TournamentRosterCheck)) == 1
        assert await s.scalar(select(func.count()).select_from(TournamentRosterOverride)) == 0
        effective = await EffectiveRosterService(s).get_effective_roster(1,1)
        assert {p['id'] for p in effective['players']} == set(ids)
        assert effective['stand_in_penalty'] == 0
        assert (await s.get(Team,1)).current_roster_id == 1
        assert set((await s.scalars(select(TeamRosterMember.player_id).where(TeamRosterMember.roster_id==1))).all()) == {1,2,3,4,5}
        future = await EffectiveRosterService(s).get_effective_roster(1,1,as_of=date.today()+timedelta(days=3))
        assert {p['id'] for p in future['players']} == {1,2,3,4,5}


@pytest.mark.parametrize('failure', ['partial', 'network', 'duplicate', 'unresolved'])
async def test_failure_and_retry(roster_db, failure):
    async with roster_db() as s:
        await start_today(s)
        source = adapter([1,2,3,4] if failure=='partial' else [1,2,3,4,4] if failure=='duplicate' else [1,2,3,4,99])
        if failure=='network': source.get_tournament_lineup.side_effect = RuntimeError('network unavailable')
        monitor = TournamentLineupMonitor(s,source)
        first = await monitor.check(1,1)
        await s.commit()
        assert first['status'] in {'partial','error'}
        row = await s.scalar(select(TournamentRosterCheck))
        assert row.roster_ids is None and row.added_ids is None and row.missing_ids is None
        source.get_tournament_lineup.side_effect = None
        source.get_tournament_lineup.return_value = LineupResult('available',[1,2,3,4,6])
        await monitor.check(1,1)
        assert source.get_tournament_lineup.await_count == 2
        assert row.baseline_ids == [1,2,3,4,5] and row.roster_ids == [1,2,3,4,6]


async def test_manual_conflict_and_shared_strength_roster(roster_db):
    async with roster_db() as s:
        await start_today(s)
        await EffectiveRosterService(s).create_manual(1,1,5,6)
        await s.commit()
        result = await TournamentLineupMonitor(s,adapter([1,2,3,4,7])).check(1,1)
        await s.commit()
        assert result['status']=='conflict'
        effective = await EffectiveRosterService(s).get_effective_roster(1,1)
        assert {p['id'] for p in effective['players']} == {1,2,3,4,6}
        assert effective['warnings'] and effective['stand_in_penalty']==-3
        team = await s.get(Team,1)
        maps = (await MapStrengthV3Service(s).calculate(1,"nuke",tournament_id=1))["roster_context"]
        strength = await TeamStrengthV3Service(s).calculate(1,tournament_id=1)
        assert maps['effective_player_ids'] == sorted(p['id'] for p in strength['effective_roster']['players'])
        assert strength['temporary_replacement_factor']['impact']==-3


async def test_bo3_roster_strength_and_new_player_statistics(roster_db):
    async with roster_db() as s:
        await start_today(s)
        await TournamentLineupMonitor(s,adapter([1,2,3,6,7])).check(1,1)
        await s.commit()
        service = TeamStrengthV3Service(s)
        service.player_service.calculate = AsyncMock(side_effect=lambda pid,*a,**kw: {
            'player_strength': pid*10, 'mechanical_strength': pid*10,
            'supporting_strength': pid*10,'reliability':80})
        strength = await service.calculate(1,tournament_id=1)
        players = strength['effective_roster_quality']['players']
        assert {p['id'] for p in players} == {1,2,3,6,7}
        assert next(p for p in players if p['id']==7)['player_strength_v3']==70
        maps = (await MapStrengthV3Service(s).calculate(1,"nuke",tournament_id=1))["roster_context"]
        assert maps['effective_player_ids'] == [1,2,3,6,7]
        assert strength['temporary_replacement_factor']['impact']==0


async def test_due_date_and_success_skipped(roster_db):
    async with roster_db() as s:
        await start_today(s)
        future = await s.get(Tournament,2)
        future.start_date=date.today()+timedelta(days=3)
        future.end_date=date.today()+timedelta(days=5)
        await s.commit()
        source=adapter([1,2,3,4,5])
        monitor=TournamentLineupMonitor(s,source)
        assert (await monitor.check(2,1))["status"] == "not_due"
        await monitor.check_due(date.today()-timedelta(days=1))
        source.get_tournament_lineup.assert_not_awaited()
        await monitor.check_due()
        await monitor.check_due()
        assert source.get_tournament_lineup.await_count==1


def test_selection_excludes_coaches_bench_inactive_unknown_and_other_team():
    def player(pid, **kw):
        return SimpleNamespace(**(dict(id=pid,is_coach=False,is_substitute=False,status=1,team_id=10)|kw))
    detail=SimpleNamespace(id=10,players=[*[player(i) for i in range(1,6)],
        player(6,is_coach=True),player(7,status=2),player(8,status=None),
        player(9,team_id=11),player(10,is_substitute=True),player(11,is_coach=None)])
    assert [p.id for p in select_roster_players(detail)] == [1,2,3,4,5]


async def test_actual_bo3_request_and_player_id_mapping(roster_db, monkeypatch):
    from cs2eye.integrations.bo3.client import Bo3Client, Bo3TeamResponse
    detail=Bo3TeamResponse(id=1,slug='vitality',raw_payload={},players=[
        dict(id=i,slug=f'p{i}',nickname=f'p{i}',is_coach=False,status=1,team_id=1) for i in [1,2,3,4,100]])
    fetch=AsyncMock(return_value=detail)
    monkeypatch.setattr(Bo3Client,'fetch_team',fetch)
    async with roster_db() as s:
        await start_today(s)
        await TournamentLineupMonitor(s).check(1,1)
        fetch.assert_awaited_once_with(1,'vitality')
        row=await s.scalar(select(TournamentRosterCheck))
        assert row.source.endswith('/api/v1/teams/vitality') and len(row.roster_ids)==5
        assert 100 not in row.roster_ids  # BO3 id is not the local player primary key.


async def test_event_roster_does_not_become_future_permanent(roster_db):
    from cs2eye.models.team import TeamRoster
    from cs2eye.services.effective_roster_service import resolve_roster
    async with roster_db() as s:
        await start_today(s)
        await TournamentLineupMonitor(s,adapter([1,2,3,6,7])).check(1,1)
        await s.commit()
        baseline=await s.get(TeamRoster,1)
        baseline.active_to=date.today()
        team=await s.get(Team,1)
        team.current_roster_id=None
        await s.commit()
        assert await resolve_roster(s,team,date.today()+timedelta(days=10),historical=True) is None


async def test_manual_created_after_capture_and_confirmed_penalty(roster_db):
    async with roster_db() as s:
        await start_today(s)
        await TournamentLineupMonitor(s,adapter([1,2,3,4,7])).check(1,1)
        await s.commit()
        # A confirmed temporary replacement already present in the BO3 five still counts once.
        s.add(TournamentRosterOverride(tournament_id=1,team_id=1,player_out_id=5,
            player_in_id=7,status='CONFIRMED',source_type='AUTO',valid_from=date.today(),
            detected_at=datetime.now(UTC)))
        await s.commit()
        effective=await EffectiveRosterService(s).get_effective_roster(1,1)
        assert effective['stand_in_penalty']==-3
        await EffectiveRosterService(s).create_manual(1,1,5,6)
        await s.commit()
        effective=await EffectiveRosterService(s).get_effective_roster(1,1)
        assert {p['id'] for p in effective['players']}=={1,2,3,4,6}
        assert effective['stand_in_penalty']==-3 and effective['warnings']


def test_migration_upgrade_and_downgrade():
    from importlib.util import module_from_spec, spec_from_file_location
    from pathlib import Path
    from sqlalchemy import create_engine, inspect
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    engine=create_engine('sqlite:///:memory:')
    from cs2eye.db.base import Base
    with engine.begin() as conn:
        Base.metadata.create_all(conn)
        TournamentRosterCheck.__table__.drop(conn)
        path=Path(__file__).resolve().parents[1]/'alembic/versions/0055_tournament_roster_checks.py'
        spec=spec_from_file_location('roster_migration',path)
        module=module_from_spec(spec)
        spec.loader.exec_module(module)
        module.op=Operations(MigrationContext.configure(conn))
        module.upgrade()
        assert 'tournament_roster_checks' in inspect(conn).get_table_names()
        module.downgrade()
        assert 'tournament_roster_checks' not in inspect(conn).get_table_names()
    engine.dispose()


async def refresh_main_roster(session, ids):
    """Use the same persistence function as the Teams page BO3 refresh."""
    from cs2eye.models.team import Player
    from cs2eye.services.team_roster_service import set_current_roster
    players = list((await session.scalars(select(Player).where(Player.id.in_(ids)))).all())
    await set_current_roster(session, 1, players, source="team_import")
    await session.commit()


async def test_teams_refresh_preserves_frozen_tournament_and_both_strengths(roster_db):
    async with roster_db() as s:
        await start_today(s)
        source = adapter([1,2,3,4,6])
        monitor = TournamentLineupMonitor(s, source)
        await monitor.check(1,1)
        await s.commit()
        await refresh_main_roster(s, [1,2,3,4,7])

        main = await EffectiveRosterService(s).get_effective_roster(1,None)
        assert {p['id'] for p in main['players']} == {1,2,3,4,7}
        row = await s.scalar(select(TournamentRosterCheck))
        assert row.baseline_ids == [1,2,3,4,5]
        assert row.roster_ids == [1,2,3,4,6]
        assert row.added_ids == [6] and row.missing_ids == [5]

        strength = await TeamStrengthV3Service(s).calculate(1,tournament_id=1)
        maps = await MapStrengthV3Service(s).calculate(1,'nuke',tournament_id=1)
        assert {p['id'] for p in strength['effective_roster']['players']} == {1,2,3,4,6}
        assert maps['roster_context']['effective_player_ids'] == [1,2,3,4,6]
        await monitor.check(1,1)
        assert source.get_tournament_lineup.await_count == 1


async def test_teams_refresh_before_first_check_becomes_comparison_baseline(roster_db):
    async with roster_db() as s:
        await start_today(s)
        await refresh_main_roster(s, [1,2,3,4,6])
        result = await TournamentLineupMonitor(s,adapter([1,2,3,4,6])).check(1,1)
        await s.commit()
        row = await s.scalar(select(TournamentRosterCheck))
        assert result['status'] == 'unchanged'
        assert row.baseline_ids == [1,2,3,4,6]
        assert row.roster_ids == [1,2,3,4,6]
        assert row.added_ids == [] and row.missing_ids == []


async def test_teams_refresh_between_failure_and_retry_preserves_original_baseline(roster_db):
    async with roster_db() as s:
        await start_today(s)
        source = adapter([1,2,3,4])
        monitor = TournamentLineupMonitor(s,source)
        assert (await monitor.check(1,1))['status'] == 'partial'
        await s.commit()
        await refresh_main_roster(s,[1,2,3,4,6])
        source.get_tournament_lineup.return_value = LineupResult('available',[1,2,3,4,6])
        assert (await monitor.check(1,1))['status'] == 'changed'
        row = await s.scalar(select(TournamentRosterCheck))
        assert row.baseline_ids == [1,2,3,4,5]
        assert row.added_ids == [6] and row.missing_ids == [5]
