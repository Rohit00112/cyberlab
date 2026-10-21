"""Widen audit target identifiers to fit challenge slugs.

Revision ID: a2bc34de56f7
Revises: f1a2b3c4d5e6
"""
import sqlalchemy as sa

from alembic import op

revision = "a2bc34de56f7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "audit_logs", "target_id", existing_type=sa.String(length=64),
        type_=sa.String(length=120), existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "audit_logs", "target_id", existing_type=sa.String(length=120),
        type_=sa.String(length=64), existing_nullable=True,
    )
