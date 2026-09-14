"""add notifications and lab provider

Revision ID: e1f2a3b4c5d6
Revises: d5e6f7a8b9c0
Create Date: 2026-09-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add notifications, announcements, and lab provider columns (Tracks 3 and 4)."""
    # Lab provider columns
    op.add_column(
        'lab_instances',
        sa.Column('provider', sa.String(length=16), server_default=sa.text("'docker'"), nullable=False),
    )
    op.add_column(
        'lab_instances',
        sa.Column('provider_ref', sa.String(length=255), nullable=True),
    )

    # Notifications table
    op.create_table(
        'notifications',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('link', sa.String(length=500), nullable=True),
        sa.Column('is_read', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('source', sa.String(length=32), server_default=sa.text("'system'"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_notifications_user_read', 'notifications', ['user_id', 'is_read'])

    # Announcements table
    op.create_table(
        'announcements',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('author_id', sa.Uuid(), nullable=True),
        sa.Column('target', sa.String(length=120), server_default=sa.text("'all'"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('announcements')
    op.drop_index('ix_notifications_user_read', table_name='notifications')
    op.drop_table('notifications')
    op.drop_column('lab_instances', 'provider_ref')
    op.drop_column('lab_instances', 'provider')
