"""Research platform services (Phase 6, PRD §70-§72).

Everything exported here is pseudonymized: identity columns are replaced by a
HMAC-based ``participant_id`` and PII keys are dropped before anything touches
disk or an API response. Artifact bytes live in ``settings.research_data_dir``
(never the database), and rows carry an expiry so exported data cannot be kept
around indefinitely.
"""
from __future__ import annotations

import csv
import json
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.pseudonym import pseudonymize_identity
from app.models.badges import Badge, UserBadge
from app.models.challenges import Challenge
from app.models.hint_reveals import HintReveal
from app.models.labs import LabInstance
from app.models.learning_paths import LearningPathStep
from app.models.research import RecommendationLog, ResearchDataset, ResearchExperiment
from app.models.skill_profiles import UserSkillProfile
from app.models.skills import ChallengeSkill, Skill
from app.models.submissions import Submission
from app.models.users import User
from app.schemas.research import (
    ChallengeQualityMetric,
    DatasetCreate,
    GraphEdge,
    GraphNode,
    MetricsEngagement,
    MetricsLearning,
    MetricsRecommendations,
    ResearchDatasetOut,
    ResearchExperimentOut,
    ResearchGraphOut,
    ResearchMetricsOut,
    SourceRecommendationMetrics,
)

RESEARCH_DIR_OVERRIDE: Path | None = None


# --------------------------------------------------------------------------- #
# Dataset building (PRD §70 — pseudonymized, expiring exports)
# --------------------------------------------------------------------------- #

def _data_dir() -> Path:
    if RESEARCH_DIR_OVERRIDE is not None:
        return RESEARCH_DIR_OVERRIDE
    directory = Path(get_settings().research_data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _date(elem: datetime | None) -> str | None:
    return elem.isoformat() if elem is not None else None


async def _submission_rows(db: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(
                User.keycloak_sub,
                Submission.challenge_id,
                Challenge.slug,
                Challenge.title,
                Challenge.category,
                Challenge.difficulty,
                Challenge.points,
                Submission.is_correct,
                Submission.earned_points,
                Submission.created_at,
            )
            .join(Challenge, Challenge.id == Submission.challenge_id)
            .join(User, User.id == Submission.user_id)
            .order_by(Submission.created_at.asc())
        )
    ).all()
    result: list[dict[str, Any]] = []
    for (
        sub,
        challenge_id,
        slug,
        title,
        category,
        difficulty,
        points,
        is_correct,
        earned_points,
        created_at,
    ) in rows:
        result.append(
            pseudonymize_identity(
                {
                    "user_id": None,
                    "challenge_id": str(challenge_id),
                    "challenge_slug": slug,
                    "title": title,
                    "category": category,
                    "difficulty": difficulty,
                    "points": points,
                    "is_correct": is_correct,
                    "earned_points": int(earned_points or 0),
                    "created_at": _date(created_at),
                },
                sub,
            )
        )
    return result


async def _skill_profile_rows(db: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(
                User.keycloak_sub,
                UserSkillProfile.skill_id,
                Skill.slug,
                Skill.name,
                Skill.parent_id,
                UserSkillProfile.competency_level,
                UserSkillProfile.last_updated,
            )
            .join(User, User.id == UserSkillProfile.user_id)
            .join(Skill, Skill.id == UserSkillProfile.skill_id)
        )
    ).all()
    return [
        pseudonymize_identity(
            {
                "user_id": None,
                "skill_id": str(skill_id),
                "skill_slug": slug,
                "skill_name": name,
                "parent_skill_id": str(parent_id) if parent_id else None,
                "competency_level": round(float(competency), 4),
                "last_updated": _date(last_updated),
            },
            sub,
        )
        for sub, skill_id, slug, name, parent_id, competency, last_updated in rows
    ]


