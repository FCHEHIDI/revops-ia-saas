"""Onboarding router.

Endpoints
─────────
POST /onboarding/import-csv
    Bulk-import contacts from a CSV file.
    Requires an authenticated session (JWT cookie).
    Accepts a multipart/form-data body with:
      - ``file``          : UploadFile — the CSV (max 5 MB)
      - ``field_mapping`` : JSON string — maps canonical keys → CSV headers
                            Required keys: email, first_name, last_name
                            Optional keys: phone, job_title, status, company

    Example field_mapping:
    {
      "first_name": "First Name",
      "last_name":  "Surname",
      "email":      "Email Address",
      "phone":      "Mobile",
      "job_title":  "Title",
      "company":    "Company"
    }

    Returns:
      200  { "inserted": int, "skipped": int, "errors": [...] }
      400  validation error (missing columns, bad JSON, …)
      413  file too large
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, Form, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user
from app.common.db import get_db
from app.models.user import User
from app.onboarding.csv_importer import import_contacts_from_csv

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

_MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB

# Default field mapping when the caller does not provide one.
# Matches the most common CSV export from tools like HubSpot / Salesforce.
_DEFAULT_MAPPING: dict[str, str] = {
    "first_name": "First Name",
    "last_name":  "Last Name",
    "email":      "Email",
    "phone":      "Phone",
    "job_title":  "Job Title",
    "status":     "Status",
    "company":    "Company",
}


class ImportResult(BaseModel):
    """Response schema for POST /onboarding/import-csv."""
    inserted: int
    skipped: int
    errors: list[dict[str, Any]]


@router.post(
    "/import-csv",
    response_model=ImportResult,
    summary="Bulk-import contacts from a CSV file",
    responses={
        400: {"description": "Invalid file or field_mapping"},
        413: {"description": "File exceeds 5 MB limit"},
    },
)
async def import_csv(
    file: UploadFile,
    field_mapping: str = Form(
        default="",
        description=(
            "JSON object mapping canonical field names to CSV column headers. "
            "Required keys: email, first_name, last_name. "
            "Optional keys: phone, job_title, status, company."
        ),
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ImportResult:
    """Import contacts from an uploaded CSV file.

    Args:
        file: The multipart-uploaded CSV file (max 5 MB).
        field_mapping: JSON string mapping canonical → CSV column names.
        current_user: Authenticated user injected via JWT cookie.
        db: Async database session.

    Returns:
        An ImportResult with counts of inserted, skipped, and errored rows.

    Raises:
        HTTPException 400: Malformed JSON, missing required columns, or empty file.
        HTTPException 413: File exceeds the 5 MB size limit.
    """
    # ── 1. Validate content type ────────────────────────────────────────
    content_type = (file.content_type or "").lower()
    if content_type and content_type not in {
        "text/csv",
        "text/plain",
        "application/csv",
        "application/vnd.ms-excel",
        "application/octet-stream",
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported content type '{content_type}'. Expected a CSV file.",
        )

    # ── 2. Read & size-check ────────────────────────────────────────────
    content = await file.read()
    if len(content) > _MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds the 5 MB limit.",
        )
    if not content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # ── 3. Parse field_mapping ──────────────────────────────────────────
    if field_mapping.strip():
        try:
            mapping: dict[str, str] = json.loads(field_mapping)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"field_mapping is not valid JSON: {exc}",
            ) from exc
    else:
        mapping = _DEFAULT_MAPPING

    if not isinstance(mapping, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in mapping.items()
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="field_mapping must be a flat JSON object with string values.",
        )

    # ── 4. Run import ───────────────────────────────────────────────────
    try:
        result = await import_contacts_from_csv(
            content=content,
            tenant_id=current_user.org_id,
            user_id=current_user.id,
            field_mapping=mapping,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return ImportResult(**result)
