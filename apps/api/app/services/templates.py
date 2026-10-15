"""Machine template lifecycle and builder service (Phase 3)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.core.config import get_settings
from app.models.machine_templates import MachineTemplate, MachineTemplateVersion
from app.schemas.machine_templates import (
    MachineTemplateApprovalIn,
    MachineTemplateCreate,
    MachineTemplateOut,
    MachineTemplateUpdate,
    MachineTemplateValidationResult,
    MachineTemplateVersionCreate,
    MachineTemplateVersionOut,
)
from app.services.users import record_audit

VALID_OS_TYPES = {"linux", "windows", "freebsd", "custom"}
VALID_ARCHS = {"x86_64", "arm64"}
VALID_STATUS_TRANSITIONS = {
    "draft": {"review", "archived"},
    "review": {"approved", "draft", "archived"},
    "approved": {"published", "draft", "archived"},
    "published": {"archived"},
    "archived": {"draft"},
}


def _template_to_out(
    template: MachineTemplate, version_count: int = 0, latest_version: int | None = None
) -> MachineTemplateOut:
    return MachineTemplateOut(
        id=template.id,
        slug=template.slug,
        title=template.title,
        description=template.description,
        category=template.category,
        difficulty=template.difficulty,
        os_type=template.os_type,
        architecture=template.architecture,
        base_image=template.base_image,
        services=template.services,
        challenge_modules=template.challenge_modules,
        resource_spec=template.resource_spec,
        network_policy=template.network_policy,
        exposure_policy=template.exposure_policy,
        flag_definitions=template.flag_definitions,
        hint_config=template.hint_config,
        max_lease_minutes=template.max_lease_minutes,
        estimated_minutes=template.estimated_minutes,
        tags=template.tags,
        prerequisites=template.prerequisites,
        status=template.status,
        author_id=template.author_id,
        created_at=template.created_at,
        updated_at=template.updated_at,
        version_count=version_count,
        latest_version=latest_version,
    )


def _version_to_out(version: MachineTemplateVersion) -> MachineTemplateVersionOut:
    return MachineTemplateVersionOut(
        id=version.id,
        template_id=version.template_id,
        version=version.version,
        config_snapshot=version.config_snapshot,
        image_ref=version.image_ref,
        image_hash=version.image_hash,
        build_log=version.build_log,
        status=version.status,
        validation_result=version.validation_result,
        validated_at=version.validated_at,
        published_at=version.published_at,
        created_by=version.created_by,
        created_at=version.created_at,
    )


async def list_templates(
    db: AsyncSession,
    *,
    status_filter: str | None = None,
    category: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[MachineTemplateOut], int]:
    stmt = select(MachineTemplate)
    count_stmt = select(func.count()).select_from(MachineTemplate)
    if status_filter:
        stmt = stmt.where(MachineTemplate.status == status_filter)
        count_stmt = count_stmt.where(MachineTemplate.status == status_filter)
    if category:
        stmt = stmt.where(MachineTemplate.category == category)
        count_stmt = count_stmt.where(MachineTemplate.category == category)

    total = int(await db.scalar(count_stmt) or 0)
    rows = (
        await db.scalars(
            stmt.order_by(MachineTemplate.updated_at.desc()).limit(limit).offset(offset)
        )
    ).all()

    out: list[MachineTemplateOut] = []
    for t in rows:
        # Get version stats
        v_count = int(
            await db.scalar(
                select(func.count())
                .select_from(MachineTemplateVersion)
                .where(MachineTemplateVersion.template_id == t.id)
            )
            or 0
        )
        latest_v = await db.scalar(
            select(func.max(MachineTemplateVersion.version)).where(
                MachineTemplateVersion.template_id == t.id
            )
        )
        out.append(_template_to_out(t, version_count=v_count, latest_version=latest_v))
    return out, total


async def get_template_by_id_or_slug(db: AsyncSession, identifier: str) -> MachineTemplate:
    template = None
    try:
        t_uuid = uuid.UUID(identifier)
        template = await db.get(MachineTemplate, t_uuid)
    except ValueError:
        template = (
            await db.scalars(select(MachineTemplate).where(MachineTemplate.slug == identifier))
        ).first()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Machine template not found"
        )
    return template


async def create_template(
    db: AsyncSession, user: CurrentUser, payload: MachineTemplateCreate
) -> MachineTemplateOut:
    existing = (
        await db.scalars(select(MachineTemplate).where(MachineTemplate.slug == payload.slug))
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Template with slug '{payload.slug}' already exists",
        )

    template = MachineTemplate(
        slug=payload.slug,
        title=payload.title,
        description=payload.description,
        category=payload.category,
        difficulty=payload.difficulty,
        os_type=payload.os_type,
        architecture=payload.architecture,
        base_image=payload.base_image,
        services=payload.services,
        challenge_modules=payload.challenge_modules,
        resource_spec=payload.resource_spec,
        network_policy=payload.network_policy,
        exposure_policy=payload.exposure_policy,
        flag_definitions=payload.flag_definitions,
        hint_config=payload.hint_config,
        max_lease_minutes=payload.max_lease_minutes,
        estimated_minutes=payload.estimated_minutes,
        tags=payload.tags,
        prerequisites=payload.prerequisites,
        status="draft",
        author_id=user.id,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    await record_audit(db, event="template.create", user_id=user.id, target_id=template.slug)
    return _template_to_out(template)


async def update_template(
    db: AsyncSession, user: CurrentUser, template: MachineTemplate, payload: MachineTemplateUpdate
) -> MachineTemplateOut:
    data = payload.model_dump(exclude_unset=True)
    for field, val in data.items():
        setattr(template, field, val)
    template.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(template)
    await record_audit(db, event="template.update", user_id=user.id, target_id=template.slug)
    return _template_to_out(template)


async def delete_template(db: AsyncSession, user: CurrentUser, template: MachineTemplate) -> None:
    await db.delete(template)
    await db.commit()
    await record_audit(db, event="template.delete", user_id=user.id, target_id=template.slug)


def validate_template_spec(template: MachineTemplate) -> MachineTemplateValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, bool] = {}

    # Check OS & Arch
    checks["os_supported"] = template.os_type in VALID_OS_TYPES
    if not checks["os_supported"]:
        errors.append(f"Invalid os_type '{template.os_type}'. Supported: {VALID_OS_TYPES}")

    checks["arch_supported"] = template.architecture in VALID_ARCHS
    if not checks["arch_supported"]:
        errors.append(f"Invalid architecture '{template.architecture}'. Supported: {VALID_ARCHS}")

    # Check Base Image
    checks["base_image_specified"] = bool(template.base_image and template.base_image.strip())
    if not checks["base_image_specified"]:
        errors.append("base_image must not be empty")

    # Resource caps
    settings = get_settings()
    res = template.resource_spec or {}
    cpu = res.get("cpu", 1.0)
    mem = res.get("memory_mb", 512)
    max_cpu = max(4.0, settings.lab_cpu_limit * 4)
    max_mem = max(4096, settings.lab_memory_limit_mb * 4)
    checks["resources_within_bounds"] = cpu <= max_cpu and mem <= max_mem
    if not checks["resources_within_bounds"]:
        warnings.append(
            f"Resource spec ({cpu} CPU, {mem}MB RAM) is high; verify hypervisor headroom"
        )

    # Network exposure
    checks["exposure_policy_valid"] = template.exposure_policy in (
        "vpn_only",
        "internal",
        "restricted_public",
    )
    if not checks["exposure_policy_valid"]:
        errors.append(f"Unknown exposure policy '{template.exposure_policy}'")

    is_valid = len(errors) == 0
    return MachineTemplateValidationResult(
        is_valid=is_valid, errors=errors, warnings=warnings, checks=checks
    )


async def workflow_transition(
    db: AsyncSession,
    user: CurrentUser,
    template: MachineTemplate,
    payload: MachineTemplateApprovalIn,
) -> MachineTemplateOut:
    target_status = {
        "submit_review": "review",
        "approve": "approved",
        "publish": "published",
        "archive": "archived",
    }.get(payload.action, payload.action)

    allowed = VALID_STATUS_TRANSITIONS.get(template.status, set())
    if target_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot transition template from '{template.status}' to '{target_status}'. "
                f"Allowed: {allowed}"
            ),
        )

    # If publishing, ensure validation passes
    if target_status == "published":
        val = validate_template_spec(template)
        if not val.is_valid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Cannot publish template with validation errors: {val.errors}",
            )

    template.status = target_status
    template.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(template)
    await record_audit(
        db,
        event=f"template.workflow.{payload.action}",
        user_id=user.id,
        target_id=template.slug,
    )
    return _template_to_out(template)


async def create_template_version(
    db: AsyncSession,
    user: CurrentUser,
    template: MachineTemplate,
    payload: MachineTemplateVersionCreate,
) -> MachineTemplateVersionOut:
    # Get next version number
    current_max = await db.scalar(
        select(func.max(MachineTemplateVersion.version)).where(
            MachineTemplateVersion.template_id == template.id
        )
    )
    next_ver = (current_max or 0) + 1

    # Freeze snapshot
    snapshot = {
        "slug": template.slug,
        "title": template.title,
        "base_image": payload.image_ref or template.base_image,
        "os_type": template.os_type,
        "architecture": template.architecture,
        "services": template.services,
        "challenge_modules": template.challenge_modules,
        "resource_spec": template.resource_spec,
        "network_policy": template.network_policy,
        "exposure_policy": template.exposure_policy,
        "flag_definitions": template.flag_definitions,
        "hint_config": template.hint_config,
        **(payload.config_overrides or {}),
    }

    # Validate snapshot
    val = validate_template_spec(template)
    version = MachineTemplateVersion(
        template_id=template.id,
        version=next_ver,
        config_snapshot=snapshot,
        image_ref=payload.image_ref or template.base_image,
        status="validated" if val.is_valid else "building",
        validation_result=val.model_dump(),
        validated_at=datetime.now(UTC) if val.is_valid else None,
        created_by=user.id,
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)
    await record_audit(
        db,
        event="template.version.create",
        user_id=user.id,
        target_id=f"{template.slug}:v{next_ver}",
    )
    return _version_to_out(version)


async def list_template_versions(
    db: AsyncSession, template_id: uuid.UUID
) -> list[MachineTemplateVersionOut]:
    rows = (
        await db.scalars(
            select(MachineTemplateVersion)
            .where(MachineTemplateVersion.template_id == template_id)
            .order_by(MachineTemplateVersion.version.desc())
        )
    ).all()
    return [_version_to_out(v) for v in rows]
