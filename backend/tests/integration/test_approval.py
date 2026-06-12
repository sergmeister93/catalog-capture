"""Integration tests for POST /jobs/{job_id}/approve."""

from tests.fixtures.factories import scenario_e_approval_failure, scenario_f_approved


def test_approve_valid_job_returns_200(client, db):
    """
    POST /approve on a fully reviewed, valid job returns 200 and approved status.
    We set the scenario_f job back to under_review to exercise the endpoint.
    """
    job = scenario_f_approved(db)
    job.status = "under_review"
    job.approved_at = None
    db.flush()

    resp = client.post(
        f"/api/v1/jobs/{job.job_id}/approve",
        json={"approved_by": "sergey"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "approved"
    assert data["approved_by"] == "sergey"
    assert data["approved_at"] is not None


def test_approve_invalid_returns_400_with_all_failures(client, db):
    """
    POST /approve on scenario_e (all sections invalid) must return HTTP 400
    with ALL failing rule IDs in a single response (not just the first).
    """
    job = scenario_e_approval_failure(db)
    db.flush()

    resp = client.post(f"/api/v1/jobs/{job.job_id}/approve", json={})
    assert resp.status_code == 400
    data = resp.json()

    assert data["error"] == "approval_validation_failed"
    assert "validation_failures" in data
    rule_ids = {f["rule"] for f in data["validation_failures"]}

    assert "review_overview.product_name_blank" in rule_ids
    assert "review_description.description_text_blank" in rule_ids
    assert "review_specifications.no_meaningful_spec" in rule_ids
    assert "review_accessories.included_accessories_text_blank" in rule_ids


def test_approve_does_not_change_status_on_failure(client, db):
    """Job must remain under_review when approval fails."""
    job = scenario_e_approval_failure(db)
    db.flush()

    client.post(f"/api/v1/jobs/{job.job_id}/approve", json={})

    db.refresh(job)
    assert job.status == "under_review"


def test_approve_wrong_status_returns_409(client, db):
    """POST /approve on an initialized job returns 409."""
    from tests.fixtures.factories import scenario_a_initialized
    job = scenario_a_initialized(db)
    db.flush()

    resp = client.post(f"/api/v1/jobs/{job.job_id}/approve", json={})
    assert resp.status_code == 409
    assert resp.json()["error"] == "invalid_status_for_approval"


def test_approve_creates_status_history_row(client, db):
    """Approval must insert under_review → approved history row."""
    from sqlalchemy import select
    from service_photo.models.listing_job_status_history import ListingJobStatusHistory

    job = scenario_f_approved(db)
    job.status = "under_review"
    job.approved_at = None
    db.flush()
    history_count_before = db.execute(
        select(ListingJobStatusHistory).where(ListingJobStatusHistory.job_id == job.job_id)
    ).scalars().all()

    client.post(f"/api/v1/jobs/{job.job_id}/approve", json={})

    history_count_after = db.execute(
        select(ListingJobStatusHistory).where(ListingJobStatusHistory.job_id == job.job_id)
    ).scalars().all()

    assert len(history_count_after) == len(history_count_before) + 1
    last_row = max(history_count_after, key=lambda r: r.changed_at)
    assert last_row.old_status == "under_review"
    assert last_row.new_status == "approved"
