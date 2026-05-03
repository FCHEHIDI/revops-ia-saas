"""Playbook HTTP routers.

Public router  (``/api/v1/playbooks``, JWT auth)
-------------------------------------------------
- POST /           — create playbook
- GET  /           — list playbooks
- GET  /{id}       — get one playbook
- PATCH /{id}      — partial update
- DELETE /{id}     — delete
- GET  /{id}/runs  — run history
- POST /{id}/trigger — manually trigger

Internal router (``/internal/v1/playbooks``, BYPASS_PATHS — no middleware JWT)
-------------------------------------------------------------------------------
- GET  /         — list active playbooks (for mcp-crm)
- POST /trigger  — run a specific playbook by id (for mcp-crm)
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from app.auth.dependencies import get_current_active_user
from app.common.db import get_db
from app.models.playbook import Playbook
from app.models.user import User
from app.playbooks import service as svc
from app.playbooks.schemas import (
    InternalTriggerRequest,
    PlaybookCreate,
    PlaybookRead,
    PlaybookRunRead,
    PlaybookUpdate,
    TriggerRequest,
)

logger = logging.getLogger(__name__)

# Public (JWT) router
router = APIRouter()
# Internal (BYPASS_PATHS) router
internal_router = APIRouter()


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/",
    response_model=PlaybookRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a playbook",
)
async def create_playbook(
    body: PlaybookCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> PlaybookRead:
    """Create a new automation playbook for the current tenant.

    Args:
        body: Playbook definition.
        current_user: Authenticated user.
        db: Database session.

    Returns:
        Created PlaybookRead.
    """
    playbook = await svc.create_playbook(db, current_user.tenant_id, body)
    return PlaybookRead.model_validate(playbook)


@router.get(
    "/",
    response_model=list[PlaybookRead],
    summary="List playbooks",
)
async def list_playbooks(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[PlaybookRead]:
    """Return a paginated list of playbooks for the current tenant.

    Args:
        page: Page number (1-based).
        limit: Page size (1–100).
        current_user: Authenticated user.
        db: Database session.

    Returns:
        List of PlaybookRead.
    """
    items, _ = await svc.list_playbooks(db, current_user.tenant_id, page=page, limit=limit)
    return [PlaybookRead.model_validate(p) for p in items]


@router.get(
    "/{playbook_id}",
    response_model=PlaybookRead,
    summary="Get a playbook",
)
async def get_playbook(
    playbook_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> PlaybookRead:
    """Retrieve a single playbook by id.

    Args:
        playbook_id: Target playbook UUID.
        current_user: Authenticated user.
        db: Database session.

    Returns:
        PlaybookRead.

    Raises:
        HTTPException: 404 if not found.
    """
    playbook = await svc.get_playbook(db, playbook_id, current_user.tenant_id)
    if playbook is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playbook not found")
    return PlaybookRead.model_validate(playbook)


@router.patch(
    "/{playbook_id}",
    response_model=PlaybookRead,
    summary="Update a playbook",
)
async def update_playbook(
    playbook_id: UUID,
    body: PlaybookUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> PlaybookRead:
    """Partially update a playbook (PATCH semantics — null fields are skipped).

    Args:
        playbook_id: Target playbook UUID.
        body: Fields to update.
        current_user: Authenticated user.
        db: Database session.

    Returns:
        Updated PlaybookRead.

    Raises:
        HTTPException: 404 if not found.
    """
    playbook = await svc.update_playbook(db, playbook_id, current_user.tenant_id, body)
    if playbook is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playbook not found")
    return PlaybookRead.model_validate(playbook)


@router.delete(
    "/{playbook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a playbook",
)
async def delete_playbook(
    playbook_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a playbook and its run history (cascade).

    Args:
        playbook_id: Target playbook UUID.
        current_user: Authenticated user.
        db: Database session.

    Raises:
        HTTPException: 404 if not found.
    """
    deleted = await svc.delete_playbook(db, playbook_id, current_user.tenant_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playbook not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{playbook_id}/runs",
    response_model=list[PlaybookRunRead],
    summary="List playbook run history",
)
async def list_runs(
    playbook_id: UUID,
    limit: int = Query(default=20, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[PlaybookRunRead]:
    """Return the most recent runs for a playbook.

    Args:
        playbook_id: Target playbook UUID.
        limit: Max runs to return (1–200).
        current_user: Authenticated user.
        db: Database session.

    Returns:
        List of PlaybookRunRead newest-first.
    """
    runs = await svc.list_runs(db, playbook_id, current_user.tenant_id, limit=limit)
    return [PlaybookRunRead.model_validate(r) for r in runs]


@router.post(
    "/{playbook_id}/trigger",
    response_model=PlaybookRunRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Manually trigger a playbook",
)
async def trigger_playbook(
    playbook_id: UUID,
    body: TriggerRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> PlaybookRunRead:
    """Trigger a playbook execution outside of the normal event flow.

    Args:
        playbook_id: Target playbook UUID.
        body: Optional entity context and payload overrides.
        current_user: Authenticated user.
        db: Database session.

    Returns:
        PlaybookRunRead for the execution just created.

    Raises:
        HTTPException: 404 if playbook not found.
    """
    playbook = await svc.get_playbook(db, playbook_id, current_user.tenant_id)
    if playbook is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playbook not found")

    event: dict = {
        "event": "manual",
        "tenant_id": str(playbook.tenant_id),
        "entity_type": body.entity_type,
        "entity_id": str(body.entity_id) if body.entity_id else None,
        "payload": body.event_payload,
    }
    run = await svc.run_playbook(db, playbook, event)
    return PlaybookRunRead.model_validate(run)


# ---------------------------------------------------------------------------
# Internal endpoints (used by mcp-crm via X-Internal-API-Key)
# ---------------------------------------------------------------------------


@internal_router.get(
    "/",
    response_model=list[PlaybookRead],
    summary="List active playbooks (internal)",
)
async def internal_list_playbooks(
    tenant_id: UUID = Query(..., alias="tenant_id"),
    db: AsyncSession = Depends(get_db),
) -> list[PlaybookRead]:
    """Return all active playbooks for *tenant_id* (for mcp-crm tooling).

    Args:
        tenant_id: Target tenant UUID (query param).
        db: Database session.

    Returns:
        List of active PlaybookRead.
    """
    items, _ = await svc.list_playbooks(db, tenant_id, active_only=True, limit=100)
    return [PlaybookRead.model_validate(p) for p in items]


@internal_router.post(
    "/trigger",
    response_model=PlaybookRunRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a playbook by id (internal)",
)
async def internal_trigger_playbook(
    body: InternalTriggerRequest,
    db: AsyncSession = Depends(get_db),
) -> PlaybookRunRead:
    """Run a specific playbook immediately (bypasses condition checks).

    Called by mcp-crm when an AI agent decides to trigger a playbook.

    Args:
        body: Trigger payload with playbook_id and optional entity context.
        db: Database session.

    Returns:
        PlaybookRunRead for the execution just created.

    Raises:
        HTTPException: 404 if playbook not found.
    """
    # tenant_id comes from the body so we can look it up
    playbook = (
        await db.execute(select(Playbook).where(Playbook.id == body.playbook_id))
    ).scalar_one_or_none()
    if playbook is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playbook not found")

    event: dict = {
        "event": "manual",
        "tenant_id": str(playbook.tenant_id),
        "entity_type": body.entity_type,
        "entity_id": str(body.entity_id) if body.entity_id else None,
        "payload": body.event_payload,
    }
    run = await svc.run_playbook(db, playbook, event)
    return PlaybookRunRead.model_validate(run)
