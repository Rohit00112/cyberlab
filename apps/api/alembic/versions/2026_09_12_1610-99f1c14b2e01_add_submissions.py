"""add submissions

Revision ID: 99f1c14b2e01
Revises: 60432c9d0e1d
Create Date: 2026-09-12 16:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '99f1c14b2e01'
down_revision: Union[str, Sequence[str], None] = '60432c9d0e1d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'submissions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('challenge_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('is_correct', sa.Boolean(), nullable=False),
        sa.Column('earned_points', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['challenge_id'], ['challenges.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_submissions_challenge_id'), 'submissions', ['challenge_id'], unique=False)
    op.create_index(op.f('ix_submissions_created_at'), 'submissions', ['created_at'], unique=False)
    op.create_index(op.f('ix_submissions_user_id'), 'submissions', ['user_id'], unique=False)
    # A student can solve a challenge exactly once.
    op.create_index(
        'uq_submissions_correct',
        'submissions',
        ['challenge_id', 'user_id'],
        unique=True,
        postgresql_where=sa.text('is_correct'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_submissions_correct', table_name='submissions')
    op.drop_index(op.f('ix_submissions_user_id'), table_name='submissions')
    op.drop_index(op.f('ix_submissions_created_at'), table_name='submissions')
    op.drop_index(op.f('ix_submissions_challenge_id'), table_name='submissions')
    op.drop_table('submissions')