"""Email delivery API endpoints.

Routes
------
POST /internal/v1/email/enqueue
    Queue an email for delivery. Called by mcp-sequences (inter-service auth).
    Body: EmailEnqueueRequest

GET  /track/{open_token}
    Open-tracking pixel endpoint (no auth, public).
    Returns a 1×1 transparent GIF and records opened_at.

GET  /click/{click_token}
    Click-tracking redirect endpoint (no auth, public).
    Query param: url (required) — the destination to redirect to.
    Records clicked_at, then 302 redirects.
"""

from __future__ import annotations

import base64
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db import get_db

from .schemas import EmailEnqueueRequest, EmailSendPublic
from .service import enqueue_send, mark_clicked, mark_opened

logger = logging.getLogger(__name__)

router = APIRouter()  # enqueue — mounted at /internal/v1/email
tracking_router = APIRouter()  # track/click — mounted at root

# Minimal 1×1 transparent GIF (35 bytes)
_TRANSPARENT_GIF = base64.b64decode(
    "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)

_INTER_SERVICE_SECRET_HEADER = "x-inter-service-secret"


def _verify_inter_service(request: Request) -> None:
    """Validate the inter-service shared secret on internal endpoints.

    Args:
        request: Incoming FastAPI Request.

    Raises:
        HTTPException: 401 if the header is missing or invalid.
    """
    from app.config import settings  # local import to avoid circular

    secret = request.headers.get(_INTER_SERVICE_SECRET_HEADER, "")
    if not secret or secret != settings.mcp_inter_service_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid inter-service secret",
        )


@router.post(
    "/enqueue",
    response_model=EmailSendPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Queue an email for delivery (internal)",
)
async def enqueue_email(
    request: Request,
    body: EmailEnqueueRequest,
    db: AsyncSession = Depends(get_db),
) -> EmailSendPublic:
    """Accept an email from an internal service and add it to the send queue.

    Authenticated by the ``x-inter-service-secret`` header shared between
    the backend and MCP services.

    Args:
        request: Raw request (used to read secret header).
        body: Email payload.
        db: Database session.

    Returns:
        The created EmailSend record (status=pending).

    Raises:
        HTTPException: 401 if secret is wrong.
    """
    _verify_inter_service(request)
    send = await enqueue_send(
        db,
        tenant_id=body.tenant_id,
        contact_id=body.contact_id,
        to_email=str(body.to_email),
        subject=body.subject,
        body_html=body.body_html,
        sequence_id=body.sequence_id,
        step_index=body.step_index,
    )
    return EmailSendPublic.model_validate(send)


@tracking_router.get(
    "/track/{open_token}",
    summary="Open-tracking pixel (public)",
    include_in_schema=False,
)
async def track_open(
    open_token: UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Return a 1×1 transparent GIF and record the open event.

    This endpoint is intentionally unauthenticated — it is embedded in emails
    as an invisible image and fired by the recipient's mail client.

    Args:
        open_token: Unique per-send UUID from the pixel URL.
        db: Database session.

    Returns:
        1×1 transparent GIF response (image/gif).
    """
    found = await mark_opened(db, open_token)
    if not found:
        logger.debug("track_open: unknown token %s", open_token)
    return Response(content=_TRANSPARENT_GIF, media_type="image/gif")


@tracking_router.get(
    "/click/{click_token}",
    summary="Click-tracking redirect (public)",
    include_in_schema=False,
)
async def track_click(
    click_token: UUID,
    url: str = Query(..., description="Destination URL to redirect to"),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Record a click event and redirect to the target URL.

    Also intentionally unauthenticated — links in emails are wrapped with
    this endpoint before sending.

    Args:
        click_token: Unique per-send UUID from the click URL.
        url: Destination URL.
        db: Database session.

    Returns:
        302 redirect to ``url``.
    """
    # Basic URL safety check — reject javascript: and data: schemes
    lower = url.lower().strip()
    if lower.startswith(("javascript:", "data:", "vbscript:")):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Redirect URL scheme not allowed",
        )

    email = await mark_clicked(db, click_token)
    if email:
        logger.info("track_click: contact clicked url=%s (email=%s)", url, email)
    else:
        logger.debug("track_click: unknown token %s", click_token)

    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)
