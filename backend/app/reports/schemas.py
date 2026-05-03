"""Pydantic schemas for Feature #7 — PDF Reports."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

REPORT_TYPES: frozenset[str] = frozenset(
    {"pipeline", "mrr", "team_performance", "churn"}
)

REPORT_STATUSES: frozenset[str] = frozenset(
    {"pending", "generating_data", "rendering", "done", "failed"}
)


class ReportGenerateRequest(BaseModel):
    """Request body for POST /api/v1/reports/generate.

    Attributes:
        report_type: One of pipeline | mrr | team_performance | churn.
        parameters: Optional extra parameters (future expansion).
    """

    report_type: str
    parameters: dict[str, Any] = {}

    @field_validator("report_type")
    @classmethod
    def validate_report_type(cls, v: str) -> str:
        """Validate report_type is a supported value.

        Args:
            v: Raw report_type string.

        Returns:
            Validated report_type string.

        Raises:
            ValueError: If report_type is not in REPORT_TYPES.
        """
        if v not in REPORT_TYPES:
            raise ValueError(
                f"Unknown report_type '{v}'. "
                f"Must be one of: {sorted(REPORT_TYPES)}"
            )
        return v


class ReportJobStatusRead(BaseModel):
    """Read schema for a report job, returned by status and generate endpoints.

    Attributes:
        id: Job UUID.
        tenant_id: Owning tenant UUID.
        report_type: Type of report.
        status: Current job status.
        download_url: Available once status is 'done'.
        error: Present if status is 'failed'.
        created_at: When the job was created.
        completed_at: When the job completed (done or failed).
    """

    id: UUID
    tenant_id: UUID
    report_type: str
    status: str
    download_url: str | None = None
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