async def _badge_rows(db: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(
                User.keycloak_sub,
                UserBadge.badge_id,
                Badge.code,
                Badge.name,
                UserBadge.earned_at,
                UserBadge.evidence,
            )
            .join(User, User.id == UserBadge.user_id)
            .join(Badge, Badge.id == UserBadge.badge_id)
        )
    ).all()
    return [
        pseudonymize_identity(
            {
                "user_id": None,
                "badge_id": str(badge_id),
                "badge_code": code,
                "badge_name": name,
                "earned_at": _date(earned_at),
                "evidence": evidence,
            },
            sub,
        )
        for sub, badge_id, code, name, earned_at, evidence in rows
    ]


async def _hint_rows(db: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(
                User.keycloak_sub,
                HintReveal.challenge_id,
                Challenge.slug,
                Challenge.title,
                HintReveal.hint_index,
                HintReveal.revealed_at,
            )
            .join(Challenge, Challenge.id == HintReveal.challenge_id)
            .join(User, User.id == HintReveal.user_id)
        )
    ).all()
    return [
        pseudonymize_identity(
            {
                "user_id": None,
                "challenge_id": str(challenge_id),
                "challenge_slug": slug,
                "title": title,
                "hint_index": int(hint_index),
                "revealed_at": _date(revealed_at),
            },
            sub,
        )
        for sub, challenge_id, slug, title, hint_index, revealed_at in rows
    ]


async def _lab_rows(db: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(
                User.keycloak_sub,
                LabInstance.challenge_id,
                Challenge.slug,
                Challenge.title,
                LabInstance.status,
                LabInstance.created_at,
                LabInstance.updated_at,
                LabInstance.expires_at,
            )
            .join(Challenge, Challenge.id == LabInstance.challenge_id)
            .join(User, User.id == LabInstance.user_id)
            .order_by(LabInstance.created_at.asc())
        )
    ).all()
    return [
        pseudonymize_identity(
            {
                "user_id": None,
                "challenge_id": str(challenge_id),
                "challenge_slug": slug,
                "title": title,
                "status": lab_status,
                "created_at": _date(created_at),
                "updated_at": _date(updated_at),
                "expires_at": _date(expires_at),
            },
            sub,
        )
        for sub, challenge_id, slug, title, lab_status, created_at, updated_at, expires_at in rows
    ]


async def _progress_rows(db: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(
                User.keycloak_sub,
                Submission.challenge_id,
                Challenge.slug,
                Challenge.title,
                Submission.created_at,
            )
            .join(Challenge, Challenge.id == Submission.challenge_id)
            .join(User, User.id == Submission.user_id)
            .where(Submission.is_correct.is_(True))
        )
    ).all()
    steps = (
        await db.execute(
            select(
                LearningPathStep.challenge_id,
                LearningPathStep.learning_path_id,
                LearningPathStep.step_order,
            )
        )
    ).all()
    step_map: dict[uuid.UUID, tuple[uuid.UUID, int]] = {
        challenge_id: (learning_path_id, int(step_order))
        for challenge_id, learning_path_id, step_order in steps
    }
    result: list[dict[str, Any]] = []
    for sub, challenge_id, slug, title, created_at in rows:
        path_entry = step_map.get(challenge_id)
        result.append(
            pseudonymize_identity(
                {
                    "user_id": None,
                    "challenge_id": str(challenge_id),
                    "challenge_slug": slug,
                    "title": title,
                    "learning_path_id": str(path_entry[0]) if path_entry else None,
                    "step_order": path_entry[1] if path_entry else None,
                    "solved_at": _date(created_at),
                },
                sub,
            )
        )
    return result


