"""Integration tests for GET /review-payload and PUT /review."""

import pytest
from tests.fixtures.factories import (
    scenario_c_ready_for_review,
    scenario_d_partial_review,
)


def test_get_review_payload_returns_correct_shape(client, db):
    """GET /review-payload returns job + images + draft (populated) + review (null sections)."""
    job = scenario_c_ready_for_review(db)
    db.flush()

    resp = client.get(f"/api/v1/jobs/{job.job_id}/review-payload")
    assert resp.status_code == 200
    data = resp.json()

    assert "job" in data
    assert "images" in data
    assert "draft" in data
    assert "review" in data

    # Draft sections must be populated.
    assert data["draft"]["overview"] is not None
    assert data["draft"]["description"] is not None
    assert data["draft"]["specifications"] is not None
    assert data["draft"]["accessories"] is not None

    # Review sections must be null (no review saved yet).
    assert data["review"]["overview"] is None
    assert data["review"]["description"] is None
    assert data["review"]["specifications"] is None
    assert data["review"]["accessories"] is None


def test_save_review_transitions_to_under_review(client, db):
    """First review save from ready_for_review must transition job to under_review."""
    job = scenario_c_ready_for_review(db)
    db.flush()

    resp = client.put(
        f"/api/v1/jobs/{job.job_id}/review",
        json={
            "reviewed_by": "reviewer",
            "overview": {
                "product_name": "Canon EOS R6",
                "condition_summary": "Good condition",
            },
        },
    )
    assert resp.status_code == 200

    # Job should now be under_review.
    db.refresh(job)
    assert job.status == "under_review"


def test_partial_save_does_not_wipe_other_sections(client, db):
    """
    Saving only overview must not clear description if it was previously saved.
    Scenario D has overview + description saved; saving only specs must leave
    overview and description intact.
    """
    job = scenario_d_partial_review(db)
    db.flush()

    # Save only specifications.
    resp = client.put(
        f"/api/v1/jobs/{job.job_id}/review",
        json={
            "specifications": {
                "sensor_format": "Full Frame",
                "weight_grams": 680,
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    # Overview and description from Scenario D must still be present.
    assert data["overview"] is not None
    assert data["overview"]["product_name"] == "Canon EOS R6 Mirrorless Camera Body"
    assert data["description"] is not None

    # Specifications must now be present.
    assert data["specifications"] is not None
    assert data["specifications"]["sensor_format"] == "Full Frame"

    # Accessories were never saved — must still be null.
    assert data["accessories"] is None


def test_save_review_no_sections_returns_400(client, db):
    """PUT /review with no sections returns 400."""
    job = scenario_c_ready_for_review(db)
    db.flush()

    resp = client.put(f"/api/v1/jobs/{job.job_id}/review", json={"reviewed_by": "reviewer"})
    assert resp.status_code == 400
    assert resp.json()["error"] == "no_review_sections_provided"


def test_review_payload_wrong_status_returns_409(client, db):
    """GET /review-payload on initialized job returns 409."""
    from tests.fixtures.factories import scenario_a_initialized
    job = scenario_a_initialized(db)
    db.flush()

    resp = client.get(f"/api/v1/jobs/{job.job_id}/review-payload")
    assert resp.status_code == 409
    assert resp.json()["error"] == "job_not_ready_for_review"
