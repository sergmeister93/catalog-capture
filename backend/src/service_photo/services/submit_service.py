"""
Submit-to-AI service.

Handles POST /jobs/{job_id}/submit: validates preconditions, drives the full
Gemini submission workflow including status transitions and draft upserts.

Status flow:
  initialized (or validation_failed / ai_error)
    → submitted_to_ai
    → ai_response_received
    → ready_for_review   (on validation success)
      OR validation_failed  (on schema validation failure)
    → ai_error            (on Gemini API failure)
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
from fastapi import HTTPException
from sqlalchemy.orm import Session

from service_photo.integrations import get_gemini_client
from service_photo.integrations.gemini_interface import GeminiClientError
from service_photo.models.listing_job import ListingJob
from service_photo.repositories import images as image_repo
from service_photo.repositories import jobs as job_repo
from service_photo.repositories import draft as draft_repo

# Statuses from which submit is allowed.
SUBMITTABLE_STATUSES = {"initialized", "validation_failed", "ai_error"}

# Load Gemini response JSON Schema for validation.
_SCHEMA_PATH = Path(__file__).parent.parent.parent.parent.parent.parent / "contracts" / "gemini_response_schema.json"


def _load_gemini_schema() -> dict:
    """Load the Gemini response schema from the contracts directory."""
    # Walk up from this file to the project root and find contracts/.
    current = Path(__file__).resolve()
    for _ in range(10):
        candidate = current.parent / "contracts" / "gemini_response_schema.json"
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
        current = current.parent
    raise FileNotFoundError("gemini_response_schema.json not found in any parent directory.")


_GEMINI_SCHEMA = _load_gemini_schema()


def _load_prompt() -> str:
    """Load the extraction prompt text from the prompts directory."""
    prompt_path = Path(__file__).parent.parent / "prompts" / "listing_extraction_v1.md"
    return prompt_path.read_text(encoding="utf-8")


def submit_job_to_ai(
    db: Session,
    job: ListingJob,
    submitted_by: str | None,
) -> ListingJob:
    """
    Drive the full Gemini submission workflow for one job.

    All intermediate status transitions are persisted before calling Gemini
    so the job's status accurately reflects the in-progress state.

    Returns the updated ListingJob regardless of success or failure path.
    """
    if job.status not in SUBMITTABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail={"error": "invalid_status_for_submit", "message": f"Job must be in an initial or retriable status to submit. Current: '{job.status}'."},
        )

    images = image_repo.get_images_for_job(db, job.job_id)
    if not images:
        raise HTTPException(
            status_code=400,
            detail={"error": "no_images_registered", "message": "Job has no registered images. Register at least one image before submitting."},
        )

    now = datetime.now(timezone.utc)
    old_status = job.status

    # ---- Step 1: transition → submitted_to_ai ----
    job_repo.update_job_status(db, job, "submitted_to_ai", now)
    job_repo.add_status_history(db, job.job_id, old_status, "submitted_to_ai", submitted_by, "Submitted to AI for analysis", now)

    # ---- Step 2: call Gemini ----
    image_paths = [img.file_path for img in images]
    prompt = _load_prompt()
    gemini_client = get_gemini_client()

    try:
        gemini_response = gemini_client.analyse_images(image_paths, prompt)
    except GeminiClientError as exc:
        # Gemini call failed — record ai_error and surface the job.
        now_err = datetime.now(timezone.utc)
        job_repo.update_job_status(db, job, "ai_error", now_err)
        job_repo.add_status_history(db, job.job_id, "submitted_to_ai", "ai_error", submitted_by, f"Gemini API error: {exc}", now_err)
        return job

    # ---- Step 3: transition → ai_response_received ----
    now_rcvd = datetime.now(timezone.utc)
    job_repo.update_job_status(db, job, "ai_response_received", now_rcvd)
    job_repo.add_status_history(db, job.job_id, "submitted_to_ai", "ai_response_received", submitted_by, "Gemini response received", now_rcvd)

    # ---- Step 4: validate Gemini response schema ----
    try:
        jsonschema.validate(instance=gemini_response, schema=_GEMINI_SCHEMA)
    except jsonschema.ValidationError as exc:
        now_fail = datetime.now(timezone.utc)
        job_repo.update_job_status(db, job, "validation_failed", now_fail)
        job_repo.add_status_history(db, job.job_id, "ai_response_received", "validation_failed", submitted_by, f"Gemini response schema validation failed: {exc.message}", now_fail)
        return job

    # ---- Step 5: upsert all four draft tables ----
    now_draft = datetime.now(timezone.utc)
    overview = gemini_response.get("overview", {})
    description = gemini_response.get("description", {})
    specifications = gemini_response.get("specifications", {})
    accessories = gemini_response.get("accessories", {})

    draft_repo.upsert_draft_overview(db, job.job_id, {
        "product_name": overview.get("product_name"),
        "brand": overview.get("brand"),
        "model": overview.get("model"),
        "product_family": overview.get("product_family"),
        "variant": overview.get("variant"),
        "mount_type": overview.get("mount_type"),
        "serial_number_visible": overview.get("serial_number_visible"),
        "condition_summary": overview.get("condition_summary"),
        "confidence_notes": overview.get("confidence_notes"),
        "extraction_warnings": gemini_response.get("extraction_warnings"),
        "raw_source_payload": gemini_response,
    }, now_draft)

    draft_repo.upsert_draft_description(db, job.job_id, {
        "short_title": description.get("short_title"),
        "description_text": description.get("description_text"),
        "visible_wear_notes": description.get("visible_wear_notes"),
        "key_selling_points": description.get("key_selling_points"),
        "confidence_notes": description.get("confidence_notes"),
    }, now_draft)

    draft_repo.upsert_draft_specifications(db, job.job_id, {
        "sensor_format": specifications.get("sensor_format"),
        "megapixels": specifications.get("megapixels"),
        "lens_mount": specifications.get("lens_mount"),
        "focal_length": specifications.get("focal_length"),
        "aperture": specifications.get("aperture"),
        "iso_range": specifications.get("iso_range"),
        "shutter_range": specifications.get("shutter_range"),
        "video_capabilities": specifications.get("video_capabilities"),
        "storage_media": specifications.get("storage_media"),
        "connectivity": specifications.get("connectivity"),
        "weight_grams": specifications.get("weight_grams"),
        "other_specifications": specifications.get("other_specifications"),
        "confidence_notes": specifications.get("confidence_notes"),
    }, now_draft)

    draft_repo.upsert_draft_accessories(db, job.job_id, {
        "included_accessories_text": accessories.get("included_accessories_text"),
        "inferred_accessories_text": accessories.get("inferred_accessories_text"),
        "missing_typical_accessories_text": accessories.get("missing_typical_accessories_text"),
        "confidence_notes": accessories.get("confidence_notes"),
    }, now_draft)

    # ---- Step 6: transition → ready_for_review ----
    now_ready = datetime.now(timezone.utc)
    job_repo.update_job_status(db, job, "ready_for_review", now_ready)
    job_repo.add_status_history(db, job.job_id, "ai_response_received", "ready_for_review", submitted_by, "Draft content written; job ready for human review", now_ready)

    return job
