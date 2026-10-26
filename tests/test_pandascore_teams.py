"""Team profiles preserve local identities, rankings and roster attribution."""
import httpx
import pytest
from sqlalchemy import select

from cs2eye.integrations.pandascore.client import PandaScoreClient, PandaScoreError
from cs2eye.models.team import Team
from cs2eye.services.pandascore_team_service import PandaScoreTeamService
from tests.test_pandascore_results import db


def service(session, rows, status=200):
    def respond(request):
        assert request.url.path == '/csgo/teams'
        assert request.url.params['sort'] == 'name'
        return httpx.Response(status, json=rows)
    def factory(quota, reserve):
        return PandaScoreClient(quota, reserve, transport=httpx.MockTransport(respond))
    return PandaScoreTeamService(session, factory)


ROW = {'id':131505, 'name':'Aurora Gaming', 'slug':'aurora-gaming', 'location':'RU',
       'image_url':'https://cdn.example.org/aurora.png'}


async def test_profile_update_preserves_local_identity_and_ranking(db):
    team = await db.get(Team, 1)
    team.current_rank = 5
    original = (team.id, team.bo3_id, team.bo3_slug, team.current_roster_id, team.roster_synced_at)
    await db.commit()
    svc = service(db, [ROW])
    found = await svc.search('Aurora')
    assert found[0].id == ROW['id']
    await svc.update(team.id, ROW['id'])
    await db.commit()
    await svc.update(team.id, ROW['id'])
    assert (team.id, team.bo3_id, team.bo3_slug, team.current_roster_id, team.roster_synced_at) == original
    assert team.current_rank == 5
    assert team.name == 'Aurora Gaming'
    assert team.country_code == 'RU'
    assert team.pandascore_data['slug'] == 'aurora-gaming'
    assert team.pandascore_synced_at
    assert len((await db.scalars(select(Team))).all()) == 2


async def test_duplicate_provider_identity_rejected(db):
    svc = service(db, [ROW])
    await svc.update(1, ROW['id'])
    await db.commit()
    with pytest.raises(ValueError, match='другой команде'):
        await svc.update(2, ROW['id'])
    assert (await db.get(Team, 2)).name == 'NAVI'


async def test_wrong_provider_id_and_rebinding_rejected(db):
    svc = service(db, [ROW])
    with pytest.raises(ValueError, match='не найдена'):
        await svc.update(1, 999)
    team = await db.get(Team, 1)
    team.pandascore_id = 999
    await db.commit()
    with pytest.raises(ValueError, match='другому PandaScore'):
        await svc.update(1, ROW['id'])


async def test_missing_optional_values_keep_existing_profile(db):
    team = await db.get(Team, 1)
    team.logo_url = 'https://cdn.example.org/original.png'
    team.country_code = 'FR'
    team.country_name = 'France'
    await db.commit()
    await service(db, [{**ROW, 'location':None, 'image_url':None}]).update(1, ROW['id'])
    assert team.logo_url.endswith('original.png')
    assert team.country_name == 'France'


async def test_provider_failure_and_invalid_data_do_not_change_profile(db):
    for svc in [service(db, [], 403), service(db, [{**ROW, 'image_url':'javascript:alert(1)'}])]:
        with pytest.raises(PandaScoreError):
            await svc.update(1, ROW['id'])
        assert (await db.get(Team, 1)).name == 'G2'


def test_schema_migration_on_existing_teams():
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, text, inspect
    path = Path(__file__).parents[1] / 'alembic/versions/0064_pandascore_teams.py'
    spec = importlib.util.spec_from_file_location('pandascore_teams_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with create_engine('sqlite://').begin() as conn:
        conn.execute(text('CREATE TABLE teams (id INTEGER PRIMARY KEY, name TEXT)'))
        conn.execute(text("INSERT INTO teams VALUES (1, 'Aurora')"))
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
            assert conn.execute(text('SELECT name, pandascore_id FROM teams')).one() == ('Aurora', None)
            assert any(index['unique'] for index in inspect(conn).get_indexes('teams'))
            migration.downgrade()
            assert conn.execute(text('SELECT name FROM teams')).scalar_one() == 'Aurora'


async def test_admin_endpoint_returns_saved_profile(db, monkeypatch):
    from cs2eye.api.routers.teams import update_pandascore_team, PandaScoreTeamUpdate
    async def fetch(self, **params):
        from cs2eye.services.pandascore_team_service import PandaScoreTeam
        return [PandaScoreTeam.model_validate(ROW)]
    monkeypatch.setattr(PandaScoreTeamService, 'fetch', fetch)
    response = await update_pandascore_team(1, PandaScoreTeamUpdate(external_id=ROW['id']), db)
    assert response.pandascore_id == ROW['id']
    assert response.name == ROW['name']
    assert response.bo3_id == 777
