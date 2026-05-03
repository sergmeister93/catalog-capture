"""
Seed/factory helpers for all 7 test scenarios defined in
docs/claude_code_seed_data_spec.md.

Each factory function inserts rows directly via the repository layer
(not through the API) so tests can start from a specific known state.

Scenarios:
  A — initialized job (no images, no draft, no review)
  B — job with 3 images (image_order 1/2/3, one primary)
  C — ready_for_review job with full draft content
  D — under_review job with partial review (overview + description only)
  E — under_review job with all review rows but intentionally invalid values
  F — approved job with full valid review rows
  G — exported job with one export record
"""

import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from service_photo.models.listing_job import ListingJob
from service_photo.models.listing_job_image import ListingJobImage
from service_photo.models.listing_job_status_history import ListingJobStatusHistory
from service_photo.models.listing_draft_overview import ListingDraftOverview
from service_photo.models.listing_draft_description import ListingDraftDescription
from service_photo.models.listing_draft_specifications import ListingDraftSpecifications
from service_photo.models.listing_draft_accessories import ListingDraftAccessories
from service_photo.models.listing_review_overview import ListingReviewOverview
from service_photo.models.listing_review_description import ListingReviewDescription
from service_photo.models.listing_review_specifications import ListingReviewSpecifications
from service_photo.models.listing_review_accessories import ListingReviewAccessories
from service_photo.models.listing_exports import ListingExport

# Fixed base time so test timestamps are deterministic and ordered.
_BASE = datetime(2026, 4, 19, 12, 0, 0, tzinfo=timezone.utc)


