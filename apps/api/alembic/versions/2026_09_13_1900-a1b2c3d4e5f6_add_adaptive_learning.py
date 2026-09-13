"""add adaptive learning tables

Revision ID: a1b2c3d4e5f6
Revises: 51a7d3f9c0b2
Create Date: 2026-09-13 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '51a7d3f9c0b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # --- user_skill_profiles ---
    op.create_table('user_skill_profiles',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('skill_id', sa.Uuid(), nullable=False),
        sa.Column('competency_level', sa.Float(), nullable=False, server_default=sa.text('0.0')),
        sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('uq_user_skill_profile', 'user_skill_profiles', ['user_id', 'skill_id'], unique=True)
    op.create_index(op.f('ix_user_skill_profiles_user_id'), 'user_skill_profiles', ['user_id'])
    op.create_index(op.f('ix_user_skill_profiles_skill_id'), 'user_skill_profiles', ['skill_id'])

    # --- learning_paths ---
    op.create_table('learning_paths',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('slug', sa.String(length=120), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_published', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_learning_paths_slug'), 'learning_paths', ['slug'], unique=True)

    # --- learning_path_steps ---
    op.create_table('learning_path_steps',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('learning_path_id', sa.Uuid(), nullable=False),
        sa.Column('challenge_id', sa.Uuid(), nullable=False),
        sa.Column('step_order', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['learning_path_id'], ['learning_paths.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['challenge_id'], ['challenges.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('uq_learning_path_challenge', 'learning_path_steps', ['learning_path_id', 'challenge_id'], unique=True)
    op.create_index('ix_learning_path_step_order', 'learning_path_steps', ['learning_path_id', 'step_order'])

    # --- challenges: add difficulty columns ---
    op.add_column('challenges', sa.Column('difficulty_score', sa.Float(), server_default=sa.text('0.2'), nullable=False))
    op.add_column('challenges', sa.Column('difficulty_scored_at_count', sa.Integer(), server_default=sa.text('0'), nullable=False))

    # Backfill difficulty_score from difficulty enum
    op.execute("""
        UPDATE challenges SET difficulty_score = CASE difficulty
            WHEN 'beginner' THEN 0.2
            WHEN 'intermediate' THEN 0.5
            WHEN 'advanced' THEN 0.8
            ELSE 0.2
        END
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('challenges', 'difficulty_scored_at_count')
    op.drop_column('challenges', 'difficulty_score')
    op.drop_index('ix_learning_path_step_order', table_name='learning_path_steps')
    op.drop_index('uq_learning_path_challenge', table_name='learning_path_steps')
    op.drop_table('learning_path_steps')
    op.drop_index(op.f('ix_learning_paths_slug'), table_name='learning_paths')
    op.drop_table('learning_paths')
    op.drop_index(op.f('ix_user_skill_profiles_skill_id'), table_name='user_skill_profiles')
    op.drop_index(op.f('ix_user_skill_profiles_user_id'), table_name='user_skill_profiles')
    op.drop_index('uq_user_skill_profile', table_name='user_skill_profiles')
    op.drop_table('user_skill_profiles')
