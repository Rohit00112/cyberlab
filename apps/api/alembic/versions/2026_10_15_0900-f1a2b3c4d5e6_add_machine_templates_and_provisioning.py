"""add machine templates, provisioning, vpn, and scoring tables

Revision ID: f1a2b3c4d5e6
Revises: e1f2a3b4c5d6
Create Date: 2026-10-15 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. machine_templates
    op.create_table(
        'machine_templates',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('slug', sa.String(length=120), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), server_default='', nullable=False),
        sa.Column('category', sa.String(length=64), server_default='general', nullable=False),
        sa.Column('difficulty', sa.String(length=16), server_default='intermediate', nullable=False),
        sa.Column('os_type', sa.String(length=32), server_default='linux', nullable=False),
        sa.Column('architecture', sa.String(length=16), server_default='x86_64', nullable=False),
        sa.Column('base_image', sa.String(length=512), nullable=False),
        sa.Column('services', sa.JSON(), nullable=True),
        sa.Column('challenge_modules', sa.JSON(), nullable=True),
        sa.Column('resource_spec', sa.JSON(), nullable=True),
        sa.Column('network_policy', sa.JSON(), nullable=True),
        sa.Column('exposure_policy', sa.String(length=16), server_default='vpn_only', nullable=False),
        sa.Column('flag_definitions', sa.JSON(), nullable=True),
        sa.Column('hint_config', sa.JSON(), nullable=True),
        sa.Column('max_lease_minutes', sa.Integer(), server_default='120', nullable=False),
        sa.Column('estimated_minutes', sa.Integer(), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('prerequisites', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=16), server_default='draft', nullable=False),
        sa.Column('author_id', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_machine_templates_slug', 'machine_templates', ['slug'], unique=True)

    # 2. machine_template_versions
    op.create_table(
        'machine_template_versions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('template_id', sa.Uuid(), nullable=False),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('config_snapshot', sa.JSON(), nullable=False),
        sa.Column('image_ref', sa.String(length=512), nullable=True),
        sa.Column('image_hash', sa.String(length=128), nullable=True),
        sa.Column('build_log', sa.Text(), nullable=True),
        sa.Column('artifact_manifest', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=16), server_default='building', nullable=False),
        sa.Column('validation_result', sa.JSON(), nullable=True),
        sa.Column('validated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['template_id'], ['machine_templates.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_machine_template_versions_template_id', 'machine_template_versions', ['template_id'])

    # 3. Add template_version_id to challenges
    op.add_column(
        'challenges',
        sa.Column('template_version_id', sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        'fk_challenges_template_version_id',
        'challenges',
        'machine_template_versions',
        ['template_version_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index('ix_challenges_template_version_id', 'challenges', ['template_version_id'])

    # 4. compute_nodes
    op.create_table(
        'compute_nodes',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('hostname', sa.String(length=255), nullable=False),
        sa.Column('provider_type', sa.String(length=32), server_default='docker', nullable=False),
        sa.Column('api_endpoint', sa.String(length=512), nullable=True),
        sa.Column('total_cpu_cores', sa.Float(), server_default='4.0', nullable=False),
        sa.Column('total_memory_mb', sa.Integer(), server_default='8192', nullable=False),
        sa.Column('total_disk_gb', sa.Integer(), server_default='100', nullable=False),
        sa.Column('allocated_cpu_cores', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('allocated_memory_mb', sa.Integer(), server_default='0', nullable=False),
        sa.Column('allocated_disk_gb', sa.Integer(), server_default='0', nullable=False),
        sa.Column('max_instances', sa.Integer(), server_default='20', nullable=False),
        sa.Column('active_instances', sa.Integer(), server_default='0', nullable=False),
        sa.Column('status', sa.String(length=32), server_default='online', nullable=False),
        sa.Column('is_cordoned', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('is_drained', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('last_heartbeat_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_compute_nodes_name', 'compute_nodes', ['name'], unique=True)
    op.create_index('ix_compute_nodes_status', 'compute_nodes', ['status'])

    # 5. provisioning_jobs
    op.create_table(
        'provisioning_jobs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('lab_instance_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('challenge_id', sa.Uuid(), nullable=False),
        sa.Column('idempotency_key', sa.String(length=128), nullable=True),
        sa.Column('status', sa.String(length=16), server_default='pending', nullable=False),
        sa.Column('worker_id', sa.String(length=128), nullable=True),
        sa.Column('celery_task_id', sa.String(length=128), nullable=True),
        sa.Column('compute_node_id', sa.Uuid(), nullable=True),
        sa.Column('attempt', sa.Integer(), server_default='1', nullable=False),
        sa.Column('max_attempts', sa.Integer(), server_default='3', nullable=False),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('error_details', sa.JSON(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['lab_instance_id'], ['lab_instances.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['challenge_id'], ['challenges.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['compute_node_id'], ['compute_nodes.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_provisioning_jobs_idempotency_key', 'provisioning_jobs', ['idempotency_key'], unique=True)
    op.create_index('ix_provisioning_jobs_status', 'provisioning_jobs', ['status'])
    op.create_index('ix_provisioning_jobs_lab', 'provisioning_jobs', ['lab_instance_id'])
    op.create_index('ix_provisioning_jobs_celery_task_id', 'provisioning_jobs', ['celery_task_id'])

    # 6. resource_reservations
    op.create_table(
        'resource_reservations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('compute_node_id', sa.Uuid(), nullable=False),
        sa.Column('job_id', sa.Uuid(), nullable=True),
        sa.Column('lab_instance_id', sa.Uuid(), nullable=True),
        sa.Column('cpu_cores', sa.Float(), nullable=False),
        sa.Column('memory_mb', sa.Integer(), nullable=False),
        sa.Column('disk_gb', sa.Integer(), server_default='5', nullable=False),
        sa.Column('status', sa.String(length=16), server_default='reserved', nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['compute_node_id'], ['compute_nodes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_id'], ['provisioning_jobs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['lab_instance_id'], ['lab_instances.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_resource_reservations_node', 'resource_reservations', ['compute_node_id'])
    op.create_index('ix_resource_reservations_status', 'resource_reservations', ['status'])

    # 7. vpn_peers
    op.create_table(
        'vpn_peers',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('public_key', sa.String(length=64), nullable=False),
        sa.Column('preshared_key_hash', sa.String(length=128), nullable=True),
        sa.Column('allocated_ip', sa.String(length=64), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('allowed_subnets', sa.JSON(), nullable=True),
        sa.Column('handshake_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('tx_bytes', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('rx_bytes', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_vpn_peers_user_id', 'vpn_peers', ['user_id'])
    op.create_index('ix_vpn_peers_public_key', 'vpn_peers', ['public_key'], unique=True)
    op.create_index('ix_vpn_peers_allocated_ip', 'vpn_peers', ['allocated_ip'], unique=True)

    # 8. score_events
    op.create_table(
        'score_events',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('competition_id', sa.Uuid(), nullable=True),
        sa.Column('challenge_id', sa.Uuid(), nullable=True),
        sa.Column('event_type', sa.String(length=32), nullable=False),
        sa.Column('points', sa.Integer(), nullable=False),
        sa.Column('current_total', sa.Integer(), nullable=False),
        sa.Column('is_first_blood', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('is_frozen', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['competition_id'], ['competitions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['challenge_id'], ['challenges.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_score_events_user_id', 'score_events', ['user_id'])
    op.create_index('ix_score_events_competition_id', 'score_events', ['competition_id'])
    op.create_index('ix_score_events_recorded_at', 'score_events', ['recorded_at'])


def downgrade() -> None:
    op.drop_table('score_events')
    op.drop_table('vpn_peers')
    op.drop_table('resource_reservations')
    op.drop_table('provisioning_jobs')
    op.drop_table('compute_nodes')
    op.drop_constraint('fk_challenges_template_version_id', 'challenges', type_='foreignkey')
    op.drop_index('ix_challenges_template_version_id', table_name='challenges')
    op.drop_column('challenges', 'template_version_id')
    op.drop_table('machine_template_versions')
    op.drop_table('machine_templates')
