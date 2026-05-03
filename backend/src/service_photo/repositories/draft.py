"""
Repository helpers for all four draft tables.

All upserts use the pattern:
  - try to fetch the existing row by job_id
  - if found, update in place
  - if not found, insert new
This is equivalent to ON CONFLICT (job_id) DO UPDATE but works portably
with the ORM session cache.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from service_photo.models.listing_draft_overview import ListingDraftOverview
from service_photo.models.listing_draft_description import ListingDraftDescription
from service_photo.models.listing_draft_specifications import ListingDraftSpecifications
from service_photo.models.listing_draft_accessories import ListingDraftAccessories


def upsert_draft_overview(
    db: Session,
    job_id: uuid.UUID,
    data: dict,
    now: datetime,
) -> ListingDraftOverview:
    """Insert or replace the draft_overview row for this job."""
    row = db.execute(
        select(ListingDraftOverview).where(ListingDraftOverview.job_id == job_id)
    ).scalar_one_or_none()

    if row is None:
        row = ListingDraftOverview(draft_overview_id=uuid.uuid4(), job_id=job_id, created_at=now)
        db.add(row)

    for field, value in data.items():
        setattr(row, field, value)
    db.flush()
    return row


def upsert_draft_description(
    db: Session,
    job_id: uuid.UUID,
    data: dict,
    now: datetime,
) -> ListingDraftDescription:
    row = db.execute(
        select(ListingDraftDescription).where(ListingDraftDescription.job_id == job_id)
    ).scalar_one_or_none()

    if row is None:
        row = ListingDraftDescription(draft_description_id=uuid.uuid4(), job_id=job_id, created_at=now)
        db.add(row)

    for field, value in data.items():
        setattr(row, field, value)
    db.flush()
    return row


def upsert_draft_specifications(
    db: Session,
    job_id: uuid.UUID,
    data: dict,
    now: datetime,
) -> ListingDraftSpecifications:
    row = db.execute(
        select(ListingDraftSpecifications).where(ListingDraftSpecifications.job_id == job_id)
    ).scalar_one_or_none()

    if row is None:
        row = ListingDraftSpecifications(draft_specifications_id=uuid.uuid4(), job_id=job_id, created_at=now)
        db.add(row)

    for field, value in data.items():
        setattr(row, field, value)
    db.flush()
    return row


def upsert_draft_accessories(
    db: Session,
    job_id: uuid.UUID,
    data: dict,
    now: datetime,
) -> ListingDraftAccessories:
    row = db.execute(
        select(ListingDraftAccessories).where(ListingDraftAccessories.job_id == job_id)
    ).scalar_one_or_none()

    if row is None:
        row = ListingDraftAccessories(draft_accessories_id=uuid.uuid4(), job_id=job_id, created_at=now)
        db.add(row)

    for field, value in data.items():
        setattr(row, field, value)
    db.flush()
    return row


def get_draft_overview(db: Session, job_id: uuid.UUID) -> ListingDraftOverview | None:
    return db.execute(
        select(ListingDraftOverview).where(ListingDraftOverview.job_id == job_id)
    ).scalar_one_or_none()


def get_draft_description(db: Session, job_id: uuid.UUID) -> ListingDraftDescription | None:
    return db.execute(
        select(ListingDraftDescription).where(ListingDraftDescription.job_id == job_id)
    ).scalar_one_or_none()


def get_draft_specifications(db: Session, job_id: uuid.UUID) -> ListingDraftSpecifications | None:
    return db.execute(
        select(ListingDraftSpecifications).where(ListingDraftSpecifications.job_id == job_id)
    ).scalar_one_or_none()


def get_draft_accessories(db: Session, job_id: uuid.UUID) -> ListingDraftAccessories | None:
    return db.execute(
        select(ListingDraftAccessories).where(ListingDraftAccessories.job_id == job_id)
    ).scalar_one_or_none()
