"""Machine template builder and administration API endpoints (Phase 3)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_permission
from app.db.session import get_db
from app.schemas.machine_templates import (
    MachineTemplateApprovalIn,
    MachineTemplateCreate,
    MachineTemplateOut,
    MachineTemplateUpdate,
    MachineTemplateValidationResult,
    MachineTemplateVersionCreate,
    MachineTemplateVersionOut,
)
from app.services import templates as template_service

router = APIRouter(tags=["templates"])


@router.get("/templates", response_model=list[MachineTemplateOut])
async def list_published_templates(
    db: Annotated[AsyncSession, Depends(get_db)],
    category: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List published machine templates available for challenge authors and students."""
    items, _ = await template_service.list_templates(
        db, status_filter="published", category=category, limit=limit, offset=offset
    )
    return items


@router.get("/admin/templates", response_model=list[MachineTemplateOut])
async def admin_list_templates(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.edit"))],
    status_filter: str | None = None,
    category: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List all machine templates across all statuses (admin/faculty only)."""
    items, _ = await template_service.list_templates(
        db, status_filter=status_filter, category=category, limit=limit, offset=offset
    )
    return items


@router.post(
    "/admin/templates",
    response_model=MachineTemplateOut,
    status_code=status.HTTP_201_CREATED,
)
async def admin_create_template(
    payload: MachineTemplateCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.edit"))],
):
    """Create a new machine template definition."""
    return await template_service.create_template(db, user, payload)


@router.get("/admin/templates/{identifier}", response_model=MachineTemplateOut)
async def admin_get_template(
    identifier: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.edit"))],
):
    """Get machine template details by UUID or slug."""
    template = await template_service.get_template_by_id_or_slug(db, identifier)
    return template_service._template_to_out(template)


@router.put("/admin/templates/{identifier}", response_model=MachineTemplateOut)
async def admin_update_template(
    identifier: str,
    payload: MachineTemplateUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.edit"))],
):
    """Update machine template specification."""
    template = await template_service.get_template_by_id_or_slug(db, identifier)
    return await template_service.update_template(db, user, template, payload)


@router.delete("/admin/templates/{identifier}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_template(
    identifier: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.edit"))],
):
    """Delete a machine template."""
    template = await template_service.get_template_by_id_or_slug(db, identifier)
    await template_service.delete_template(db, user, template)


@router.post(
    "/admin/templates/{identifier}/validate",
    response_model=MachineTemplateValidationResult,
)
async def admin_validate_template(
    identifier: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.edit"))],
):
    """Validate template specifications and configuration before versioning."""
    template = await template_service.get_template_by_id_or_slug(db, identifier)
    return template_service.validate_template_spec(template)


@router.post(
    "/admin/templates/{identifier}/workflow",
    response_model=MachineTemplateOut,
)
async def admin_template_workflow(
    identifier: str,
    payload: MachineTemplateApprovalIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.edit"))],
):
    """Execute approval workflow transition (submit_review, approve, publish, archive)."""
    template = await template_service.get_template_by_id_or_slug(db, identifier)
    return await template_service.workflow_transition(db, user, template, payload)


@router.post(
    "/admin/templates/{identifier}/versions",
    response_model=MachineTemplateVersionOut,
    status_code=status.HTTP_201_CREATED,
)
async def admin_create_template_version(
    identifier: str,
    payload: MachineTemplateVersionCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.edit"))],
):
    """Create an immutable snapshot version of the machine template."""
    template = await template_service.get_template_by_id_or_slug(db, identifier)
    return await template_service.create_template_version(db, user, template, payload)


@router.get(
    "/admin/templates/{identifier}/versions",
    response_model=list[MachineTemplateVersionOut],
)
async def admin_list_template_versions(
    identifier: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("challenge.edit"))],
):
    """List all version snapshots of a machine template."""
    template = await template_service.get_template_by_id_or_slug(db, identifier)
    return await template_service.list_template_versions(db, template.id)
