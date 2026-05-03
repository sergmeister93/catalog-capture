"""
Review payload assembly service.

Handles GET /jobs/{job_id}/review-payload: fetches job, images, all four draft
sections, and all four review sections, then returns a ReviewPayload schema.
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from service_photo.models.listing_job import ListingJob
from service_photo.repositories import images as image_repo
from service_photo.repositories import draft as draft_repo
from service_photo.repositories import review as review_repo
from service_photo.schemas.jobs import ListingJob as ListingJobSchema, ListingJobImage as ListingJobImageSchema
from service_photo.schemas.draft import DraftContent, DraftOverview, DraftDescription, DraftSpecifications, DraftAccessories
from service_photo.schemas.review import ReviewContent, ReviewOverview, ReviewDescription, ReviewSpecifications, ReviewAccessories, ReviewPayload

# Statuses that allow review payload retrieval.
REVIEW_ELIGIBLE_STATUSES = {"ready_for_review", "under_review", "approved", "exported"}


def get_review_payload(db: Session, job: ListingJob) -> ReviewPayload:
    """
    Assemble and return the full ReviewPayload for the given job.

    Raises HTTPException 409 if the job is not in a review-eligible status.
    """
    if job.status not in REVIEW_ELIGIBLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail={"error": "job_not_ready_for_review", "message": f"Job must be in ready_for_review, under_review, approved, or exported status. Current: '{job.status}'."},
        )

    images = image_repo.get_images_for_job(db, job.job_id)

    # Fetch each draft section (any may be None before submit completes).
    d_overview = draft_repo.get_draft_overview(db, job.job_id)
    d_description = draft_repo.get_draft_description(db, job.job_id)
    d_specifications = draft_repo.get_draft_specifications(db, job.job_id)
    d_accessories = draft_repo.get_draft_accessories(db, job.job_id)

    # Fetch each review section (any may be None before reviewer saves).
    r_overview = review_repo.get_review_overview(db, job.job_id)
    r_description = review_repo.get_review_description(db, job.job_id)
    r_specifications = review_repo.get_review_specifications(db, job.job_id)
    r_accessories = review_repo.get_review_accessories(db, job.job_id)

    return ReviewPayload(
        job=ListingJobSchema.model_validate(job),
        images=[ListingJobImageSchema.model_validate(img) for img in images],
        draft=DraftContent(
            overview=DraftOverview.model_validate(d_overview) if d_overview else None,
            description=DraftDescription.model_validate(d_description) if d_description else None,
            specifications=DraftSpecifications.model_validate(d_specifications) if d_specifications else None,
            accessories=DraftAccessories.model_validate(d_accessories) if d_accessories else None,
        ),
        review=ReviewContent(
            overview=ReviewOverview.model_validate(r_overview) if r_overview else None,
            description=ReviewDescription.model_validate(r_description) if r_description else None,
            specifications=ReviewSpecifications.model_validate(r_specifications) if r_specifications else None,
            accessories=ReviewAccessories.model_validate(r_accessories) if r_accessories else None,
        ),
    )
