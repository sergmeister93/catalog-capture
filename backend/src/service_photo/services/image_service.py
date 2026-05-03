"""
Image registration service.

Handles POST /jobs/{job_id}/images: validates preconditions, inserts image row,
updates job.updated_at.
"""

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from service_photo.models.listing_job import ListingJob
from service_photo.models.listing_job_image import ListingJobImage
from service_photo.repositories import images as image_repo
from service_photo.repositories import jobs as job_repo
from service_photo.schemas.jobs import RegisterImageInput

# Jobs in these statuses cannot have images added.
TERMINAL_STATUSES = {"approved", "exported", "rejected"}


def register_image(
    db: Session,
    job: ListingJob,
    data: RegisterImageInput,
) -> ListingJobImage:
    """
    Register one image for the given job.

    Raises HTTPException on:
      - 409 if job is in a terminal status
      - 409 if image_order is already taken for this job
    """
    if job.status in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=409,
            detail={"error": "job_not_editable", "message": f"Job is in terminal status '{job.status}' and cannot be modified."},
        )

    if image_repo.image_order_exists(db, job.job_id, data.image_order):
        raise HTTPException(
            status_code=409,
            detail={"error": "image_order_conflict", "message": f"image_order {data.image_order} is already registered for this job."},
        )

    now = datetime.now(timezone.utc)

    image = image_repo.create_image(
        db=db,
        job_id=job.job_id,
        file_name=data.file_name,
        file_path=data.file_path,
        file_type=data.file_type,
        image_order=data.image_order,
        is_primary=data.is_primary,
        uploaded_at=now,
        file_size_bytes=data.file_size_bytes,
        uploaded_by=data.uploaded_by,
        checksum=data.checksum,
    )

    # Touch job.updated_at on every image registration.
    job.updated_at = now
    db.flush()

    return image
