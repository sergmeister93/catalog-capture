"""
Pydantic schemas for listing jobs, images, and status history.

Mirrors the OpenAPI components/schemas section exactly.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Shared enum-like type for status
# ---------------------------------------------------------------------------
JobStatus = Literal[
    "uploaded",
    "initialized",
    "submitted_to_ai",
    "ai_response_received",
    "ready_for_review",
    "under_review",
    "approved",
    "exported",
    "validation_failed",
    "ai_error",
    "needs_rework",
    "rejected",
]


# ---------------------------------------------------------------------------
# Core job record
# ---------------------------------------------------------------------------
class ListingJob(BaseModel):
    """Mirrors ListingJob in the OpenAPI spec."""
    model_config = ConfigDict(from_attributes=True)

    job_id: uuid.UUID
    job_number: str
    created_at: datetime
    updated_at: datetime
    created_by: str | None = None
    reviewed_by: str | None = None
    approved_by: str | None = None
    status: JobStatus
    item_category: str | None = None
    is_reviews_enriched: bool
    is_price_enriched: bool
    approved_at: datetime | None = None
    exported_at: datetime | None = None
    notes: str | None = None


class StatusHistoryEntry(BaseModel):
    """One row from listing_job_status_history."""
    model_config = ConfigDict(from_attributes=True)

    status_history_id: uuid.UUID
    job_id: uuid.UUID
    old_status: JobStatus | None = None
    new_status: JobStatus
    changed_at: datetime
    changed_by: str | None = None
    change_reason: str | None = None


class ListingJobImage(BaseModel):
    """One row from listing_job_images."""
    model_config = ConfigDict(from_attributes=True)

    image_id: uuid.UUID
    job_id: uuid.UUID
    file_name: str
    file_path: str
    file_type: str
    file_size_bytes: int | None = None
    image_order: int
    is_primary: bool
    uploaded_at: datetime
    uploaded_by: str | None = None
    checksum: str | None = None


class ListingJobDetail(ListingJob):
    """Job record extended with images and status history."""
    images: list[ListingJobImage] = []
    status_history: list[StatusHistoryEntry] = []


# ---------------------------------------------------------------------------
# Request input schemas
# ---------------------------------------------------------------------------
class CreateJobInput(BaseModel):
    item_category: str | None = None
    created_by: str | None = None
    notes: str | None = None


class RegisterImageInput(BaseModel):
    file_name: str
    file_path: str
    file_type: str
    file_size_bytes: int | None = None
    image_order: int
    is_primary: bool = False
    uploaded_by: str | None = None
    checksum: str | None = None


class SubmitJobInput(BaseModel):
    submitted_by: str | None = None


class ApproveJobInput(BaseModel):
    approved_by: str | None = None


class ExportJobInput(BaseModel):
    export_type: Literal["csv"] = "csv"
    exported_by: str | None = None