def _t(offset_seconds: int = 0) -> datetime:
    return _BASE + timedelta(seconds=offset_seconds)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _add_job(
    db: Session,
    job_number: str,
    status: str,
    item_category: str = "camera body",
    created_by: str | None = "test_user",
    approved_by: str | None = None,
    approved_at: datetime | None = None,
    exported_at: datetime | None = None,
    reviewed_by: str | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> ListingJob:
    job = ListingJob(
        job_id=uuid.uuid4(),
        job_number=job_number,
        status=status,
        item_category=item_category,
        created_by=created_by,
        approved_by=approved_by,
        approved_at=approved_at,
        exported_at=exported_at,
        reviewed_by=reviewed_by,
        is_reviews_enriched=False,
        is_price_enriched=False,
        created_at=created_at or _t(0),
        updated_at=updated_at or _t(0),
    )
    db.add(job)
    db.flush()
    return job


def _add_status_history(db: Session, job_id: uuid.UUID, entries: list[tuple]) -> None:
    """entries = list of (old_status, new_status, offset_seconds)"""
    for old, new, offset in entries:
        db.add(ListingJobStatusHistory(
            status_history_id=uuid.uuid4(),
            job_id=job_id,
            old_status=old,
            new_status=new,
            changed_at=_t(offset),
            changed_by="test_user",
            change_reason="factory seed",
        ))
    db.flush()


def _add_images(db: Session, job_id: uuid.UUID, count: int = 3) -> list[ListingJobImage]:
    images = []
    for i in range(1, count + 1):
        img = ListingJobImage(
            image_id=uuid.uuid4(),
            job_id=job_id,
            file_name=f"image_{i:02d}.jpg",
            file_path=f"./storage/images/test_{job_id}_{i}.jpg",
            file_type="image/jpeg",
            file_size_bytes=204800 * i,
            image_order=i,
            is_primary=(i == 1),
            uploaded_at=_t(10 + i),
            uploaded_by="test_user",
        )
        db.add(img)
        images.append(img)
    db.flush()
    return images


def _add_draft(db: Session, job_id: uuid.UUID) -> None:
    db.add(ListingDraftOverview(
        draft_overview_id=uuid.uuid4(), job_id=job_id,
        product_name="Canon EOS R6 Mirrorless Camera Body",
        brand="Canon", model="EOS R6", product_family="EOS R",
        variant=None, mount_type="Canon RF", serial_number_visible=None,
        condition_summary="Used body with light cosmetic wear.",
        confidence_notes="Brand confirmed by visible markings.",
        extraction_warnings=["Serial number not visible."],
        raw_source_payload={"schema_version": "1.0"},
        created_at=_t(30),
    ))
    db.add(ListingDraftDescription(
        draft_description_id=uuid.uuid4(), job_id=job_id,
        short_title="Canon EOS R6 Mirrorless Camera Body",
        description_text="Used Canon EOS R6 body. Light wear. Sold as pictured.",
        visible_wear_notes="Light surface wear near grip and rear dial.",
        key_selling_points="Full-frame mirrorless. Canon RF mount.",
        confidence_notes="Condition based on visible surfaces only.",
        created_at=_t(30),
    ))
    db.add(ListingDraftSpecifications(
        draft_specifications_id=uuid.uuid4(), job_id=job_id,
        sensor_format="Full Frame", megapixels=20.1, lens_mount="Canon RF",
        iso_range="100-102400", shutter_range="30s to 1/8000s",
        video_capabilities="4K UHD up to 60fps",
        storage_media="SD / CFexpress Type B",
        connectivity="Wi-Fi, Bluetooth", weight_grams=680,
        other_specifications={"battery_type": "LP-E6NH"},
        confidence_notes="Specs from Canon published data.",
        created_at=_t(30),
    ))
    db.add(ListingDraftAccessories(
        draft_accessories_id=uuid.uuid4(), job_id=job_id,
        included_accessories_text="Body cap, battery.",
        inferred_accessories_text="LP-E6NH battery and charger likely included.",
        missing_typical_accessories_text="Box and strap not visible.",
        confidence_notes="Based on visible items only.",
        created_at=_t(30),
    ))
    db.flush()


def _add_valid_review(db: Session, job_id: uuid.UUID) -> None:
    db.add(ListingReviewOverview(
        review_overview_id=uuid.uuid4(), job_id=job_id,
        product_name="Canon EOS R6 Mirrorless Camera Body",
        brand="Canon", model="EOS R6", product_family="EOS R",
        condition_summary="Used — light cosmetic wear. Sensor clean.",
        last_edited_at=_t(60), last_edited_by="reviewer",
    ))
    db.add(ListingReviewDescription(
        review_description_id=uuid.uuid4(), job_id=job_id,
        short_title="Canon EOS R6 Mirrorless Camera Body",
        description_text="Used Canon EOS R6 mirrorless camera body with light cosmetic wear.",
        visible_wear_notes="Light scuffs near grip.",
        key_selling_points="Full-frame sensor, Canon RF mount.",
        last_edited_at=_t(60), last_edited_by="reviewer",
    ))
    db.add(ListingReviewSpecifications(
        review_specifications_id=uuid.uuid4(), job_id=job_id,
        sensor_format="Full Frame", megapixels=20.1, lens_mount="Canon RF",
        iso_range="100-102400", shutter_range="30s to 1/8000s",
        weight_grams=680,
        other_specifications={"battery_type": "LP-E6NH", "screen_size": "3.0 in"},
        last_edited_at=_t(60), last_edited_by="reviewer",
    ))
    db.add(ListingReviewAccessories(
        review_accessories_id=uuid.uuid4(), job_id=job_id,
        included_accessories_text="Body cap, battery, charger.",
        missing_typical_accessories_text="Box and strap not visible.",
        last_edited_at=_t(60), last_edited_by="reviewer",
    ))
    db.flush()


# ---------------------------------------------------------------------------
# Scenario A — Initialized job
# ---------------------------------------------------------------------------
def scenario_a_initialized(db: Session) -> ListingJob:
    """One initialized job. No images, no draft, no review."""
    job = _add_job(db, "JOB-20260419-A01", "initialized")
    _add_status_history(db, job.job_id, [(None, "initialized", 0)])
    return job


# ---------------------------------------------------------------------------
# Scenario B — Job with images
# ---------------------------------------------------------------------------
def scenario_b_with_images(db: Session) -> tuple[ListingJob, list[ListingJobImage]]:
    """Initialized job with 3 images registered (order 1, 2, 3; image 1 is primary)."""
    job = _add_job(db, "JOB-20260419-B01", "initialized")
    _add_status_history(db, job.job_id, [(None, "initialized", 0)])
    images = _add_images(db, job.job_id, count=3)
    return job, images


# ---------------------------------------------------------------------------
# Scenario C — Ready for review
# ---------------------------------------------------------------------------
def scenario_c_ready_for_review(db: Session) -> ListingJob:
    """Job in ready_for_review with full draft content; no review rows yet."""
    job = _add_job(db, "JOB-20260419-C01", "ready_for_review")
    _add_status_history(db, job.job_id, [
        (None, "initialized", 0),
        ("initialized", "submitted_to_ai", 10),
        ("submitted_to_ai", "ai_response_received", 20),
        ("ai_response_received", "ready_for_review", 30),
    ])
    _add_images(db, job.job_id, count=2)
    _add_draft(db, job.job_id)
    return job


# ---------------------------------------------------------------------------
# Scenario D — Under review with partial review rows
# ---------------------------------------------------------------------------
def scenario_d_partial_review(db: Session) -> ListingJob:
    """Under review with overview + description saved; specs + accessories absent."""
    job = _add_job(db, "JOB-20260419-D01", "under_review", reviewed_by="reviewer")
    _add_status_history(db, job.job_id, [
        (None, "initialized", 0),
        ("initialized", "submitted_to_ai", 10),
        ("submitted_to_ai", "ai_response_received", 20),
        ("ai_response_received", "ready_for_review", 30),
        ("ready_for_review", "under_review", 40),
    ])
    _add_images(db, job.job_id, count=2)
    _add_draft(db, job.job_id)

    # Save only overview + description — leave specs and accessories absent.
    db.add(ListingReviewOverview(
        review_overview_id=uuid.uuid4(), job_id=job.job_id,
        product_name="Canon EOS R6 Mirrorless Camera Body",
        brand="Canon", model="EOS R6",
        condition_summary="Used — light cosmetic wear.",
        last_edited_at=_t(60), last_edited_by="reviewer",
    ))
    db.add(ListingReviewDescription(
        review_description_id=uuid.uuid4(), job_id=job.job_id,
        short_title="Canon EOS R6 Mirrorless Camera Body",
        description_text="Used Canon EOS R6 body.",
        last_edited_at=_t(60), last_edited_by="reviewer",
    ))
    db.flush()
    return job


# ---------------------------------------------------------------------------
# Scenario E — Approval failure case
# ---------------------------------------------------------------------------
def scenario_e_approval_failure(db: Session) -> ListingJob:
    """
    Under review with all four review rows present but intentionally invalid:
      - blank product_name
      - blank description_text
      - no meaningful spec field
      - blank included_accessories_text
    Expected: approval returns all 4 failures in one response.
    """
    job = _add_job(db, "JOB-20260419-E01", "under_review")
    _add_status_history(db, job.job_id, [
        (None, "initialized", 0),
        ("initialized", "submitted_to_ai", 10),
        ("submitted_to_ai", "ai_response_received", 20),
        ("ai_response_received", "ready_for_review", 30),
        ("ready_for_review", "under_review", 40),
    ])
    _add_images(db, job.job_id, count=1)
    _add_draft(db, job.job_id)

    db.add(ListingReviewOverview(
        review_overview_id=uuid.uuid4(), job_id=job.job_id,
        product_name="   ",       # blank — triggers OVR-02
        condition_summary="Used", # valid
        last_edited_at=_t(60), last_edited_by="reviewer",
    ))
    db.add(ListingReviewDescription(
        review_description_id=uuid.uuid4(), job_id=job.job_id,
        short_title="Canon EOS R6",  # valid
        description_text="   ",      # blank — triggers DSC-04
        last_edited_at=_t(60), last_edited_by="reviewer",
    ))
    db.add(ListingReviewSpecifications(
        review_specifications_id=uuid.uuid4(), job_id=job.job_id,
        # All qualifying fields left null — triggers SPC-01
        last_edited_at=_t(60), last_edited_by="reviewer",
    ))
    db.add(ListingReviewAccessories(
        review_accessories_id=uuid.uuid4(), job_id=job.job_id,
        included_accessories_text="   ",  # blank — triggers ACC-02
        last_edited_at=_t(60), last_edited_by="reviewer",
    ))
    db.flush()
    return job


# ---------------------------------------------------------------------------
# Scenario F — Approved job
# ---------------------------------------------------------------------------
def scenario_f_approved(db: Session) -> ListingJob:
    """Fully approved job; all review rows valid; no export yet."""
    job = _add_job(
        db, "JOB-20260419-F01", "approved",
        approved_by="reviewer", approved_at=_t(90),
    )
    _add_status_history(db, job.job_id, [
        (None, "initialized", 0),
        ("initialized", "submitted_to_ai", 10),
        ("submitted_to_ai", "ai_response_received", 20),
        ("ai_response_received", "ready_for_review", 30),
        ("ready_for_review", "under_review", 40),
        ("under_review", "approved", 90),
    ])
    _add_images(db, job.job_id, count=2)
    _add_draft(db, job.job_id)
    _add_valid_review(db, job.job_id)
    return job


# ---------------------------------------------------------------------------
# Scenario G — Exported job
# ---------------------------------------------------------------------------
def scenario_g_exported(db: Session) -> tuple[ListingJob, ListingExport]:
    """Exported job with one listing_exports record."""
    export_time = _t(120)
    job = _add_job(
        db, "JOB-20260419-G01", "exported",
        approved_by="reviewer", approved_at=_t(90),
        exported_at=export_time,
    )
    _add_status_history(db, job.job_id, [
        (None, "initialized", 0),
        ("initialized", "submitted_to_ai", 10),
        ("submitted_to_ai", "ai_response_received", 20),
        ("ai_response_received", "ready_for_review", 30),
        ("ready_for_review", "under_review", 40),
        ("under_review", "approved", 90),
        ("approved", "exported", 120),
    ])
    _add_images(db, job.job_id, count=2)
    _add_draft(db, job.job_id)
    _add_valid_review(db, job.job_id)

    export_row = ListingExport(
        export_id=uuid.uuid4(),
        job_id=job.job_id,
        export_type="csv",
        export_file_name=f"service_photo_export_{job.job_number}_20260419T120000Z.csv",
        export_file_path=f"./storage_test/exports/service_photo_export_{job.job_number}_20260419T120000Z.csv",
        exported_at=export_time,
        exported_by="reviewer",
        export_status="success",
        export_payload_snapshot={
            "job": {"job_number": job.job_number},
            "export": {"export_type": "csv", "exported_at": export_time.isoformat()},
        },
    )
    db.add(export_row)
    db.flush()
    return job, export_row
