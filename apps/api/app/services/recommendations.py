"""Recommendation dispatcher with protocol-based backend selection (Phase 7, PRD §72).

Flow:
  1. Build candidate pool (unsolved published challenges + user competency)
  2. Read ``settings.recommendation_backend`` → ``rule | graph | gnn``
  3. Dispatch to the selected backend
  4. On any ``RecommenderError``, fall back to ``recommend_rule()``
  5. Tag ``ChallengeRecommendationOut.source`` and ``RecommendationLog.source``
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, time

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.challenges import Challenge
from app.models.research import RecommendationLog
from app.models.submissions import Submission
from app.schemas.recommendation import ChallengeRecommendationOut
from app.schemas.skill import SkillBrief
from app.services.rec_common import RecommenderError, candidate_pool, recommend_rule
from app.services.rec_gnn import recommend_gnn
from app.services.rec_graph import recommend_graph

logger = logging.getLogger("cyberlab.recommendations")


async def refresh_difficulty_score(db: AsyncSession, challenge: Challenge) -> None:
    """Recomputes standard ELO-adjacent difficulty score after every 10 fresh attempts."""
    total_unfiltered = await db.scalar(
        select(func.count(Submission.id)).where(Submission.challenge_id == challenge.id)
    )
    total = int(total_unfiltered or 0)

    if total - challenge.difficulty_scored_at_count < 10:
        return

    solves_unfiltered = await db.scalar(
        select(func.count(Submission.id)).where(
            Submission.challenge_id == challenge.id,
            Submission.is_correct.is_(True),
        )
    )
    solves = int(solves_unfiltered or 0)

    score = (total - solves) / total if total > 0 else 0.2

    challenge.difficulty_score = max(0.0, min(1.0, score))
    challenge.difficulty_scored_at_count = total
    db.add(challenge)
    await db.flush()


async def refresh_challenge_difficulty_after_submission(
    db: AsyncSession, challenge_id: uuid.UUID
) -> None:
    """Helper invoked downstream from flag submission."""
    challenge = await db.get(Challenge, challenge_id)
    if challenge:
        await refresh_difficulty_score(db, challenge)


async def _log_recommendations(
    db: AsyncSession,
    user_id: uuid.UUID,
    recommendations: list[ChallengeRecommendationOut],
    source: str,
) -> None:
    """Record served impressions once per (user, challenge, day) for H1 (§72)."""
    if not recommendations:
        return
    day_start = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)
    already_served = set(
        (
            await db.scalars(
                select(RecommendationLog.challenge_id).where(
                    RecommendationLog.user_id == user_id,
                    RecommendationLog.generated_at >= day_start,
                )
            )
        ).all()
    )
    for recommendation in recommendations:
        if recommendation.challenge_id not in already_served:
            db.add(
                RecommendationLog(
                    user_id=user_id, challenge_id=recommendation.challenge_id, source=source
                )
            )
    await db.commit()


def _build_outputs(
    items: list[dict], source: str
) -> list[ChallengeRecommendationOut]:
    """Convert scored candidate dicts to response schema."""
    return [
        ChallengeRecommendationOut(
            challenge_id=item["challenge"].id,
            slug=item["challenge"].slug,
            title=item["challenge"].title,
            category=item["challenge"].category,
            difficulty=item["challenge"].difficulty,
            points=item["challenge"].points,
            difficulty_score=item["challenge"].difficulty_score,
            recommendation_score=item.get("score", 0.0),
            source=source,
            skills=[
                SkillBrief(id=s.id, slug=s.slug, name=s.name, icon=s.icon)
                for s in item["skills"]
            ],
        )
        for item in items
    ]


async def get_recommendations(
    db: AsyncSession, user_id: uuid.UUID, limit: int = 10
) -> list[ChallengeRecommendationOut]:
    """Dispatch to the configured backend with rule fallback."""
    limit = min(max(limit, 1), 50)
    settings = get_settings()
    backend = settings.recommendation_backend

    solved_ids, candidates, user_competency = await candidate_pool(db, user_id)

    if not candidates:
        return []

    source = backend
    items: list[dict] = []

    try:
        if backend == "graph":
            items = await recommend_graph(
                db, candidates, solved_ids, user_competency, limit
            )
        elif backend == "gnn":
            items = await recommend_gnn(
                db, candidates, solved_ids, user_competency, limit
            )
        else:
            items = await recommend_rule(candidates, user_competency, limit)
            source = "rule"
    except RecommenderError as exc:
        logger.warning(
            "backend '%s' failed (%s); falling back to rule", backend, exc
        )
        source = "rule"
        items = await recommend_rule(candidates, user_competency, limit)
    except Exception:  # noqa: BLE001
        logger.exception(
            "unexpected error in backend '%s'; falling back to rule", backend
        )
        source = "rule"
        items = await recommend_rule(candidates, user_competency, limit)

    recommendations = _build_outputs(items, source)
    await _log_recommendations(db, user_id, recommendations, source)
    return recommendations


async def recommendation_status() -> dict:
    """Return the current recommendation backend configuration and health."""
    settings = get_settings()
    backend = settings.recommendation_backend
    healthy = True
    model_path: str | None = None

    if backend == "gnn":
        model_path = settings.gnn_model_path
        try:
            from app.services.rec_gnn import load_gnn_session

            load_gnn_session()
        except RecommenderError:
            healthy = False

    return {
        "backend": backend,
        "healthy": healthy,
        "model_path": model_path,
    }
