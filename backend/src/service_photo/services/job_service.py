"""
Job creation service.

Handles POST /jobs: generates job_id, job_number, inserts listing_jobs row,
inserts initial status history row.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from service_photo.models.listing_job import ListingJob
from service_photo.repositories import jobs as job_repo
from service_photo.utils.job_number import generate_job_number


def create_listing_job(
    db: Session,
    item_category: str | None,
    created_by: str | None,
    notes: str | None,
) -> ListingJob:
    """
    Create a new listing job in 'initialized' status.

    Inserts:
      - listing_jobs row
      - listing_job_status_history row (old_status=null, new_status='initialized')

    Returns the new ListingJob ORM instance.
    """
    now = datetime.now(timezone.utc)
    job_id = uuid.uuid4()
    job_number = generate_job_number(db)

    job = job_repo.create_job(
        db=db,
        job_id=job_id,
        job_number=job_number,
        status="initialized",
        item_category=item_category,
        created_by=created_by,
        notes=notes,
        now=now,
    )

    job_repo.add_status_history(
        db=db,
        job_id=job_id,
        old_status=None,
        new_status="initialized",
        changed_by=created_by,
        change_reason="Job created",
        now=now,
    )

    return job
