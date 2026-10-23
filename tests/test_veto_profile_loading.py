from datetime import date

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cs2eye.db.base import Base
from cs2eye.models.demo import DemoMapResult, DemoTeamRoster
from cs2eye.models.demo_file import DemoFile
from cs2eye.models.match import Match, MatchVetoAction
from cs2eye.models.team import Team, TeamRoster
from cs2eye.services.veto_service import VetoService


@pytest.mark.parametrize('series_count', [1, 12])
async def test_veto_profile_batches_history_and_preserves_pick_results(series_count):
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            team = Team(id=1, bo3_id=1, bo3_slug='one', name='One')
            session.add_all([team, Team(id=2, bo3_id=2, bo3_slug='two', name='Two')])
            session.add(TeamRoster(id=1, team_id=1, fingerprint='current',
                source='manual', resolution_status='complete', is_current=True))
            await session.flush()
            team.current_roster_id = 1
            for index in range(series_count):
                match = Match(team_a_id=1, team_b_id=2, match_date=date(2026, 10, 1),
                    format='bo3', status='completed', veto_data_status='complete')
                session.add(match)
                await session.flush()
                for order, (name, kind, actor, won) in enumerate([
                    ('nuke', 'pick', 1, True), ('mirage', 'pick', 2, False),
                    ('inferno', 'decider', None, True),
                ], 1):
                    session.add(MatchVetoAction(match_series_id=match.id, order_index=order,
                        map_name=name, action=kind, team_id=actor))
                    demo = DemoFile(match_id=match.id, tournament_name='Test', tournament_slug='test',
                        match_date=match.match_date, original_filename=f'{index}-{name}.dem',
                        storage_path='/unused', file_size_bytes=1, sha256='0' * 64)
                    session.add(demo)
                    await session.flush()
                    # Reverse team orientation to catch incorrect result attribution.
                    result = DemoMapResult(demo_file_id=demo.id, map_name=name,
                        team_a_id=2, team_b_id=1, team_a_score=5 if won else 13,
                        team_b_score=13 if won else 5, result_source='manual_override',
                        metadata_status='complete')
                    session.add(result)
                    await session.flush()
                    session.add(DemoTeamRoster(demo_file_id=demo.id, demo_map_result_id=result.id,
                        team_id=1, roster_id=1, team_name_snapshot='One', resolution_status='complete'))
            await session.commit()
            queries = []

            def record(conn, cursor, statement, parameters, context, executemany):
                queries.append(statement)

            event.listen(engine.sync_engine, 'before_cursor_execute', record)
            try:
                profile = await VetoService(session).profile(1, aggregation_level='current_roster')
            finally:
                event.remove(engine.sync_engine, 'before_cursor_execute', record)
            # SQL count must stay constant as the number of series/maps grows.
            assert len(queries) <= 7
            assert profile['sample'] == {'series': series_count, 'complete_series': series_count}
            maps = {row['map_name']: row for row in profile['maps']}
            assert maps['nuke']['pick']['wins'] == series_count
            assert maps['nuke']['pick']['win_rate'] == 100
            assert maps['mirage']['opponent_pick']['losses'] == series_count
            assert maps['mirage']['opponent_pick']['win_rate'] == 0
            assert maps['inferno']['decider']['wins'] == series_count
            assert maps['ancient']['pick']['win_rate'] is None

            # One unresolved or missing map lineup excludes the entire series.
            roster = await session.get(DemoTeamRoster, 1)
            roster.resolution_status = 'partial'
            await session.flush()
            filtered = await VetoService(session).profile(1, aggregation_level='current_roster')
            assert filtered['sample']['series'] == series_count - 1
            await session.delete(roster)
            await session.flush()
            filtered = await VetoService(session).profile(1, aggregation_level='current_roster')
            assert filtered['sample']['series'] == series_count - 1
    finally:
        await engine.dispose()
