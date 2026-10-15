"""Pluggable scoring engine and score event recorder (Phase 4).

Supported scoring modes:
- standard: fixed challenge points minus hint penalty
- dynamic: logarithmic/hyperbolic decay based on solve count
- first_blood: dynamic or standard with first/second/third blood bonuses
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.challenges import Challenge
from app.models.competitions import Competition
from app.models.submissions import Submission
from app.models.vpn_scoring import ScoreEvent


def compute_dynamic_points(
    base_points: int,
    solve_count: int,
    *,
    min_points: int = 100,
    decay_scale: int = 15,
) -> int:
    """Calculate decayed challenge point value based on total solve count.

    Formula: min_points + (base_points - min_points) * (1 / (1 + (solve_count - 1) / decay_scale))
    When solve_count == 1, returns base_points.
    As solve_count increases, approaches min_points.
    """
    if solve_count <= 1:
        return base_points
    min_pts = min(min_points, base_points)
    decay_ratio = 1.0 / (1.0 + (solve_count - 1) / float(max(1, decay_scale)))
    computed = min_pts + (base_points - min_pts) * decay_ratio
    return max(min_pts, int(round(computed)))


def calculate_first_blood_bonus(rank: int, base_points: int) -> int:
    """Return bonus points for top solves (PRD §40)."""
    if rank == 1:
        return int(round(base_points * 0.20))  # +20% first blood
    if rank == 2:
        return int(round(base_points * 0.10))  # +10% second blood
    if rank == 3:
        return int(round(base_points * 0.05))  # +5% third blood
    return 0


async def record_submission_score_event(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    challenge: Challenge,
    competition: Competition | None = None,
    penalty: int = 0,
) -> ScoreEvent:
    """Evaluate points according to scoring mode and record an immutable ScoreEvent."""
    mode = competition.scoring_mode if competition else "standard"
    comp_id = competition.id if competition else None

    # Determine solve rank for this challenge in this context
    count_stmt = (
        select(func.count())
        .select_from(Submission)
        .where(
            Submission.challenge_id == challenge.id,
            Submission.is_correct.is_(True),
        )
    )
    if competition and competition.start_at:
        count_stmt = count_stmt.where(Submission.created_at >= competition.start_at)
    total_solves = int(await db.scalar(count_stmt) or 0)
    current_solve_rank = total_solves + 1

    earned = challenge.points
    is_first = current_solve_rank == 1

    if mode == "dynamic":
        earned = compute_dynamic_points(challenge.points, current_solve_rank)
    elif mode == "first_blood":
        bonus = calculate_first_blood_bonus(current_solve_rank, challenge.points)
        earned = challenge.points + bonus

    final_points = max(0, earned - penalty)

    # Calculate user's current total score
    total_prev = int(
        await db.scalar(
            select(func.sum(ScoreEvent.points)).where(
                ScoreEvent.user_id == user_id,
                ScoreEvent.competition_id == comp_id,
            )
        )
        or 0
    )
    new_total = total_prev + final_points

    is_frozen = bool(competition and competition.freeze_leaderboard)

    event = ScoreEvent(
        user_id=user_id,
        competition_id=comp_id,
        challenge_id=challenge.id,
        event_type="solve",
        points=final_points,
        current_total=new_total,
        is_first_blood=is_first,
        is_frozen=is_frozen,
        recorded_at=datetime.now(UTC),
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def freeze_competition_leaderboard(db: AsyncSession, competition: Competition) -> Competition:
    """Freeze the competition leaderboard."""
    competition.freeze_leaderboard = True
    competition.frozen_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(competition)
    return competition


async def unfreeze_competition_leaderboard(
    db: AsyncSession, competition: Competition
) -> Competition:
    """Unfreeze the competition leaderboard."""
    competition.freeze_leaderboard = False
    competition.frozen_at = None
    await db.commit()
    await db.refresh(competition)
    return competition