async def _engagement_rows(db: AsyncSession) -> list[dict[str, Any]]:
    empty_day = {"attempts": 0, "solves": 0, "hints": 0}
    activity: dict[str, dict[date, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: dict(empty_day))
    )
    rows = (
        await db.execute(
            select(User.keycloak_sub, Submission.created_at, Submission.is_correct).join(
                User, User.id == Submission.user_id
            )
        )
    ).all()
    for sub, created_at, is_correct in rows:
        day = created_at.date() if created_at else None
        if day is not None:
            activity[sub][day]["attempts"] += 1
            if is_correct:
                activity[sub][day]["solves"] += 1
    hint_rows = (
        await db.execute(
            select(User.keycloak_sub, HintReveal.revealed_at).join(
                User, User.id == HintReveal.user_id
            )
        )
    ).all()
    for sub, revealed_at in hint_rows:
        day = revealed_at.date() if revealed_at else None
        if day is not None:
            activity[sub][day]["hints"] += 1

    result: list[dict[str, Any]] = []
    for sub, days in activity.items():
        seen = set()
        for day, counts in sorted(days.items()):
            if day in seen:
                continue
            seen.add(day)
            result.append(
                pseudonymize_identity(
                    {
                        "user_id": None,
                        "activity_date": day.isoformat(),
                        "attempts": counts["attempts"],
                        "solves": counts["solves"],
                        "hints_used": counts["hints"],
                    },
                    sub,
                )
            )
    return result


_KIND_COLLECTORS: dict[str, Any] = {
    "submissions": _submission_rows,
    "skill_profiles": _skill_profile_rows,
    "badges": _badge_rows,
    "hints": _hint_rows,
    "labs": _lab_rows,
    "learning_progress": _progress_rows,
    "engagements": _engagement_rows,
}


def _csv_dump(path: Path, rows: list[dict[str, Any]]) -> None:
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in keys})


async def build_dataset(
    db: AsyncSession, data: DatasetCreate, created_by: uuid.UUID
) -> ResearchDatasetOut:
    if data.kind == "all":
        rows: list[dict[str, Any]] = []
        for kind in _KIND_COLLECTORS:
            for row in await _KIND_COLLECTORS[kind](db):
                tagged = dict(row)
                tagged["source_kind"] = kind
                rows.append(tagged)
    else:
        rows = await _KIND_COLLECTORS[data.kind](db)

    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(
        days=data.expires_in_days or settings.research_dataset_expiry_days
    )

    dataset_id = uuid.uuid4()
    directory = _data_dir()
    json_ref = f"{dataset_id}.json"
    csv_ref = f"{dataset_id}.csv"
    try:
        with (directory / json_ref).open("w", encoding="utf-8") as handle:
            json.dump(rows, handle, indent=2, default=str)
        _csv_dump(directory / csv_ref, rows)
    except OSError as exc:  # pragma: no cover - filesystem failure path
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not write dataset artifact",
        ) from exc

    dataset = ResearchDataset(
        id=dataset_id,
        name=data.name.strip(),
        description=data.description,
        kind=data.kind,
        pseudonymized=True,
        row_count=len(rows),
        file_ref=csv_ref,
        created_by=created_by,
        expires_at=expires_at,
    )
    db.add(dataset)
    await db.commit()
    await db.refresh(dataset)
    return ResearchDatasetOut.model_validate(dataset)


async def list_datasets(db: AsyncSession) -> list[ResearchDatasetOut]:
    rows = (
        await db.scalars(select(ResearchDataset).order_by(ResearchDataset.created_at.desc()))
    ).all()
    return [ResearchDatasetOut.model_validate(dataset) for dataset in rows]


async def get_dataset(db: AsyncSession, dataset_id: uuid.UUID) -> ResearchDataset:
    dataset = await db.get(ResearchDataset, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    return dataset


async def ensure_active(dataset: ResearchDataset) -> None:
    if dataset.expires_at is not None and dataset.expires_at < datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=(
                "This dataset has expired and can no longer be downloaded. "
                "Build a fresh export from the research datasets page."
            ),
        )


def dataset_artifact_path(dataset: ResearchDataset) -> Path:
    file_ref = dataset.file_ref
    if not file_ref:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dataset has no artifact"
        )
    return _data_dir() / file_ref


