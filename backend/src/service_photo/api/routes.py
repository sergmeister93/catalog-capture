"""
All 8 FastAPI route handlers for the Service Photo POC API.

Base path: /api/v1  (set in main.py via include_router prefix)

Endpoints:
  POST   /jobs
  GET    /jobs/{job_id}
  POST   /jobs/{job_id}/images
  POST   /jobs/{job_id}/submit
  GET    /jobs/{job_id}/review-payload
  PUT    /jobs/{job_id}/review
  POST   /jobs/{job_id}/approve
  POST   /jobs/{job_id}/export
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from service_photo.db.session import get_db
from service_photo.repositories import jobs as job_repo
from service_photo.schemas.jobs import (
    ListingJob,
    ListingJobDetail,
    ListingJobImage,
    StatusHistoryEntry,
    CreateJobInput,
    RegisterImageInput,
    SubmitJobInput,
    ApproveJobInput,
    ExportJobInput,
)
from service_photo.schemas.review import ReviewContent, ReviewPayload, SaveReviewInput
from service_photo.schemas.export import ListingExport
from service_photo.schemas.errors import ErrorResponse, ApprovalValidationError
from service_photo.services import job_service, image_service, submit_service
from service_photo.services import review_payload_service, review_service
from service_photo.services import approval_service, export_service

router = APIRouter()


# ---------------------------------------------------------------------------
# Shared dependency: resolve job_id → ListingJob ORM, 404 on miss
# ---------------------------------------------------------------------------
def _get_job_or_404(job_id: uuid.UUID, db: Session = Depends(get_db)):
    job = job_repo.get_job_by_id(db, job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "job_not_found", "message": f"No job found with id '{job_id}'."},
        )
    return job


# ---------------------------------------------------------------------------
# POST /jobs — Create listing job
# ---------------------------------------------------------------------------
@router.post("/jobs", response_model=ListingJob, status_code=201)
def create_job(
    body: CreateJobInput,
    db: Session = Depends(get_db),
):
    job = job_service.create_listing_job(
        db=db,
        item_category=body.item_category,
        created_by=body.created_by,
        notes=body.notes,
    )
    return ListingJob.model_validate(job)


# ---------------------------------------------------------------------------
# GET /jobs/{job_id} — Get job with images + status history
# ---------------------------------------------------------------------------
@router.get("/jobs/{job_id}", response_model=ListingJobDetail)
def get_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    job = job_repo.get_job_by_id(db, job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "job_not_found", "message": f"No job found with id '{job_id}'."},
        )

    return ListingJobDetail(
        **ListingJob.model_validate(job).model_dump(),
        images=[ListingJobImage.model_validate(img) for img in job.images],
        status_history=[StatusHistoryEntry.model_validate(sh) for sh in job.status_history],
    )


# ---------------------------------------------------------------------------
# POST /jobs/{job_id}/images — Register image
# ---------------------------------------------------------------------------
@router.post("/jobs/{job_id}/images", response_model=ListingJobImage, status_code=201)
def register_image(
    job_id: uuid.UUID,
    body: RegisterImageInput,
    db: Session = Depends(get_db),
):
    job = job_repo.get_job_by_id(db, job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "job_not_found", "message": f"No job found with id '{job_id}'."},
        )

    image = image_service.register_image(db=db, job=job, data=body)
    return ListingJobImage.model_validate(image)


# ---------------------------------------------------------------------------
# POST /jobs/{job_id}/submit — Submit job to AI
# ---------------------------------------------------------------------------
@router.post("/jobs/{job_id}/submit", response_model=ListingJob)
def submit_job(
    job_id: uuid.UUID,
    body: SubmitJobInput | None = None,
    db: Session = Depends(get_db),
):
    job = job_repo.get_job_by_id(db, job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "job_not_found", "message": f"No job found with id '{job_id}'."},
        )

    submitted_by = body.submitted_by if body else None
    job = submit_service.submit_job_to_ai(db=db, job=job, submitted_by=submitted_by)
    return ListingJob.model_validate(job)


# ---------------------------------------------------------------------------
# GET /jobs/{job_id}/review-payload — Get full review payload
# ---------------------------------------------------------------------------
@router.get("/jobs/{job_id}/review-payload", response_model=ReviewPayload)
def get_review_payload(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    job = job_repo.get_job_by_id(db, job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "job_not_found", "message": f"No job found with id '{job_id}'."},
        )

    return review_payload_service.get_review_payload(db=db, job=job)


# ---------------------------------------------------------------------------
# PUT /jobs/{job_id}/review — Save reviewed content
# ---------------------------------------------------------------------------
@router.put("/jobs/{job_id}/review", response_model=ReviewContent)
def save_review(
    job_id: uuid.UUID,
    body: SaveReviewInput,
    db: Session = Depends(get_db),
):
    job = job_repo.get_job_by_id(db, job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "job_not_found", "message": f"No job found with id '{job_id}'."},
        )

    return review_service.save_review_content(db=db, job=job, data=body)


# ---------------------------------------------------------------------------
# POST /jobs/{job_id}/approve — Approve job
# ---------------------------------------------------------------------------
@router.post(
    "/jobs/{job_id}/approve",
    response_model=ListingJob,
    responses={
        400: {"model": ApprovalValidationError},
        409: {"model": ErrorResponse},
    },
)
def approve_job(
    job_id: uuid.UUID,
    body: ApproveJobInput | None = None,
    db: Session = Depends(get_db),
):
    job = job_repo.get_job_by_id(db, job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "job_not_found", "message": f"No job found with id '{job_id}'."},
        )

    approved_by = body.approved_by if body else None
    job = approval_service.approve_job(db=db, job=job, approved_by=approved_by)
    return ListingJob.model_validate(job)


# ---------------------------------------------------------------------------
# POST /jobs/{job_id}/export — Export approved job
# ---------------------------------------------------------------------------
@router.post("/jobs/{job_id}/export", response_model=ListingExport, status_code=201)
def export_job(
    job_id: uuid.UUID,
    body: ExportJobInput | None = None,
    db: Session = Depends(get_db),
):
    job = job_repo.get_job_by_id(db, job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "job_not_found", "message": f"No job found with id '{job_id}'."},
        )

    exported_by = body.exported_by if body else None
    return export_service.export_job(db=db, job=job, exported_by=exported_by)
