"""Exclusive account roles and durable administrator operations metadata."""
from alembic import op
import sqlalchemy as sa

revision='20260907_0012'
down_revision='20260905_0011'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('user',sa.Column('role',sa.String(16),nullable=False,server_default='user'))
    op.add_column('user',sa.Column('session_version',sa.Integer(),nullable=False,server_default='0'))
    op.create_table('admin_settings',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('values_json',sa.Text(),nullable=False))
    op.create_table('admin_user_quota',sa.Column('owner_id',sa.Integer(),sa.ForeignKey('user.id'),primary_key=True),sa.Column('values_json',sa.Text(),nullable=False))
    op.create_table('admin_job_control',sa.Column('kind',sa.String(),primary_key=True),sa.Column('job_id',sa.String(),primary_key=True),
        sa.Column('held',sa.Boolean(),nullable=False),sa.Column('priority',sa.Integer(),nullable=False),sa.Column('admin_retries',sa.Integer(),nullable=False),sa.Column('repair',sa.Boolean(),nullable=False))
    op.create_table('admin_repair_day',sa.Column('utc_date',sa.String(),primary_key=True),sa.Column('video_used',sa.Integer(),nullable=False),sa.Column('ai_used',sa.Integer(),nullable=False))
    op.create_table('admin_lease',sa.Column('kind',sa.String(),primary_key=True),sa.Column('job_id',sa.String(),primary_key=True),sa.Column('pool',sa.String(),nullable=False),
        sa.Column('pid',sa.Integer(),nullable=False),sa.Column('hostname',sa.String(),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False))
    op.create_index('ix_admin_lease_pool','admin_lease',['pool'])
    op.create_table('admin_attempt',sa.Column('id',sa.String(),primary_key=True),sa.Column('kind',sa.String(),nullable=False),sa.Column('job_id',sa.String(),nullable=False),
        sa.Column('owner_id',sa.Integer(),sa.ForeignKey('user.id'),nullable=True),sa.Column('repair',sa.Boolean(),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False))
    for name in ('job_id','owner_id','created_at'):
        op.create_index('ix_admin_attempt_'+name,'admin_attempt',[name])
    op.create_table('admin_audit',sa.Column('id',sa.String(),primary_key=True),sa.Column('actor_id',sa.Integer(),sa.ForeignKey('user.id'),nullable=False),sa.Column('action',sa.String(),nullable=False),sa.Column('reason',sa.String(500),nullable=False),
        sa.Column('target_kind',sa.String(),nullable=False),sa.Column('target_ids_json',sa.String(),nullable=False),sa.Column('changes_json',sa.Text(),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False))
    op.create_index('ix_admin_audit_created_at','admin_audit',['created_at'])
    op.create_table('admin_preset_job',sa.Column('id',sa.String(),primary_key=True),sa.Column('preset_id',sa.String(),nullable=False),sa.Column('status',sa.String(),nullable=False),
        sa.Column('attempts',sa.Integer(),nullable=False),sa.Column('expected',sa.Boolean(),nullable=False),sa.Column('payload_json',sa.Text(),nullable=False),sa.Column('usage_json',sa.String(),nullable=False),
        sa.Column('available_at',sa.DateTime(),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('updated_at',sa.DateTime(),nullable=False))


def downgrade():
    for table in ('admin_preset_job','admin_audit','admin_attempt','admin_lease','admin_repair_day','admin_job_control','admin_user_quota','admin_settings'):
        op.drop_table(table)
    with op.batch_alter_table('user') as batch:
        batch.drop_column('session_version')
        batch.drop_column('role')
