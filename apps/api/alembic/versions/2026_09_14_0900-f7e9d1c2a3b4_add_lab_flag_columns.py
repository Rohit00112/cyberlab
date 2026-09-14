"""add per-session lab flag columns

Revision ID: f7e9d1c2a3b4
Revises: a1b2c3d4e5f6
Create Date: 2026-09-14 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7e9d1c2a3b4'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add per-session lab flag storage (SHA-256 hash only, never plaintext)."""
    op.add_column('lab_instances', sa.Column('flag_hash', sa.String(length=64), nullable=True))
    op.add_column('lab_instances', sa.Column('flag_path', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('lab_instances', 'flag_path')
    op.drop_column('lab_instances', 'flag_hash')