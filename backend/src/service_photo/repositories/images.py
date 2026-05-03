"""Repository helpers for listing_job_images."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from service_photo.models.listing_job_image import ListingJobImage


def get_images_for_job(db: Session, job_id: uuid.UUID) -> list[ListingJobImage]:
    """Return all images for a job ordered by image_order ascending."""
    stmt = (
        select(ListingJobImage)
        .where(ListingJobImage.job_id == job_id)
        .order_by(ListingJobImage.image_order)
    )
    return list(db.execute(stmt).scalars().all())


def image_order_exists(db: Session, job_id: uuid.UUID, image_order: int) -> bool:
    """Return True if the given image_order is already taken for this job."""
    stmt = select(ListingJobImage).where(
        ListingJobImage.job_id == job_id,
        ListingJobImage.image_order == image_order,
    )
    return db.execute(stmt).scalar_one_or_none() is not None


def create_image(
    db: Session,
    job_id: uuid.UUID,
    file_name: str,
    file_path: str,
    file_type: str,
    image_order: int,
    is_primary: bool,
    uploaded_at: datetime,
    file_size_bytes: int | None = None,
    uploaded_by: str | None = None,
    checksum: str | None = None,
) -> ListingJobImage:
    """Insert a new listing_job_images row and return it."""
    image = ListingJobImage(
        image_id=uuid.uuid4(),
        job_id=job_id,
        file_name=file_name,
        file_path=file_path,
        file_type=file_type,
        file_size_bytes=file_size_bytes,
        image_order=image_order,
        is_primary=is_primary,
        uploaded_at=uploaded_at,
        uploaded_by=uploaded_by,
        checksum=checksum,
    )
    db.add(image)
    db.flush()
    return image
