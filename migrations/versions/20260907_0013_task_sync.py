"""Persist explicit registration settings and versioned task synchronization."""
from alembic import op
import sqlalchemy as sa

revision = '20260907_0013'
down_revision = '20260907_0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('analysis', sa.Column('enrollment_mode', sa.String(length=16), nullable=False, server_default='sequential'))
    op.add_column('analysis', sa.Column('expected_persons', sa.Integer(), nullable=True))
    op.add_column('analysis', sa.Column('sync_config_json', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('analysis', 'sync_config_json')
    op.drop_column('analysis', 'expected_persons')
    op.drop_column('analysis', 'enrollment_mode')