async def delete_dataset(db: AsyncSession, dataset: ResearchDataset) -> None:
    artifact = dataset_artifact_path(dataset)
    if artifact.exists():
        try:
            artifact.unlink()
        except OSError:  # pragma: no cover - filesystem failure path
            pass
    sibling = artifact.with_suffix(".json")
    if sibling.exists():
        try:
            sibling.unlink()  # pragma: no cover - build-scope guard
        except OSError:  # pragma: no cover - filesystem failure path
            pass
    await db.delete(dataset)
    await db.commit()


# --------------------------------------------------------------------------- #
# Research metrics (PRD §71)
# --------------------------------------------------------------------------- #

async def research_metrics(db: AsyncSession) -> ResearchMetricsOut:
    subs = (
        await db.execute(
            select(
                Submission.user_id,
                Submission.challenge_id,
                Submission.is_correct,
                Submission.created_at,
            )
        )
    ).all()
    by_user_attempts: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    by_user_solves: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    solved_by_challenge: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    attempted_by_challenge: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for user_id, challenge_id, is_correct, _created_at in subs:
        by_user_attempts[user_id].add(challenge_id)
        attempted_by_challenge[challenge_id].add(user_id)
        if is_correct:
            by_user_solves[user_id].add(challenge_id)
            solved_by_challenge[challenge_id].add(user_id)

    profiles = (
        await db.execute(
            select(UserSkillProfile.user_id, UserSkillProfile.competency_level)
        )
    ).all()
    competency_by_user: dict[uuid.UUID, list[float]] = defaultdict(list)
    for user_id, competency in profiles:
        competency_by_user[user_id].append(float(competency))
    skill_deltas = [median(v) for v in competency_by_user.values()]

    # Return frequency: consecutive session gaps per user (day granularity).
    days_by_user: dict[uuid.UUID, list[date]] = defaultdict(list)
    for user_id, _, _, created_at in subs:
        if created_at is not None:
            days_by_user[user_id].append(created_at.date())
    gaps: list[int] = []
    for user_id in days_by_user:
        ordered = sorted(set(days_by_user[user_id]))
        for i in range(len(ordered) - 1):
            if ordered[i + 1] > ordered[i]:
                gaps.append((ordered[i + 1] - ordered[i]).days)

    hints_total = int(
        await db.scalar(select(func.count()).select_from(HintReveal)) or 0
    )
    week_ago = datetime.now(UTC) - timedelta(days=7)
    weekly_active = int(
        await db.scalar(
            select(func.count(func.distinct(Submission.user_id))).where(
                Submission.created_at >= week_ago
            )
        )
        or 0
    )

    # Retention: at least one attempt in two distinct calendar weeks.
    weeks_by_user: dict[uuid.UUID, set[tuple[int, int]]] = defaultdict(set)
    for user_id, _, _, created_at in subs:
        if created_at is not None:
            iso = created_at.isocalendar()
            weeks_by_user[user_id].add((iso.year, iso.week))
    retained = sum(1 for weeks in weeks_by_user.values() if len(weeks) >= 2)

    assessed_users = len(by_user_attempts)
    attempted_pairs = sum(len(v) for v in by_user_attempts.values())
    solved_pairs = sum(len(v) for v in by_user_solves.values())

    learning = MetricsLearning(
        assessed_users=assessed_users,
        completion_rate=round(solved_pairs / attempted_pairs, 4) if attempted_pairs else 0.0,
        avg_skill_delta=round(sum(skill_deltas) / len(skill_deltas), 2) if skill_deltas else 0.0,
        retention_rate=round(retained / assessed_users, 4) if assessed_users else 0.0,
        median_days_to_competency=None,
    )

    engagement = MetricsEngagement(
        weekly_active_users=weekly_active,
        challenges_attempted=attempted_pairs,
        hints_used=hints_total,
        median_return_days=round(median(gaps), 1) if gaps else None,
    )

    # Challenge quality table.
    challenges = (
        await db.scalars(select(Challenge).where(Challenge.status == "published"))
    ).all()
    quality: list[ChallengeQualityMetric] = []
    for challenge in challenges:
        attempter_count = len(attempted_by_challenge.get(challenge.id, set()))
        solver_count = len(solved_by_challenge.get(challenge.id, set()))
        quality.append(
            ChallengeQualityMetric(
                challenge_id=challenge.id,
                slug=challenge.slug,
                title=challenge.title,
                success_rate=round(solver_count / attempter_count, 4) if attempter_count else 0.0,
                median_solve_seconds=None,
                abandonment_rate=round(
                    1 - solver_count / attempter_count, 4
                ) if attempter_count else 0.0,
            )
        )

    # Solve time metric (median first-attempt → solve delta per challenge).
    rows = (
        await db.execute(
            select(
                Submission.challenge_id,
                Submission.user_id,
                Submission.created_at,
                Submission.is_correct,
            ).order_by(Submission.created_at.asc())
        )
    ).all()
    solve_deltas: dict[uuid.UUID, list[float]] = defaultdict(list)
    first_attempt: dict[tuple[uuid.UUID, uuid.UUID], datetime] = {}
    for challenge_id, user_id, created_at, is_correct in rows:
        key = (challenge_id, user_id)
        if key not in first_attempt:
            first_attempt[key] = created_at
        if (
            is_correct
            and key in first_attempt
            and first_attempt[key] is not None
            and created_at is not None
        ):
            solve_deltas[challenge_id].append((created_at - first_attempt[key]).total_seconds())
    median_by_challenge = {
        cid: round(median(deltas), 1) for cid, deltas in solve_deltas.items() if deltas
    }
    for metric in quality:
        metric.median_solve_seconds = median_by_challenge.get(metric.challenge_id)

    # Recommendation quality (H1) — aggregate + per-source.
    logs = (
        await db.execute(
            select(
                RecommendationLog.user_id,
                RecommendationLog.challenge_id,
                RecommendationLog.generated_at,
                RecommendationLog.source,
            )
        )
    ).all()
    accepted, solved = _recommendation_quality(
        subs, [(u, c, g) for u, c, g, _s in logs]
    )

    # Per-source breakdown.
    by_source: dict[str, list[tuple]] = defaultdict(list)
    for user_id, challenge_id, generated_at, source in logs:
        by_source[source].append((user_id, challenge_id, generated_at))
    per_source: list[SourceRecommendationMetrics] = []
    for source_key, source_logs in sorted(by_source.items()):
        s_accepted, s_solved = _recommendation_quality(subs, source_logs)
        s_served = len(source_logs)
        per_source.append(
            SourceRecommendationMetrics(
                source=source_key,
                served=s_served,
                accepted=s_accepted,
                solved=s_solved,
                acceptance_rate=round(s_accepted / s_served, 4) if s_served else 0.0,
                completion_rate=round(s_solved / s_served, 4) if s_served else 0.0,
            )
        )

    served = len(logs)
    return ResearchMetricsOut(
        learning=learning,
        engagement=engagement,
        challenge_quality=quality,
        recommendations=MetricsRecommendations(
            served=served,
            accepted=accepted,
            solved=solved,
            acceptance_rate=round(accepted / served, 4) if served else 0.0,
            completion_rate=round(solved / served, 4) if served else 0.0,
            per_source=per_source,
        ),
        generated_at=datetime.now(UTC),
    )


