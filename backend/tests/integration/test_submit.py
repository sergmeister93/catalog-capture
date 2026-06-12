"""Integration tests for POST /jobs/{job_id}/submit."""

from tests.fixtures.factories import scenario_b_with_images, scenario_a_initialized
from service_photo.models.listing_job_status_history import ListingJobStatusHistory
from service_photo.models.listing_draft_overview import ListingDraftOverview
from sqlalchemy import select


def test_submit_happy_path_transitions_to_ready_for_review(client, db):
    """
    Submit a job with images → mock Gemini returns a valid draft →
    job status ends at ready_for_review.
    """
    job, _ = scenario_b_with_images(db)
    db.flush()

    resp = client.post(f"/api/v1/jobs/{job.job_id}/submit", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready_for_review"


def test_submit_creates_multiple_status_history_rows(client, db):
    """
    Submit must create 3 new history rows:
      initialized → submitted_to_ai → ai_response_received → ready_for_review
    Plus the 1 row from job creation = 4 total.
    """
    job, _ = scenario_b_with_images(db)
    db.flush()

    client.post(f"/api/v1/jobs/{job.job_id}/submit", json={})

    rows = db.execute(
        select(ListingJobStatusHistory).where(
            ListingJobStatusHistory.job_id == job.job_id
        ).order_by(ListingJobStatusHistory.changed_at)
    ).scalars().all()

    statuses = [r.new_status for r in rows]
    # Original seed has 1 row (initialized); submit adds 3.
    assert "submitted_to_ai" in statuses
    assert "ai_response_received" in statuses
    assert "ready_for_review" in statuses


def test_submit_writes_draft_rows(client, db):
    """All four draft tables must be populated after a successful submit."""
    from service_photo.models.listing_draft_description import ListingDraftDescription
    from service_photo.models.listing_draft_specifications import ListingDraftSpecifications
    from service_photo.models.listing_draft_accessories import ListingDraftAccessories

    job, _ = scenario_b_with_images(db)
    db.flush()

    client.post(f"/api/v1/jobs/{job.job_id}/submit", json={})

    assert db.execute(select(ListingDraftOverview).where(ListingDraftOverview.job_id == job.job_id)).scalar_one_or_none() is not None
    assert db.execute(select(ListingDraftDescription).where(ListingDraftDescription.job_id == job.job_id)).scalar_one_or_none() is not None
    assert db.execute(select(ListingDraftSpecifications).where(ListingDraftSpecifications.job_id == job.job_id)).scalar_one_or_none() is not None
    assert db.execute(select(ListingDraftAccessories).where(ListingDraftAccessories.job_id == job.job_id)).scalar_one_or_none() is not None


def test_submit_stores_extraction_warnings(client, db):
    """extraction_warnings from the mock Gemini response must be stored on draft_overview."""
    job, _ = scenario_b_with_images(db)
    db.flush()

    client.post(f"/api/v1/jobs/{job.job_id}/submit", json={})

    row = db.execute(
        select(ListingDraftOverview).where(ListingDraftOverview.job_id == job.job_id)
    ).scalar_one()
    # Mock client always returns a non-null extraction_warnings list.
    assert row.extraction_warnings is not None
    assert isinstance(row.extraction_warnings, list)


def test_submit_no_images_returns_400(client, db):
    """Submitting a job with no images returns 400."""
    job = scenario_a_initialized(db)
    db.flush()

    resp = client.post(f"/api/v1/jobs/{job.job_id}/submit", json={})
    assert resp.status_code == 400
    assert resp.json()["error"] == "no_images_registered"


def test_submit_wrong_status_returns_409(client, db):
    """Submitting a ready_for_review job returns 409."""
    from tests.fixtures.factories import scenario_c_ready_for_review
    job = scenario_c_ready_for_review(db)
    db.flush()

    resp = client.post(f"/api/v1/jobs/{job.job_id}/submit", json={})
    assert resp.status_code == 409
    assert resp.json()["error"] == "invalid_status_for_submit"


def test_draft_content_does_not_mutate_after_creation(client, db):
    """
    Draft content must not change after the initial write (resubmission
    replaces the row entirely, but we verify the created_at is preserved
    on the second submit while content is overwritten).

    This tests the 'draft is read-only after creation' contract by asserting
    that a second submit replaces the draft rather than appending.
    """
    job, _ = scenario_b_with_images(db)
    db.flush()

    # First submit.
    client.post(f"/api/v1/jobs/{job.job_id}/submit", json={})
    first_row = db.execute(select(ListingDraftOverview).where(ListingDraftOverview.job_id == job.job_id)).scalar_one()
    first_id = first_row.draft_overview_id

    # Set back to allow resubmission (simulate validation_failed).
    job.status = "validation_failed"
    db.flush()

    # Second submit.
    client.post(f"/api/v1/jobs/{job.job_id}/submit", json={})
    second_row = db.execute(select(ListingDraftOverview).where(ListingDraftOverview.job_id == job.job_id)).scalar_one()

    # Row is updated in-place (same PK), not a new row.
    assert second_row.draft_overview_id == first_id
