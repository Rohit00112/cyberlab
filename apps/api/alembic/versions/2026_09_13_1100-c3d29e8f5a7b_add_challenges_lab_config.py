"""add challenges.lab_config

Revision ID: c3d29e8f5a7b
Revises: b2f19a7c4d6e
Create Date: 2026-09-13 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d29e8f5a7b'
down_revision: Union[str, Sequence[str], None] = 'b2f19a7c4d6e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('challenges', sa.Column('lab_config', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('challenges', 'lab_config')