def _recommendation_quality(
    subs: list[tuple[uuid.UUID, uuid.UUID, bool, datetime | None]],
    logs: list[tuple[uuid.UUID, uuid.UUID, datetime | None]],
) -> tuple[int, int]:
    accepted, solved = 0, 0
    for log_user, log_challenge, generated_at in logs:
        if generated_at is None:
            continue
        matched = [
            (is_correct, created_at)
            for user_id, challenge_id, is_correct, created_at in subs
            if user_id == log_user
            and challenge_id == log_challenge
            and created_at is not None
            and created_at >= generated_at
            and (created_at - generated_at) <= timedelta(days=7)
        ]
        if any(is_correct for is_correct, _ in matched):
            solved += 1
        elif matched:
            accepted += 1
    return accepted, solved


# --------------------------------------------------------------------------- #
# Knowledge graph (PRD §72)
# --------------------------------------------------------------------------- #

async def research_graph(db: AsyncSession) -> ResearchGraphOut:
    skills = (await db.scalars(select(Skill))).all()
    challenges = (
        await db.scalars(select(Challenge).where(Challenge.status == "published"))
    ).all()
    skill_ids = {s.id for s in skills}
    challenge_ids = {c.id for c in challenges}

    nodes: dict[str, GraphNode] = {}
    for skill in skills:
        nodes[f"skill:{skill.id}"] = GraphNode(
            id=f"skill:{skill.id}",
            type="skill",
            label=skill.name,
            meta={"slug": skill.slug, "icon": skill.icon},
        )
    for skill in skills:  # ensure ancestor nodes exist even when solved indirectly
        if skill.parent_id and skill.parent_id in skill_ids:
            parent = next(s for s in skills if s.id == skill.parent_id)
            nodes[f"skill:{skill.parent_id}"] = GraphNode(
                id=f"skill:{skill.parent_id}",
                type="skill",
                label=parent.name,
                meta={"slug": parent.slug, "icon": parent.icon},
            )
    for challenge in challenges:
        nodes[f"challenge:{challenge.id}"] = GraphNode(
            id=f"challenge:{challenge.id}",
            type="challenge",
            label=challenge.title,
            meta={
                "slug": challenge.slug,
                "category": challenge.category,
                "difficulty": challenge.difficulty,
                "points": challenge.points,
            },
        )
        nodes[f"category:{challenge.category}"] = GraphNode(
            id=f"category:{challenge.category}",
            type="category",
            label=challenge.category,
            meta={},
        )

    edges: list[GraphEdge] = []

    # challenge -> skill (requires), challenge -> category (in), skill hierarchy.
    links = (
        await db.execute(
            select(ChallengeSkill.challenge_id, ChallengeSkill.skill_id).where(
                ChallengeSkill.challenge_id.in_(challenge_ids)
            )
        )
    ).all()
    for challenge_id, skill_id in links:
        edges.append(
            GraphEdge(
                source=f"challenge:{challenge_id}",
                target=f"skill:{skill_id}",
                relation="requires",
                weight=1.0,
            )
        )
    for challenge in challenges:
        edges.append(
            GraphEdge(
                source=f"challenge:{challenge.id}",
                target=f"category:{challenge.category}",
                relation="in",
                weight=1.0,
            )
        )
    for skill in skills:
        if skill.parent_id and skill.parent_id in skill_ids:
            edges.append(
                GraphEdge(
                    source=f"skill:{skill.parent_id}",
                    target=f"skill:{skill.id}",
                    relation="requires",
                    weight=1.0,
                )
            )

    # Co-solved skill pairs and challenge pairs (users who solved both).
    solved = (
        await db.execute(
            select(Submission.user_id, ChallengeSkill.skill_id)
            .join(ChallengeSkill, ChallengeSkill.challenge_id == Submission.challenge_id)
            .where(Submission.is_correct.is_(True))
        )
    ).all()
    by_user_skills: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for user_id, skill_id in solved:
        by_user_skills[user_id].add(skill_id)
    skill_pair_counts: dict[tuple[str, str], int] = defaultdict(int)
    for user_skills in by_user_skills.values():
        listed = sorted(user_skills)
        for i in range(len(listed)):
            for j in range(i + 1, len(listed)):
                skill_pair_counts[(f"skill:{listed[i]}", f"skill:{listed[j]}")] += 1
    for (source, target), count in sorted(skill_pair_counts.items(), key=lambda kv: -kv[1])[:200]:
        edges.append(
            GraphEdge(
                source=source,
                target=target,
                relation="co_solved",
                weight=float(count),
            )
        )

    solved_challenges = (
        await db.execute(
            select(Submission.user_id, Submission.challenge_id)
            .where(Submission.is_correct.is_(True))
        )
    ).all()
    by_user_challenges: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for user_id, challenge_id in solved_challenges:
        by_user_challenges[user_id].add(challenge_id)
    challenge_pair_counts: dict[tuple[str, str], int] = defaultdict(int)
    for user_challenges in by_user_challenges.values():
        listed = sorted(user_challenges)
        for i in range(len(listed)):
            for j in range(i + 1, len(listed)):
                challenge_pair_counts[(f"challenge:{listed[i]}", f"challenge:{listed[j]}")] += 1
    ranked_challenge_pairs = sorted(
        challenge_pair_counts.items(), key=lambda kv: -kv[1]
    )[:200]
    for (source, target), count in ranked_challenge_pairs:
        edges.append(
            GraphEdge(
                source=source,
                target=target,
                relation="co_solved",
                weight=float(count),
            )
        )

    # Learning path order edges.
    path_steps = (
        await db.execute(
            select(LearningPathStep)
            .order_by(LearningPathStep.learning_path_id, LearningPathStep.step_order)
        )
    ).all()
    ordered: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for (step,) in path_steps:
        ordered[step.learning_path_id].append(step.challenge_id)
    for _path_id, challenge_list in ordered.items():
        for previous, following in zip(challenge_list, challenge_list[1:], strict=False):
            if previous in challenge_ids and following in challenge_ids:
                edges.append(
                    GraphEdge(
                        source=f"challenge:{previous}",
                        target=f"challenge:{following}",
                        relation="step",
                        weight=1.0,
                    )
                )

    return ResearchGraphOut(
        nodes=list(nodes.values()),
        edges=edges,
        generated_at=datetime.now(UTC),
    )


