"""
Review save service.

Handles PUT /jobs/{job_id}/review: upserts only the sections present in the
request body. Omitted sections are left untouched. Transitions the job to
under_review on the first save from ready_for_review.
"""

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from service_photo.models.listing_job import ListingJob
from service_photo.repositories import jobs as job_repo
from service_photo.repositories import review as review_repo
from service_photo.schemas.review import (
    SaveReviewInput,
    ReviewContent,
    ReviewOverview,
    ReviewDescription,
    ReviewSpecifications,
    ReviewAccessories,
)

# Statuses that allow review content to be saved.
EDITABLE_STATUSES = {"ready_for_review", "under_review"}


def save_review_content(
    db: Session,
    job: ListingJob,
    data: SaveReviewInput,
) -> ReviewContent:
    """
    Upsert one or more review sections.

    Returns the current state of ALL four review sections after the write
    (including sections not touched in this call).

    Raises HTTPException on:
      - 400 if no sections are provided in the request body
      - 409 if job is not in an editable status
    """
    if job.status not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail={"error": "invalid_status_for_review", "message": f"Job must be in ready_for_review or under_review status. Current: '{job.status}'."},
        )

    has_any_section = any([data.overview, data.description, data.specifications, data.accessories])
    if not has_any_section:
        raise HTTPException(
            status_code=400,
            detail={"error": "no_review_sections_provided", "message": "At least one review section (overview, description, specifications, accessories) must be provided."},
        )

    now = datetime.now(timezone.utc)

    # Transition ready_for_review → under_review on first save.
    if job.status == "ready_for_review":
        job_repo.update_job_status(db, job, "under_review", now, reviewed_by=data.reviewed_by)
        job_repo.add_status_history(db, job.job_id, "ready_for_review", "under_review", data.reviewed_by, "Review started", now)
    else:
        # Already under_review — just update reviewed_by and updated_at.
        if data.reviewed_by is not None:
            job.reviewed_by = data.reviewed_by
        job.updated_at = now
        db.flush()

    # Write only the sections that are present in the request.
    if data.overview is not None:
        review_repo.upsert_review_overview(
            db, job.job_id,
            data.overview.model_dump(exclude_unset=False),
            now,
        )

    if data.description is not None:
        review_repo.upsert_review_description(
            db, job.job_id,
            data.description.model_dump(exclude_unset=False),
            now,
        )

    if data.specifications is not None:
        review_repo.upsert_review_specifications(
            db, job.job_id,
            data.specifications.model_dump(exclude_unset=False),
            now,
        )

    if data.accessories is not None:
        review_repo.upsert_review_accessories(
            db, job.job_id,
            data.accessories.model_dump(exclude_unset=False),
            now,
        )

    # Re-fetch all four sections and return the current state.
    r_overview = review_repo.get_review_overview(db, job.job_id)
    r_description = review_repo.get_review_description(db, job.job_id)
    r_specifications = review_repo.get_review_specifications(db, job.job_id)
    r_accessories = review_repo.get_review_accessories(db, job.job_id)

    return ReviewContent(
        overview=ReviewOverview.model_validate(r_overview) if r_overview else None,
        description=ReviewDescription.model_validate(r_description) if r_description else None,
        specifications=ReviewSpecifications.model_validate(r_specifications) if r_specifications else None,
        accessories=ReviewAccessories.model_validate(r_accessories) if r_accessories else None,
    )
