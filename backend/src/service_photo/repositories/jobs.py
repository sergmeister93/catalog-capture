"""
Repository helpers for listing_jobs and listing_job_status_history.

All functions accept a SQLAlchemy Session and return ORM model instances
(or None). Business logic belongs in the service layer, not here.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from service_photo.models.listing_job import ListingJob
from service_photo.models.listing_job_status_history import ListingJobStatusHistory


def get_job_by_id(db: Session, job_id: uuid.UUID) -> ListingJob | None:
    """Return the ListingJob with the given job_id, or None."""
    return db.get(ListingJob, job_id)


def create_job(
    db: Session,
    job_id: uuid.UUID,
    job_number: str,
    status: str,
    item_category: str | None,
    created_by: str | None,
    notes: str | None,
    now: datetime,
) -> ListingJob:
    """Insert a new listing_jobs row and return it."""
    job = ListingJob(
        job_id=job_id,
        job_number=job_number,
        status=status,
        item_category=item_category,
        created_by=created_by,
        notes=notes,
        is_reviews_enriched=False,
        is_price_enriched=False,
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.flush()
    return job


def update_job_status(
    db: Session,
    job: ListingJob,
    new_status: str,
    now: datetime,
    approved_by: str | None = None,
    reviewed_by: str | None = None,
    exported_at: datetime | None = None,
) -> None:
    """Update job status and related audit fields in place."""
    job.status = new_status
    job.updated_at = now
    if approved_by is not None:
        job.approved_by = approved_by
    if reviewed_by is not None:
        job.reviewed_by = reviewed_by
    if new_status == "approved":
        job.approved_at = now
    if exported_at is not None:
        job.exported_at = exported_at
    db.flush()


def add_status_history(
    db: Session,
    job_id: uuid.UUID,
    old_status: str | None,
    new_status: str,
    changed_by: str | None,
    change_reason: str | None,
    now: datetime,
) -> ListingJobStatusHistory:
    """Append a new status history row. Never updates existing rows."""
    row = ListingJobStatusHistory(
        status_history_id=uuid.uuid4(),
        job_id=job_id,
        old_status=old_status,
        new_status=new_status,
        changed_at=now,
        changed_by=changed_by,
        change_reason=change_reason,
    )
    db.add(row)
    db.flush()
    return row
