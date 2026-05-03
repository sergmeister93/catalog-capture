"""
Approval service.

Handles POST /jobs/{job_id}/approve: runs ALL validation rules against the
reviewed content layer, collects every failure in one pass (does not short-
circuit), and either transitions the job to 'approved' or returns all failures.

Rules sourced from contracts/approval_validation_rules.md.
"""

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from service_photo.models.listing_job import ListingJob
from service_photo.repositories import jobs as job_repo
from service_photo.repositories import review as review_repo
from service_photo.schemas.errors import ApprovalValidationError, ValidationFailure

# Qualifying spec fields for SPC-01 (any one must be non-null / non-blank).
_SPEC_TEXT_FIELDS = [
    "sensor_format", "lens_mount", "focal_length", "aperture",
    "iso_range", "shutter_range", "video_capabilities", "storage_media", "connectivity",
]
_SPEC_NUMERIC_FIELDS = ["megapixels", "weight_grams"]


def _is_blank(value: str | None) -> bool:
    """Return True if value is None or whitespace-only."""
    return value is None or not value.strip()


def _run_approval_validation(db: Session, job_id) -> list[ValidationFailure]:
    """
    Run all approval gate rules. Return list of all failures (may be empty).
    Never short-circuits — collects every failure.
    """
    failures: list[ValidationFailure] = []

    # ---- Check: required rows exist ----
    r_overview = review_repo.get_review_overview(db, job_id)
    r_description = review_repo.get_review_description(db, job_id)
    r_specifications = review_repo.get_review_specifications(db, job_id)
    r_accessories = review_repo.get_review_accessories(db, job_id)

    if r_overview is None:
        failures.append(ValidationFailure(rule="missing_review_overview", detail="listing_review_overview row is missing for this job."))
    if r_description is None:
        failures.append(ValidationFailure(rule="missing_review_description", detail="listing_review_description row is missing for this job."))
    if r_specifications is None:
        failures.append(ValidationFailure(rule="missing_review_specifications", detail="listing_review_specifications row is missing for this job."))
    if r_accessories is None:
        failures.append(ValidationFailure(rule="missing_review_accessories", detail="listing_review_accessories row is missing for this job."))

    # ---- Field-level rules (only if rows exist) ----

    if r_overview is not None:
        if r_overview.product_name is None:
            failures.append(ValidationFailure(rule="review_overview.product_name_null", detail="product_name is null in listing_review_overview"))
        elif _is_blank(r_overview.product_name):
            failures.append(ValidationFailure(rule="review_overview.product_name_blank", detail="product_name is blank in listing_review_overview"))

        if r_overview.condition_summary is None:
            failures.append(ValidationFailure(rule="review_overview.condition_summary_null", detail="condition_summary is null in listing_review_overview"))
        elif _is_blank(r_overview.condition_summary):
            failures.append(ValidationFailure(rule="review_overview.condition_summary_blank", detail="condition_summary is blank in listing_review_overview"))

    if r_description is not None:
        if r_description.short_title is None:
            failures.append(ValidationFailure(rule="review_description.short_title_null", detail="short_title is null in listing_review_description"))
        elif _is_blank(r_description.short_title):
            failures.append(ValidationFailure(rule="review_description.short_title_blank", detail="short_title is blank in listing_review_description"))

        if r_description.description_text is None:
            failures.append(ValidationFailure(rule="review_description.description_text_null", detail="description_text is null in listing_review_description"))
        elif _is_blank(r_description.description_text):
            failures.append(ValidationFailure(rule="review_description.description_text_blank", detail="description_text is blank in listing_review_description"))

    if r_specifications is not None:
        # SPC-01: at least one qualifying spec field must be non-null / non-blank.
        has_meaningful_spec = False
        for field in _SPEC_TEXT_FIELDS:
            value = getattr(r_specifications, field, None)
            if value is not None and str(value).strip():
                has_meaningful_spec = True
                break
        if not has_meaningful_spec:
            for field in _SPEC_NUMERIC_FIELDS:
                value = getattr(r_specifications, field, None)
                if value is not None:
                    has_meaningful_spec = True
                    break
        if not has_meaningful_spec:
            failures.append(ValidationFailure(
                rule="review_specifications.no_meaningful_spec",
                detail="No qualifying specification field is populated in listing_review_specifications",
            ))

    if r_accessories is not None:
        if r_accessories.included_accessories_text is None:
            failures.append(ValidationFailure(rule="review_accessories.included_accessories_text_null", detail="included_accessories_text is null in listing_review_accessories"))
        elif _is_blank(r_accessories.included_accessories_text):
            failures.append(ValidationFailure(rule="review_accessories.included_accessories_text_blank", detail="included_accessories_text is blank in listing_review_accessories"))

    return failures


def approve_job(
    db: Session,
    job: ListingJob,
    approved_by: str | None,
) -> ListingJob:
    """
    Run the approval gate and transition the job to 'approved' if all rules pass.

    Raises HTTPException 409 if job is not in under_review.
    Raises HTTPException 400 (with ApprovalValidationError body) if any rules fail.
    Returns the updated ListingJob on success.
    """
    if job.status != "under_review":
        raise HTTPException(
            status_code=409,
            detail={"error": "invalid_status_for_approval", "message": f"Job must be in under_review status to approve. Current: '{job.status}'."},
        )

    failures = _run_approval_validation(db, job.job_id)

    if failures:
        error = ApprovalValidationError(validation_failures=failures)
        raise HTTPException(status_code=400, detail=error.model_dump())

    # All rules passed — transition to approved.
    now = datetime.now(timezone.utc)
    job_repo.update_job_status(db, job, "approved", now, approved_by=approved_by)
    job_repo.add_status_history(db, job.job_id, "under_review", "approved", approved_by, "Approval gate passed", now)

    return job
