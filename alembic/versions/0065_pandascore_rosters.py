"""Separate PandaScore roster snapshots and player identities."""
from alembic import op
import sqlalchemy as sa

revision = '0065_pandascore_rosters'
down_revision = '0064_pandascore_teams'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('teams', sa.Column('pandascore_roster_data', sa.JSON(), nullable=True))
    op.add_column('teams', sa.Column('pandascore_roster_synced_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('players', sa.Column('pandascore_id', sa.Integer(), nullable=True))
    op.add_column('players', sa.Column('pandascore_slug', sa.String(160), nullable=True))
    op.create_index('uq_players_pandascore_id', 'players', ['pandascore_id'], unique=True)
    with op.batch_alter_table('players') as batch:
        batch.alter_column('bo3_id', existing_type=sa.Integer(), nullable=True)
        batch.alter_column('bo3_slug', existing_type=sa.String(160), nullable=True)
    with op.batch_alter_table('team_rosters') as batch:
        batch.drop_constraint('ck_team_rosters_source', type_='check')
        batch.create_check_constraint('ck_team_rosters_source', "source IN ('team_import', 'manual', 'demo', 'migration', 'tournament', 'pandascore')")
    op.add_column('tournaments', sa.Column('pandascore_id', sa.Integer(), nullable=True))
    op.add_column('tournaments', sa.Column('pandascore_data', sa.JSON(), nullable=True))
    op.create_index('uq_tournaments_pandascore_id', 'tournaments', ['pandascore_id'], unique=True)


def downgrade():
    # Inventing BO3 identities for PandaScore-only players would corrupt history.
    connection = op.get_bind()
    if connection.execute(sa.text('SELECT count(*) FROM players WHERE bo3_id IS NULL OR bo3_slug IS NULL')).scalar():
        raise RuntimeError('Cannot downgrade: PandaScore-only players require nullable BO3 identities.')
    op.drop_index('uq_tournaments_pandascore_id', table_name='tournaments')
    op.drop_column('tournaments', 'pandascore_data')
    op.drop_column('tournaments', 'pandascore_id')
    op.execute("UPDATE team_rosters SET source = 'team_import' WHERE source = 'pandascore'")
    with op.batch_alter_table('team_rosters') as batch:
        batch.drop_constraint('ck_team_rosters_source', type_='check')
        batch.create_check_constraint('ck_team_rosters_source', "source IN ('team_import', 'manual', 'demo', 'migration', 'tournament')")
    with op.batch_alter_table('players') as batch:
        batch.alter_column('bo3_slug', existing_type=sa.String(160), nullable=False)
        batch.alter_column('bo3_id', existing_type=sa.Integer(), nullable=False)
    op.drop_index('uq_players_pandascore_id', table_name='players')
    op.drop_column('players', 'pandascore_slug')
    op.drop_column('players', 'pandascore_id')
    op.drop_column('teams', 'pandascore_roster_synced_at')
    op.drop_column('teams', 'pandascore_roster_data')
