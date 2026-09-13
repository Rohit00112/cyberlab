"""add hint_penalty column and hint_reveals table

Revision ID: a4b1c2d3e4f5
Revises: 99f1c14b2e01
Create Date: 2026-09-12 16:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a4b1c2d3e4f5'
down_revision: Union[str, Sequence[str], None] = '99f1c14b2e01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('challenges', sa.Column('hint_penalty', sa.Integer(), server_default='0', nullable=False))
    # Drop server_default so ORM Python default drives the value.
    op.alter_column('challenges', 'hint_penalty', server_default=None)

    op.create_table(
        'hint_reveals',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('challenge_id', sa.Uuid(), nullable=False),
        sa.Column('hint_index', sa.Integer(), nullable=False),
        sa.Column('revealed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['challenge_id'], ['challenges.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_hint_reveals_challenge_id'), 'hint_reveals', ['challenge_id'], unique=False)
    op.create_index(op.f('ix_hint_reveals_user_id'), 'hint_reveals', ['user_id'], unique=False)
    op.create_index(
        'uq_hint_reveal',
        'hint_reveals',
        ['user_id', 'challenge_id', 'hint_index'],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_hint_reveal', table_name='hint_reveals')
    op.drop_index(op.f('ix_hint_reveals_user_id'), table_name='hint_reveals')
    op.drop_index(op.f('ix_hint_reveals_challenge_id'), table_name='hint_reveals')
    op.drop_table('hint_reveals')
    op.drop_column('challenges', 'hint_penalty')