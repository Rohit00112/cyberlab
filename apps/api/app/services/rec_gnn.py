"""GNN recommender (Phase 7): serve a pretrained graph encoder via ONNX.

Contract of the exported model file (`data/research/model/gnn.onnx`):
  * input  "features"  float32 [N, 5]
  * output "embeddings" float32 [N, D]

Each row is a challenge. The 5 input features, in order:
  1. difficulty_score        (0..1)
  2. platform solve rate     (0..1)
  3. points / 1000
  4. number of tagged skills / 10
  5. number of learning-path predecessors / 10

The user embedding is the mean of their solved challenges' embeddings; a
candidate is scored by cosine similarity blended with the competency
skill match. The scorer is dependency-free (pure Python); only model serving
requires the optional `onnxruntime` extra.
"""
from __future__ import annotations

import math
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.challenges import Challenge
from app.models.learning_paths import LearningPathStep
from app.models.skills import ChallengeSkill
from app.models.submissions import Submission
from app.services.rec_common import RecommenderError

FEATURE_DIM = 5
COSINE_WEIGHT = 0.8
SKILL_MATCH_WEIGHT = 0.2


def load_gnn_session():
    """Import onnxruntime lazily and load the frozen model (sync, cached)."""
    try:
        import onnxruntime  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RecommenderError("onnxruntime is not installed (add the 'research' extra)") from exc

    path = get_settings().gnn_model_path
    model_path = str(path)
    try:
        with open(model_path, "rb"):
            pass
    except OSError as exc:
        raise RecommenderError(f"gnn model artifact not found at {model_path}") from exc
    return onnxruntime.InferenceSession(model_path, providers=["CPUExecutionProvider"])


def build_features(
    difficulty_score: float,
    solve_rate: float,
    points: int,
    skill_count: int,
    path_predecessors: int,
) -> list[float]:
    return [
        max(0.0, min(1.0, difficulty_score)),
        max(0.0, min(1.0, solve_rate)),
        min(points / 1000, 1.0),
        min(skill_count / 10, 1.0),
        min(path_predecessors / 10, 1.0),
    ]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(-1.0, min(1.0, dot / (norm_a * norm_b)))


async def _solve_rates(
    db: AsyncSession, challenge_ids: set[uuid.UUID]
) -> dict[uuid.UUID, float]:
    """Platform-wide solve rate per challenge (aggregate, not per-user)."""
    if not challenge_ids:
        return {}
    rows = (
        await db.execute(
            select(
                Submission.challenge_id,
                func.count(Submission.id).filter(Submission.is_correct.is_(True)),
                func.count(Submission.id),
            )
            .where(Submission.challenge_id.in_(challenge_ids))
            .group_by(Submission.challenge_id)
        )
    ).all()
    rates = {}
    for challenge_id, solves, total in rows:
        total = int(total or 0)
        rates[challenge_id] = int(solves or 0) / total if total else 0.0
    return rates


async def _path_predecessors(
    db: AsyncSession, challenge_ids: set[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """Number of (path, step) predecessors for each challenge."""
    if not challenge_ids:
        return {}
    rows = (
        await db.execute(
            select(LearningPathStep.challenge_id, func.count(LearningPathStep.id))
            .where(LearningPathStep.challenge_id.in_(challenge_ids))
            .group_by(LearningPathStep.challenge_id)
        )
    ).all()
    return {challenge_id: int(count) for challenge_id, count in rows}


async def recommend_gnn(
    db: AsyncSession,
    candidates: list[dict],
    solved_ids: set[uuid.UUID],
    user_competency: dict[uuid.UUID, float],
    limit: int,
) -> list[dict]:
    """Score candidates with the frozen GNN; raise RecommenderError on any failure."""
    if not candidates:
        return []
    session = load_gnn_session()

    candidate_ids = {item["challenge"].id for item in candidates}
    embed_ids = candidate_ids | solved_ids
    if not embed_ids:
        return []

    solve_rates = await _solve_rates(db, embed_ids)
    predecessors = await _path_predecessors(db, embed_ids)
    skill_rows = (
        await db.execute(
            select(ChallengeSkill.challenge_id, func.count(ChallengeSkill.id))
            .where(ChallengeSkill.challenge_id.in_(embed_ids))
            .group_by(ChallengeSkill.challenge_id)
        )
    ).all()
    skill_counts = {challenge_id: int(count) for challenge_id, count in skill_rows}
    solve_rows: dict[uuid.UUID, Challenge] = {}
    if solved_ids:
        solved_challenges = (
            await db.execute(select(Challenge).where(Challenge.id.in_(solved_ids)))
        ).scalars()
        solve_rows = {c.id: c for c in solved_challenges}

    ordered = [item["challenge"] for item in candidates]
    ordered_ids = [c.id for c in ordered] + list(solved_ids - candidate_ids)

    features, embedding_ids = [], []
    for cid in ordered_ids:
        challenge = solve_rows.get(cid)
        if challenge is None:
            continue
        features.append(
            build_features(
                difficulty_score=challenge.difficulty_score,
                solve_rate=solve_rates.get(cid, 0.0),
                points=challenge.points,
                skill_count=skill_counts.get(cid, 0),
                path_predecessors=predecessors.get(cid, 0),
            )
        )
        embedding_ids.append(cid)

    try:
        result = session.run(None, {"features": features})
    except Exception as exc:  # noqa: BLE001 - any serving failure degrades to rule
        raise RecommenderError(f"gnn inference failed: {exc}") from exc
    embeddings = result[0]
    vectors = embeddings.tolist() if hasattr(embeddings, "tolist") else list(embeddings)

    map_by_id = dict(zip(embedding_ids, vectors, strict=False))
    solved_vectors = [map_by_id[cid] for cid in solved_ids if cid in map_by_id]
    user_ref = (
        [sum(col) / len(solved_vectors) for col in zip(*solved_vectors, strict=False)]
        if solved_vectors
        else None
    )

    scored = []
    for item in candidates:
        vector = map_by_id.get(item["challenge"].id)
        if vector is None or user_ref is None:
            continue
        sim = _cosine(user_ref, vector)
        if user_competency:
            challenge = item["challenge"]
            match = sum(user_competency.get(s.id, 0.0) for s in item["skills"]) / len(
                item["skills"]
            ) if item["skills"] else 0.0
            score = (sim * COSINE_WEIGHT) + (match / 100 * SKILL_MATCH_WEIGHT)
        else:
            score = sim
        scored.append((item, score))

    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [item for item, _ in scored[:limit]]