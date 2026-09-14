"""Graph recommender (Phase 7): rank candidates on the solved-adjacency graph.

Uses the knowledge-graph signals that are cheap to compute at request time:
  - competency skill match (same base as `rule`),
  - co-solve popularity: distinct users who solved the candidate AND at least
    one challenge the user has already solved (PRD §72 edge semantics),
  - learning-path ordering: a boost when the candidate appears in a path step
    *after* a challenge the user already solved.
"""
from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.learning_paths import LearningPathStep
from app.models.submissions import Submission
from app.services.rec_common import difficulty_gap, skill_match

# relative weight of co-solve popularity vs the baseline skill match
CO_SOLVE_WEIGHT = 0.6
PATH_BOOST = 0.3


async def _co_solve_counts(
    db: AsyncSession,
    candidate_ids: set[uuid.UUID],
    solved_ids: set[uuid.UUID],
) -> dict[uuid.UUID, int]:
    """Distinct users who solved a candidate challenge and a solved challenge."""
    if not candidate_ids or not solved_ids:
        return {}
    mine = aliased(Submission)
    theirs = aliased(Submission)
    rows = (
        await db.execute(
            select(mine.challenge_id, func.count(func.distinct(mine.user_id)))
            .join(theirs, theirs.user_id == mine.user_id)
            .where(
                mine.is_correct.is_(True),
                mine.challenge_id.in_(candidate_ids),
                theirs.is_correct.is_(True),
                theirs.challenge_id.in_(solved_ids),
            )
            .group_by(mine.challenge_id)
        )
    ).all()
    return {challenge_id: int(count) for challenge_id, count in rows}


async def _path_orders(
    db: AsyncSession, challenge_ids: set[uuid.UUID]
) -> dict[uuid.UUID, dict[uuid.UUID, int]]:
    """path_id -> {challenge_id: step_order} for the given challenges."""
    if not challenge_ids:
        return {}
    rows = (
        await db.execute(
            select(LearningPathStep).where(LearningPathStep.challenge_id.in_(challenge_ids))
        )
    ).all()
    orders: dict[uuid.UUID, dict[uuid.UUID, int]] = defaultdict(dict)
    for (step,) in rows:
        orders[step.learning_path_id][step.challenge_id] = step.step_order
    return orders


def _path_boost(
    candidate_id: uuid.UUID,
    solved_ids: set[uuid.UUID],
    path_orders: dict[uuid.UUID, dict[uuid.UUID, int]],
) -> float:
    """0 or PATH_BOOST when a solved challenge precedes the candidate in a path."""
    for orders in path_orders.values():
        candidate_order = orders.get(candidate_id)
        if candidate_order is None:
            continue
        if any(
            solved_id in orders and orders[solved_id] < candidate_order for solved_id in solved_ids
        ):
            return PATH_BOOST
    return 0.0


async def recommend_graph(
    db: AsyncSession,
    candidates: list[dict],
    solved_ids: set[uuid.UUID],
    user_competency: dict[uuid.UUID, float],
    limit: int,
) -> list[dict]:
    """Score candidates graph-aware and return the top `limit` (score desc)."""
    if not candidates:
        return []

    candidate_ids = {item["challenge"].id for item in candidates}
    co_solve = await _co_solve_counts(db, candidate_ids, solved_ids)
    path_orders = await _path_orders(db, candidate_ids | solved_ids)
    max_co = max(co_solve.values()) if co_solve else 0

    scored = []
    for item in candidates:
        challenge = item["challenge"]
        co = (co_solve.get(challenge.id, 0) / max_co) if max_co else 0.0
        path = _path_boost(challenge.id, solved_ids, path_orders)
        if not user_competency:
            score = (co * CO_SOLVE_WEIGHT) + path
        else:
            user_avg = sum(user_competency.values()) / len(user_competency)
            base = skill_match(challenge, item["skills"], user_competency) - (
                difficulty_gap(challenge, user_avg) * 0.3
            )
            score = base + (co * CO_SOLVE_WEIGHT) + path
        item["score"] = score
        scored.append((item, score))

    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [item for item, _ in scored[:limit]]