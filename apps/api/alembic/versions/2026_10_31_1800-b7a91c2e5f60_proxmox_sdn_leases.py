"""Store Proxmox SDN VNet reservations independently from lab/user lifecycle.

Revision ID: b7a91c2e5f60
Revises: a2bc34de56f7
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "b7a91c2e5f60"
down_revision = "a2bc34de56f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proxmox_sdn_leases",
        sa.Column("vnet", sa.String(length=8), nullable=False),
        # Deliberately no FK to users: on-delete CASCADE would free a live network.
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "assigned_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("vnet"),
    )
    op.create_index(
        "ix_proxmox_sdn_leases_user_id", "proxmox_sdn_leases", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_proxmox_sdn_leases_user_id", table_name="proxmox_sdn_leases")
    op.drop_table("proxmox_sdn_leases")
