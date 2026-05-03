"""Webhook management endpoints.

Routes
------
POST   /api/v1/webhooks              Create a new webhook subscription
GET    /api/v1/webhooks              List all webhooks for the current tenant
DELETE /api/v1/webhooks/{id}         Delete (revoke) a webhook
GET    /api/v1/webhooks/{id}/logs    List delivery logs for a webhook
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user
from app.common.db import get_db
from app.models.user import User

from .schemas import (
    WebhookDeliveryLogPublic,
    WebhookEndpointCreate,
    WebhookEndpointPublic,
    WebhookEndpointResponse,
)
from .service import create_endpoint, delete_endpoint, list_endpoints, list_logs

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])


@router.post(
    "",
    response_model=WebhookEndpointResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a webhook subscription",
)
async def create_webhook(
    body: WebhookEndpointCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> WebhookEndpointResponse:
    """Register a new webhook endpoint.

    The ``secret`` field in the response is the HMAC-SHA256 signing key.
    It is returned **once** — store it securely. Incoming requests will carry
    ``X-Revops-Signature: sha256=<hex>`` computed with this secret.

    Args:
        body: Webhook creation payload (event_type + HTTPS url).
        current_user: Authenticated user (injected by FastAPI).
        db: Database session (injected by FastAPI).

    Returns:
        The created endpoint including the signing secret.
    """
    endpoint = await create_endpoint(
        db=db,
        tenant_id=current_user.tenant_id,
        event_type=body.event_type,
        url=str(body.url),
    )
    logger.info(
        "webhooks: created endpoint %s for tenant %s event=%s",
        endpoint.id,
        current_user.tenant_id,
        body.event_type,
    )
    return WebhookEndpointResponse.model_validate(endpoint)


@router.get(
    "",
    response_model=list[WebhookEndpointPublic],
    summary="List webhook subscriptions",
)
async def list_webhooks(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[WebhookEndpointPublic]:
    """Return all webhook endpoints for the current tenant (secret omitted).

    Args:
        current_user: Authenticated user (injected by FastAPI).
        db: Database session (injected by FastAPI).

    Returns:
        List of webhook endpoints without the signing secret.
    """
    endpoints = await list_endpoints(db=db, tenant_id=current_user.tenant_id)
    return [WebhookEndpointPublic.model_validate(ep) for ep in endpoints]


@router.delete(
    "/{webhook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a webhook subscription",
)
async def delete_webhook(
    webhook_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Revoke a webhook endpoint.

    Args:
        webhook_id: UUID of the endpoint to delete.
        current_user: Authenticated user (injected by FastAPI).
        db: Database session (injected by FastAPI).

    Raises:
        HTTPException: 404 if the endpoint is not found or not owned by tenant.
    """
    deleted = await delete_endpoint(
        db=db, endpoint_id=webhook_id, tenant_id=current_user.tenant_id
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")
    logger.info(
        "webhooks: deleted endpoint %s for tenant %s",
        webhook_id,
        current_user.tenant_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{webhook_id}/logs",
    response_model=list[WebhookDeliveryLogPublic],
    summary="Delivery logs for a webhook",
)
async def get_webhook_logs(
    webhook_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[WebhookDeliveryLogPublic]:
    """Return the last 50 delivery attempts for a webhook endpoint.

    Args:
        webhook_id: UUID of the endpoint.
        current_user: Authenticated user (injected by FastAPI).
        db: Database session (injected by FastAPI).

    Returns:
        List of delivery log entries (newest first).
    """
    logs = await list_logs(
        db=db,
        endpoint_id=webhook_id,
        tenant_id=current_user.tenant_id,
    )
    return [WebhookDeliveryLogPublic.model_validate(log) for log in logs]
