"""add research platform tables

Revision ID: d5e6f7a8b9c0
Revises: f7e9d1c2a3b4
Create Date: 2026-09-14 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, Sequence[str], None] = 'f7e9d1c2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add research platform tables (Phase 6, PRD §70-§72)."""
    op.create_table(
        'research_datasets',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('pseudonymized', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('row_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('file_ref', sa.String(length=255), nullable=True),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'research_experiments',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('model_ref', sa.String(length=120), nullable=False),
        sa.Column('params', sa.JSON(), nullable=True),
        sa.Column('metrics', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=16), server_default=sa.text("'queued'"), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'recommendation_logs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('challenge_id', sa.Uuid(), nullable=False),
        sa.Column('source', sa.String(length=16), server_default=sa.text("'adaptive'"), nullable=False),
        sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['challenge_id'], ['challenges.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_recommendation_logs_challenge', 'recommendation_logs', ['challenge_id'])
    op.create_index('ix_recommendation_logs_user_date', 'recommendation_logs', ['user_id', 'generated_at'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_recommendation_logs_user_date', table_name='recommendation_logs')
    op.drop_index('ix_recommendation_logs_challenge', table_name='recommendation_logs')
    op.drop_table('recommendation_logs')
    op.drop_table('research_experiments')
    op.drop_table('research_datasets')