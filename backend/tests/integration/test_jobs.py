"""Integration tests for POST /jobs and GET /jobs/{job_id}."""

import pytest
from tests.fixtures.factories import scenario_a_initialized, scenario_b_with_images


def test_create_job_returns_201(client):
    """POST /jobs creates a job and returns HTTP 201 with the job record."""
    resp = client.post("/api/v1/jobs", json={"item_category": "camera body", "created_by": "tester"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "initialized"
    assert data["item_category"] == "camera body"
    assert "job_id" in data
    assert data["job_number"].startswith("JOB-")
    assert data["is_reviews_enriched"] is False
    assert data["is_price_enriched"] is False


def test_create_job_inserts_status_history(client, db):
    """POST /jobs must insert exactly one status history row."""
    from service_photo.models.listing_job_status_history import ListingJobStatusHistory
    from sqlalchemy import select

    resp = client.post("/api/v1/jobs", json={})
    assert resp.status_code == 201
    job_id = resp.json()["job_id"]

    rows = db.execute(
        select(ListingJobStatusHistory).where(
            ListingJobStatusHistory.job_id == job_id
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].old_status is None
    assert rows[0].new_status == "initialized"


def test_get_job_returns_images_and_history(client, db):
    """GET /jobs/{job_id} returns job + images list + status_history list."""
    job, images = scenario_b_with_images(db)
    db.flush()

    resp = client.get(f"/api/v1/jobs/{job.job_id}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["job_id"] == str(job.job_id)
    assert len(data["images"]) == 3
    assert len(data["status_history"]) == 1

    # Images must be ordered by image_order.
    orders = [img["image_order"] for img in data["images"]]
    assert orders == [1, 2, 3]

    # Primary image is first.
    assert data["images"][0]["is_primary"] is True


def test_get_job_not_found(client):
    """GET /jobs/{unknown} returns 404."""
    import uuid
    resp = client.get(f"/api/v1/jobs/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["error"] == "job_not_found"