# --------------------------------------------------------------------------- #
# Experiment registry (PRD §72 — offline ML/GNN runs reference these)
# --------------------------------------------------------------------------- #

async def create_experiment(
    db: AsyncSession,
    *,
    name: str,
    model_ref: str,
    description: str | None,
    params: dict | None,
    created_by: uuid.UUID,
) -> ResearchExperimentOut:
    experiment = ResearchExperiment(
        name=name.strip(),
        model_ref=model_ref.strip(),
        description=description,
        params=params,
        status="queued",
        created_by=created_by,
    )
    db.add(experiment)
    await db.commit()
    await db.refresh(experiment)
    return ResearchExperimentOut.model_validate(experiment)


async def list_experiments(db: AsyncSession) -> list[ResearchExperimentOut]:
    rows = (
        await db.scalars(select(ResearchExperiment).order_by(ResearchExperiment.created_at.desc()))
    ).all()
    return [ResearchExperimentOut.model_validate(experiment) for experiment in rows]


async def get_experiment(db: AsyncSession, experiment_id: uuid.UUID) -> ResearchExperiment:
    experiment = await db.get(ResearchExperiment, experiment_id)
    if experiment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Experiment not found")
    return experiment


async def update_experiment(
    db: AsyncSession,
    experiment: ResearchExperiment,
    *,
    status_value: str | None,
    metrics: dict | None,
) -> ResearchExperimentOut:
    if status_value is not None:
        experiment.status = status_value
    if metrics is not None:
        experiment.metrics = metrics
    await db.commit()
    await db.refresh(experiment)
    return ResearchExperimentOut.model_validate(experiment)


async def delete_experiment(db: AsyncSession, experiment: ResearchExperiment) -> None:
    await db.delete(experiment)
    await db.commit()