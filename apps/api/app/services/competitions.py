"""Competition lifecycle, registration and leaderboard service (Phase 3, PRD §24).

Server owns the state machine: the frontend only sends intent (an ``action``),
never an arbitrary status (PRD §40 "competition status sent by frontend").
Scoring is derived from the shared submissions table scoped to the
competition's challenges, participants and time window.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.challenges import Challenge
from app.models.competitions import (
    Competition,
    CompetitionChallenge,
    CompetitionParticipant,
    Team,
    TeamMember,
)
from app.models.submissions import Submission
from app.models.users import User
from app.schemas.competition import (
    ChallengeShot,
    CompetitionChallengeOut,
    CompetitionCreate,
    CompetitionLeaderboardEntry,
    CompetitionOut,
    CompetitionSummary,
    CompetitionUpdate,
    ParticipantSelf,
    TeamOut,
)
from app.services.users import record_audit

REGISTRATION_OPEN = {"registration", "scheduled"}
CHALLENGES_EDITABLE = {"draft", "registration"}
TRANSITIONS = {
    "start_registration": ("draft", "registration"),
    "schedule": ("registration", "scheduled"),
    "start": ("scheduled", "live"),
    "finish": ("live", "finished"),
    "archive": ("finished", "archived"),
}


async def list_competitions(
    db: AsyncSession, *, filter_status: str | None = None
) -> list[CompetitionSummary]:
    conditions = []
    if filter_status:
        conditions.append(Competition.status == filter_status)

    competitions = (
        await db.scalars(
            select(Competition)
            .where(*conditions)
            .order_by(Competition.created_at.desc())
        )
    ).all()
    out: list[CompetitionSummary] = []
    for comp in competitions:
        out.append(await _to_summary(db, comp))
    return out


async def get_competition(
    db: AsyncSession,
    competition: Competition,
    user: User | None = None,
    *,
    include_rules: bool = False,
) -> CompetitionOut:
    return await _to_out(db, competition, user=user, include_rules=include_rules)


async def create_competition(
    db: AsyncSession,
    data: CompetitionCreate,
    user: User,
    request: Request | None = None,
) -> CompetitionOut:
    base = _slugify(data.title)
    slug = base
    if await db.scalar(select(Competition).where(Competition.slug == slug)):
        slug = f"{base}-{uuid.uuid4().hex[:6]}"
    competition = Competition(
        slug=slug,
        title=data.title,
        description=data.description,
        rules=data.rules,
        start_at=data.start_at,
        end_at=data.end_at,
        registration_ends_at=data.registration_ends_at,
        allow_teams=data.allow_teams,
        max_team_size=data.max_team_size,
        scoring_mode=data.scoring_mode,
        status="draft",
        created_by=user.id,
    )
    db.add(competition)
    await db.commit()
    await db.refresh(competition)
    await record_audit(
        db,
        event="competition.create",
        user_id=user.id,
        target_id=competition.slug,
        request=request,
    )
    return await _to_out(db, competition, user=user)


async def update_competition(
    db: AsyncSession,
    competition: Competition,
    data: CompetitionUpdate,
    user: User,
    request: Request | None = None,
) -> CompetitionOut:
    if competition.status not in ("draft", "registration", "scheduled"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Competition is already live or finished — fields are locked.",
        )
    updates = data.model_dump(exclude_unset=True)
    start_at, end_at = updates.get("start_at"), updates.get("end_at")
    if start_at and end_at and start_at >= end_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_at must be before end_at",
        )
    for field, value in updates.items():
        setattr(competition, field, value)
    await db.commit()
    await db.refresh(competition)
    await record_audit(
        db,
        event="competition.update",
        user_id=user.id,
        target_id=competition.slug,
        request=request,
    )
    return await _to_out(db, competition, user=user)


async def transition(
    db: AsyncSession,
    competition: Competition,
    action: str,
    user: User,
    request: Request | None = None,
) -> CompetitionOut:
    allowed = TRANSITIONS.get(action)
    if allowed is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown transition")
    from_status, to_status = allowed
    if competition.status != from_status:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot {action}: competition is '{competition.status}', "
                f"expected '{from_status}'."
            ),
        )
    now = datetime.now(UTC)
    starts = competition.start_at
    if action == "start" and starts and starts.replace(tzinfo=UTC) > now + timedelta(minutes=5):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Competition cannot start before its scheduled start time.",
        )
    if action == "schedule" and not (competition.start_at and competition.end_at):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Set start_at and end_at before scheduling.",
        )
    if action == "finish" and competition.end_at and competition.end_at.replace(tzinfo=UTC) > now:
        # Allowed: organizer may finish early, but be explicit about it.
        pass
    competition.status = to_status
    await db.commit()
    await db.refresh(competition)
    await record_audit(
        db,
        event="competition.transition",
        user_id=user.id,
        target_id=competition.slug,
        details={"action": action, "from": from_status, "to": to_status},
        request=request,
    )
    return await _to_out(db, competition, user=user)


async def add_challenge(
    db: AsyncSession,
    competition: Competition,
    challenge_id: uuid.UUID,
    points: int | None,
    user: User,
    request: Request | None = None,
) -> CompetitionOut:
    _ensure_editable(competition)
    challenge = await db.get(Challenge, challenge_id)
    if challenge is None or not challenge.is_published:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not found")
    existing = await db.scalar(
        select(CompetitionChallenge).where(
            CompetitionChallenge.competition_id == competition.id,
            CompetitionChallenge.challenge_id == challenge_id,
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Challenge already in competition",
        )
    max_pos = int(
        await db.scalar(
            select(func.coalesce(func.max(CompetitionChallenge.position), -1)).where(
                CompetitionChallenge.competition_id == competition.id
            )
        )
        or 0
    )
    db.add(
        CompetitionChallenge(
            competition_id=competition.id,
            challenge_id=challenge_id,
            points=points if competition.scoring_mode == "override" else None,
            position=max_pos + 1,
        )
    )
    await db.commit()
    await record_audit(
        db,
        event="competition.challenge_add",
        user_id=user.id,
        target_id=str(challenge_id),
        details={"competition": competition.slug},
        request=request,
    )
    return await _to_out(db, competition, user=user)


async def remove_challenge(
    db: AsyncSession,
    competition: Competition,
    challenge_id: uuid.UUID,
    user: User,
    request: Request | None = None,
) -> CompetitionOut:
    _ensure_editable(competition)
    await db.execute(
        delete(CompetitionChallenge).where(
            CompetitionChallenge.competition_id == competition.id,
            CompetitionChallenge.challenge_id == challenge_id,
        )
    )
    await db.commit()
    await record_audit(
        db,
        event="competition.challenge_remove",
        user_id=user.id,
        target_id=str(challenge_id),
        details={"competition": competition.slug},
        request=request,
    )
    return await _to_out(db, competition, user=user)


async def register(
    db: AsyncSession,
    competition: Competition,
    user: User,
    request: Request | None = None,
) -> CompetitionOut:
    _ensure_registration_open(competition)
    existing = await db.scalar(
        select(CompetitionParticipant).where(
            CompetitionParticipant.competition_id == competition.id,
            CompetitionParticipant.user_id == user.id,
        )
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already registered")
    db.add(CompetitionParticipant(competition_id=competition.id, user_id=user.id, team_id=None))
    await db.commit()
    await record_audit(
        db,
        event="competition.register",
        user_id=user.id,
        target_id=competition.slug,
        request=request,
    )
    return await _to_out(db, competition, user=user)


async def create_team(
    db: AsyncSession,
    competition: Competition,
    name: str,
    user: User,
    request: Request | None = None,
) -> CompetitionOut:
    _ensure_registration_open(competition)
    if not competition.allow_teams:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Teams are not enabled for this competition.",
        )
    participant = await _participant(db, competition.id, user.id)
    if participant is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Register for the competition before creating a team.",
        )
    team = Team(competition_id=competition.id, name=name.strip(), created_by=user.id)
    db.add(team)
    await db.flush()
    db.add(TeamMember(team_id=team.id, user_id=user.id, role="captain"))
    participant.team_id = team.id
    await db.commit()
    await record_audit(
        db,
        event="team.create",
        user_id=user.id,
        target_id=team.name,
        details={"competition": competition.slug},
        request=request,
    )
    return await _to_out(db, competition, user=user)


async def join_team(
    db: AsyncSession,
    competition: Competition,
    team_id: uuid.UUID,
    user: User,
    request: Request | None = None,
) -> CompetitionOut:
    _ensure_registration_open(competition)
    if not competition.allow_teams:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Teams are not enabled for this competition.",
        )
    team = await db.get(Team, team_id)
    if team is None or team.competition_id != competition.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    participant = await _participant(db, competition.id, user.id)
    if participant is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Register for the competition before joining a team.",
        )
    if participant.team_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You are already on a team in this competition.",
        )
    member_count = int(
        await db.scalar(
            select(func.count()).select_from(TeamMember).where(TeamMember.team_id == team.id)
        )
        or 0
    )
    if member_count >= competition.max_team_size:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Team is full (max {competition.max_team_size}).",
        )
    participant.team_id = team.id
    db.add(TeamMember(team_id=team.id, user_id=user.id, role="member"))
    await db.commit()
    await record_audit(
        db,
        event="team.join",
        user_id=user.id,
        target_id=team.name,
        details={"competition": competition.slug},
        request=request,
    )
    return await _to_out(db, competition, user=user)


async def freeze(
    db: AsyncSession,
    competition: Competition,
    user: User,
    *,
    frozen: bool,
    request: Request | None = None,
) -> CompetitionOut:
    competition.freeze_leaderboard = frozen
    competition.frozen_at = datetime.now(UTC) if frozen else None
    await db.commit()
    await db.refresh(competition)
    await record_audit(
        db,
        event="competition.freeze" if frozen else "competition.unfreeze",
        user_id=user.id,
        target_id=competition.slug,
        request=request,
    )
    return await _to_out(db, competition, user=user)


async def leaderboard(
    db: AsyncSession,
    competition: Competition,
    *,
    limit: int = 50,
) -> list[CompetitionLeaderboardEntry]:
    """Scoreboard derived from correct submissions scoped to the competition.

    A participant on a team contributes to the team's score; individuals are
    ranked directly. When the leaderboard is frozen, scoring stops at the
    freeze timestamp.
    """
    cutoff = competition.frozen_at if competition.freeze_leaderboard else None
    start = competition.start_at

    challenge_ids = set(
        (
            await db.scalars(
                select(CompetitionChallenge.challenge_id).where(
                    CompetitionChallenge.competition_id == competition.id
                )
            )
        ).all()
    )
    if not challenge_ids:
        return []

    participants = (
        await db.execute(
            select(
                CompetitionParticipant.user_id,
                CompetitionParticipant.team_id,
            ).where(CompetitionParticipant.competition_id == competition.id)
        )
    ).all()
    entity_of_user: dict[uuid.UUID, tuple[str, uuid.UUID]] = {}
    team_ids: set[uuid.UUID] = set()
    for user_id, team_id in participants:
        if team_id is not None:
            entity_of_user[user_id] = ("team", team_id)
            team_ids.add(team_id)
        else:
            entity_of_user[user_id] = ("user", user_id)

    if not entity_of_user:
        return []

    user_ids = list(entity_of_user.keys())
    solves = (
        await db.execute(
            select(
                Submission.user_id,
                Submission.earned_points,
                Submission.created_at,
            )
            .where(
                Submission.is_correct.is_(True),
                Submission.challenge_id.in_(challenge_ids),
                Submission.user_id.in_(user_ids),
                *( [Submission.created_at >= start.replace(tzinfo=UTC)] if start else [] ),
                *( [Submission.created_at <= cutoff.replace(tzinfo=UTC)] if cutoff else [] ),
            )
            .order_by(Submission.created_at.asc())
        )
    ).all()

    scores: dict[uuid.UUID, dict] = {}
    for user_id, points, created_at in solves:
        entity_type, entity_id = entity_of_user[user_id]
        entry = scores.setdefault(
            entity_id,
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "display_name": "",
                "points": 0,
                "solved_count": 0,
                "last_solve_at": None,
                "rank": 0,
            },
        )
        entry["points"] += int(points or 0)
        entry["solved_count"] += 1
        entry["last_solve_at"] = max(
            entry["last_solve_at"], created_at
        ) if entry["last_solve_at"] else created_at

    if team_ids:
        team_names = dict(
            (await db.execute(select(Team.id, Team.name).where(Team.id.in_(team_ids)))).all()
        )
    else:
        team_names = {}
    user_names = dict(
        (
            await db.execute(
                select(User.id, User.display_name).where(User.id.in_(user_ids))
            )
        ).all()
    )

    ranked: list[CompetitionLeaderboardEntry] = []
    for entity_id, entry in scores.items():
        entry["display_name"] = (
            team_names.get(entity_id)
            if entry["entity_type"] == "team"
            else user_names.get(entity_id) or "Anonymous"
        )
        ranked.append(CompetitionLeaderboardEntry(**entry))
    ranked.sort(key=lambda e: (-e.points, e.last_solve_at or datetime.max.replace(tzinfo=UTC)))
    for index, entry in enumerate(ranked, start=1):
        entry.rank = index
    return ranked[:limit]


async def unregister(
    db: AsyncSession,
    competition: Competition,
    user: User,
    request: Request | None = None,
) -> CompetitionOut:
    participant = await _participant(db, competition.id, user.id)
    if participant is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Not registered")
    await db.execute(
        delete(CompetitionParticipant).where(
            CompetitionParticipant.competition_id == competition.id,
            CompetitionParticipant.user_id == user.id,
        )
    )
    await db.execute(
        delete(TeamMember).where(
            TeamMember.team_id == participant.team_id,
            TeamMember.user_id == user.id,
        )
    )
    await db.commit()
    await record_audit(
        db,
        event="competition.unregister",
        user_id=user.id,
        target_id=competition.slug,
        request=request,
    )
    return await _to_out(db, competition, user=user)


# ---------------------------------------------------------------- internals

def _slugify(title: str) -> str:
    value = "".join(c if c.isalnum() else "-" for c in title.lower()).strip("-")
    return (value or "competition")[:120]


def _ensure_editable(competition: Competition) -> None:
    if competition.status not in CHALLENGES_EDITABLE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Challenge set is locked once competition leaves registration.",
        )


def _ensure_registration_open(competition: Competition) -> None:
    if competition.status not in REGISTRATION_OPEN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Registration is not open (status '{competition.status}').",
        )


async def _participant(
    db: AsyncSession, competition_id: uuid.UUID, user_id: uuid.UUID
) -> CompetitionParticipant | None:
    return await db.scalar(
        select(CompetitionParticipant).where(
            CompetitionParticipant.competition_id == competition_id,
            CompetitionParticipant.user_id == user_id,
        )
    )


async def _to_summary(db: AsyncSession, competition: Competition) -> CompetitionSummary:
    challenge_count = int(
        await db.scalar(
            select(func.count()).select_from(CompetitionChallenge).where(
                CompetitionChallenge.competition_id == competition.id
            )
        )
        or 0
    )
    participant_count = int(
        await db.scalar(
            select(func.count()).select_from(CompetitionParticipant).where(
                CompetitionParticipant.competition_id == competition.id
            )
        )
        or 0
    )
    return CompetitionSummary(
        id=competition.id,
        slug=competition.slug,
        title=competition.title,
        description=competition.description,
        status=competition.status,
        start_at=competition.start_at,
        end_at=competition.end_at,
        registration_ends_at=competition.registration_ends_at,
        allow_teams=competition.allow_teams,
        max_team_size=competition.max_team_size,
        scoring_mode=competition.scoring_mode,
        freeze_leaderboard=competition.freeze_leaderboard,
        frozen_at=competition.frozen_at,
        challenge_count=challenge_count,
        participant_count=participant_count,
        created_at=competition.created_at,
        updated_at=competition.updated_at,
    )


async def _to_out(
    db: AsyncSession,
    competition: Competition,
    *,
    user: User | None = None,
    include_rules: bool = False,
) -> CompetitionOut:
    summary = await _to_summary(db, competition)
    rows = (
        await db.execute(
            select(CompetitionChallenge, Challenge)
            .join(Challenge, Challenge.id == CompetitionChallenge.challenge_id)
            .where(CompetitionChallenge.competition_id == competition.id)
            .order_by(CompetitionChallenge.position.asc())
        )
    ).all()
    challenges = [
        CompetitionChallengeOut(
            challenge=ChallengeShot(
                id=ch.id,
                slug=ch.slug,
                title=ch.title,
                category=ch.category,
                difficulty=ch.difficulty,
                points=ch.points,
                environment_type=ch.environment_type,
            ),
            position=cc.position,
            points=cc.points,
        )
        for cc, ch in rows
    ]
    team_count = int(
        await db.scalar(
            select(func.count()).select_from(Team).where(Team.competition_id == competition.id)
        )
        or 0
    )

    me: ParticipantSelf | None = None
    if user is not None:
        participant = await _participant(db, competition.id, user.id)
        if participant is not None:
            me = ParticipantSelf(registered=True)
            if participant.team_id is not None:
                team = await db.get(Team, participant.team_id)
                membership = await db.scalar(
                    select(TeamMember.role).where(
                        TeamMember.team_id == participant.team_id,
                        TeamMember.user_id == user.id,
                    )
                )
                if team:
                    members = (
                        (
                            await db.execute(
                                select(User.display_name).join(
                                    TeamMember, TeamMember.user_id == User.id
                                ).where(TeamMember.team_id == team.id)
                            )
                        )
                        .scalars()
                        .all()
                    )
                    me.entity_type = "team"
                    me.entity_id = team.id
                    me.entity_name = team.name
                    me.team = TeamOut(
                        id=team.id,
                        competition_id=team.competition_id,
                        name=team.name,
                        role=membership or "member",
                        member_count=len(members),
                        members=[m for m in members if m],
                    )
            else:
                me.entity_type = "user"
                me.entity_id = user.id
                me.entity_name = user.display_name

    return CompetitionOut(
        **summary.model_dump(),
        rules=competition.rules if include_rules else None,
        team_count=team_count,
        challenges=challenges,
        me=me,
    )