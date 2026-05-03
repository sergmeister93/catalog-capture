"""
Repository helpers for all four review tables.

Upsert pattern: fetch by job_id → update if found, insert if not.
Only the sections present in the caller's data dict are written;
omitted sections are left untouched (enforced by the service layer
which only calls the relevant upsert function).
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from service_photo.models.listing_review_overview import ListingReviewOverview
from service_photo.models.listing_review_description import ListingReviewDescription
from service_photo.models.listing_review_specifications import ListingReviewSpecifications
from service_photo.models.listing_review_accessories import ListingReviewAccessories


def upsert_review_overview(
    db: Session,
    job_id: uuid.UUID,
    data: dict,
    now: datetime,
) -> ListingReviewOverview:
    row = db.execute(
        select(ListingReviewOverview).where(ListingReviewOverview.job_id == job_id)
    ).scalar_one_or_none()

    if row is None:
        row = ListingReviewOverview(
            review_overview_id=uuid.uuid4(),
            job_id=job_id,
            # Placeholders overwritten immediately by data dict below.
            product_name="",
            condition_summary="",
            last_edited_at=now,
        )
        db.add(row)

    for field, value in data.items():
        setattr(row, field, value)
    row.last_edited_at = now
    db.flush()
    return row


def upsert_review_description(
    db: Session,
    job_id: uuid.UUID,
    data: dict,
    now: datetime,
) -> ListingReviewDescription:
    row = db.execute(
        select(ListingReviewDescription).where(ListingReviewDescription.job_id == job_id)
    ).scalar_one_or_none()

    if row is None:
        row = ListingReviewDescription(
            review_description_id=uuid.uuid4(),
            job_id=job_id,
            short_title="",
            description_text="",
            last_edited_at=now,
        )
        db.add(row)

    for field, value in data.items():
        setattr(row, field, value)
    row.last_edited_at = now
    db.flush()
    return row


def upsert_review_specifications(
    db: Session,
    job_id: uuid.UUID,
    data: dict,
    now: datetime,
) -> ListingReviewSpecifications:
    row = db.execute(
        select(ListingReviewSpecifications).where(ListingReviewSpecifications.job_id == job_id)
    ).scalar_one_or_none()

    if row is None:
        row = ListingReviewSpecifications(
            review_specifications_id=uuid.uuid4(),
            job_id=job_id,
            last_edited_at=now,
        )
        db.add(row)

    for field, value in data.items():
        setattr(row, field, value)
    row.last_edited_at = now
    db.flush()
    return row


def upsert_review_accessories(
    db: Session,
    job_id: uuid.UUID,
    data: dict,
    now: datetime,
) -> ListingReviewAccessories:
    row = db.execute(
        select(ListingReviewAccessories).where(ListingReviewAccessories.job_id == job_id)
    ).scalar_one_or_none()

    if row is None:
        row = ListingReviewAccessories(
            review_accessories_id=uuid.uuid4(),
            job_id=job_id,
            included_accessories_text="",
            last_edited_at=now,
        )
        db.add(row)

    for field, value in data.items():
        setattr(row, field, value)
    row.last_edited_at = now
    db.flush()
    return row


def get_review_overview(db: Session, job_id: uuid.UUID) -> ListingReviewOverview | None:
    return db.execute(
        select(ListingReviewOverview).where(ListingReviewOverview.job_id == job_id)
    ).scalar_one_or_none()


def get_review_description(db: Session, job_id: uuid.UUID) -> ListingReviewDescription | None:
    return db.execute(
        select(ListingReviewDescription).where(ListingReviewDescription.job_id == job_id)
    ).scalar_one_or_none()


def get_review_specifications(db: Session, job_id: uuid.UUID) -> ListingReviewSpecifications | None:
    return db.execute(
        select(ListingReviewSpecifications).where(ListingReviewSpecifications.job_id == job_id)
    ).scalar_one_or_none()


def get_review_accessories(db: Session, job_id: uuid.UUID) -> ListingReviewAccessories | None:
    return db.execute(
        select(ListingReviewAccessories).where(ListingReviewAccessories.job_id == job_id)
    ).scalar_one_or_none()
