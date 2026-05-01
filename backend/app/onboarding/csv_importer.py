"""CSV importer for bulk contact (and optional account) creation.

Parses a CSV file and bulk-inserts rows into the `contacts` table,
optionally creating `accounts` on the fly when a company column is present.

Field mapping
─────────────
The caller passes a ``field_mapping`` dict that maps *canonical keys* to
*CSV column headers* present in the file.  Recognised canonical keys:

  first_name, last_name, email, phone, job_title, status, company

``email``, ``first_name``, and ``last_name`` are required.
All other fields are optional and silently skipped when absent.

Limits
──────
- Max file size : 5 MB  (enforced in the router before calling this module)
- Max rows      : 5 000 (enforced here)
- On duplicate  (org_id, email): row is skipped and counted in ``skipped``
"""

from __future__ import annotations

import csv
import io
import logging
import re
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.crm.models import Account, Contact

logger = logging.getLogger(__name__)

_MAX_ROWS = 5_000
_REQUIRED_FIELDS: set[str] = {"email", "first_name", "last_name"}
_VALID_STATUSES: set[str] = {"active", "lead", "customer", "churned"}
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------------------
# Public entry-point
# ---------------------------------------------------------------------------

async def import_contacts_from_csv(
    content: bytes,
    tenant_id: UUID,
    user_id: UUID,
    field_mapping: dict[str, str],
    db: AsyncSession,
) -> dict[str, Any]:
    """Parse *content* and bulk-insert contacts for *tenant_id*.

    Args:
        content: Raw bytes of the uploaded CSV file.
        tenant_id: The organisation UUID (used as ``org_id`` on each row).
        user_id: The authenticated user performing the import.
        field_mapping: Maps canonical field names → CSV column headers.
        db: Async SQLAlchemy session.

    Returns:
        A dict with keys ``inserted``, ``skipped``, ``errors`` (list of
        ``{"row": int, "reason": str}``).

    Raises:
        ValueError: When the CSV is malformed or required columns are absent.
    """
    _validate_mapping(field_mapping)

    text_content = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text_content))

    if reader.fieldnames is None:
        raise ValueError("CSV file appears to be empty — no header row found.")

    _check_required_columns(reader.fieldnames, field_mapping)

    # Set RLS context for this session so FK lookups and UNIQUE checks work
    await db.execute(
        text("SELECT set_config('app.current_tenant_id', :tid, true)"),
        {"tid": str(tenant_id)},
    )

    inserted = 0
    skipped = 0
    errors: list[dict[str, Any]] = []

    # Cache: company_name → account_id  (avoids a DB round-trip per row)
    account_cache: dict[str, UUID] = {}

    for row_num, row in enumerate(reader, start=2):
        if row_num - 1 > _MAX_ROWS:
            errors.append({"row": row_num, "reason": f"Import limit of {_MAX_ROWS} rows reached; remaining rows skipped."})
            break

        try:
            contact_kwargs = _map_row(row, field_mapping, row_num)
        except ValueError as exc:
            errors.append({"row": row_num, "reason": str(exc)})
            continue

        # Optional company → account resolution
        company = _get(row, field_mapping, "company")
        if company:
            contact_kwargs["account_id"] = await _resolve_account(
                db, company, tenant_id, user_id, account_cache
            )

        # Duplicate-check
        existing = await db.execute(
            select(Contact).where(
                Contact.org_id == tenant_id,
                Contact.email == contact_kwargs["email"],
            )
        )
        if existing.scalar_one_or_none() is not None:
            skipped += 1
            continue

        db.add(
            Contact(
                id=uuid4(),
                org_id=tenant_id,
                created_by=user_id,
                **contact_kwargs,
            )
        )
        inserted += 1

    await db.commit()

    logger.info(
        "CSV import completed tenant=%s inserted=%d skipped=%d errors=%d",
        tenant_id, inserted, skipped, len(errors),
    )

    return {"inserted": inserted, "skipped": skipped, "errors": errors}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_mapping(field_mapping: dict[str, str]) -> None:
    """Raise ValueError if mandatory canonical keys are missing."""
    missing = _REQUIRED_FIELDS - set(field_mapping.keys())
    if missing:
        raise ValueError(
            f"field_mapping is missing required canonical keys: {sorted(missing)}"
        )


def _check_required_columns(
    headers: list[str], field_mapping: dict[str, str]
) -> None:
    """Raise ValueError when a required CSV column header is absent."""
    header_set = {h.strip() for h in headers}
    for canonical in _REQUIRED_FIELDS:
        csv_col = field_mapping.get(canonical, "")
        if csv_col not in header_set:
            raise ValueError(
                f"Required column '{csv_col}' (mapped from '{canonical}') "
                "not found in CSV headers."
            )


def _get(row: dict[str, str], mapping: dict[str, str], canonical: str) -> str:
    """Return the value of the canonical field from *row*, or empty string."""
    col = mapping.get(canonical, "")
    return row.get(col, "").strip()


def _map_row(
    row: dict[str, str],
    field_mapping: dict[str, str],
    row_num: int,
) -> dict[str, Any]:
    """Extract and validate one CSV row into a dict of Contact kwargs.

    Raises:
        ValueError: On invalid email or empty required fields.
    """
    email = _get(row, field_mapping, "email")
    first_name = _get(row, field_mapping, "first_name")
    last_name = _get(row, field_mapping, "last_name")

    if not email:
        raise ValueError("email is empty")
    if not _EMAIL_RE.match(email):
        raise ValueError(f"invalid email format: '{email}'")
    if not first_name:
        raise ValueError("first_name is empty")
    if not last_name:
        raise ValueError("last_name is empty")

    status = _get(row, field_mapping, "status") or "active"
    if status not in _VALID_STATUSES:
        status = "active"

    return {
        "first_name": first_name[:255],
        "last_name": last_name[:255],
        "email": email[:255].lower(),
        "phone": _get(row, field_mapping, "phone")[:50] or None,
        "job_title": _get(row, field_mapping, "job_title")[:150] or None,
        "status": status,
    }


async def _resolve_account(
    db: AsyncSession,
    company: str,
    tenant_id: UUID,
    user_id: UUID,
    cache: dict[str, UUID],
) -> Optional[UUID]:
    """Return the account_id for *company*, creating the account if needed.

    Uses an in-memory cache to avoid one DB round-trip per row when the same
    company appears multiple times in the CSV.
    """
    key = company.lower().strip()
    if key in cache:
        return cache[key]

    result = await db.execute(
        select(Account).where(
            Account.org_id == tenant_id,
            Account.name == company,
        )
    )
    account = result.scalar_one_or_none()

    if account is None:
        account = Account(
            id=uuid4(),
            org_id=tenant_id,
            name=company[:255],
            status="active",
            created_by=user_id,
        )
        db.add(account)
        await db.flush()

    cache[key] = account.id
    return account.id
