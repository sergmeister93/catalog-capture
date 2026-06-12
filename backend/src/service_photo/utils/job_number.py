"""
Job number generator.

Inputs:  a SQLAlchemy Session and the current UTC date
Outputs: a unique job_number string in the format JOB-YYYYMMDD-NNN

The NNN counter is derived by counting existing job_numbers that share
the same date prefix, so it is sequential within a day. Uniqueness is
enforced by the database UNIQUE constraint on listing_jobs.job_number —
if a collision occurs (concurrent inserts on the same day), the DB will
raise an IntegrityError that the caller can retry.
"""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from service_photo.models.listing_job import ListingJob


def generate_job_number(db: Session, for_date: date | None = None) -> str:
    """
    Return the next available job_number for the given date.

    Example: JOB-20260419-001
    """
    from datetime import datetime, timezone

    if for_date is None:
        for_date = datetime.now(timezone.utc).date()

    date_prefix = f"JOB-{for_date.strftime('%Y%m%d')}-"

    # Count how many jobs already exist for this date prefix.
    count = db.execute(
        select(func.count()).where(
            ListingJob.job_number.like(f"{date_prefix}%")
        )
    ).scalar() or 0

    # Next sequence number is count + 1, zero-padded to 3 digits.
    next_seq = count + 1
    return f"{date_prefix}{next_seq:03d}"
