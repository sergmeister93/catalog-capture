"""Integration tests for POST /jobs/{job_id}/export."""

import csv
import os
import pytest
from pathlib import Path

from tests.fixtures.factories import scenario_f_approved, scenario_g_exported
from service_photo.exports.csv_generator import CSV_COLUMNS


def test_export_approved_job_returns_201(client, db):
    """POST /export on an approved job returns 201 with the export record."""
    job = scenario_f_approved(db)
    db.flush()

    resp = client.post(
        f"/api/v1/jobs/{job.job_id}/export",
        json={"exported_by": "sergey"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["export_type"] == "csv"
    assert data["export_status"] == "success"
    assert data["exported_by"] == "sergey"
    assert data["job_id"] == str(job.job_id)


def test_export_transitions_job_to_exported(client, db):
    """Job status must be 'exported' after a successful export call."""
    job = scenario_f_approved(db)
    db.flush()

    client.post(f"/api/v1/jobs/{job.job_id}/export", json={})

    db.refresh(job)
    assert job.status == "exported"
    assert job.exported_at is not None


def test_export_csv_column_order_matches_spec(client, db):
    """The generated CSV file must have columns in the exact order from the spec."""
    job = scenario_f_approved(db)
    db.flush()

    resp = client.post(f"/api/v1/jobs/{job.job_id}/export", json={"exported_by": "tester"})
    assert resp.status_code == 201
    file_path = resp.json()["export_file_path"]

    # Read the CSV and check the header row.
    with open(file_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        actual_columns = reader.fieldnames

    assert actual_columns == CSV_COLUMNS


def test_export_csv_has_one_data_row(client, db):
    """The exported CSV must have exactly one data row (Phase 1 is one job per file)."""
    job = scenario_f_approved(db)
    db.flush()

    resp = client.post(f"/api/v1/jobs/{job.job_id}/export", json={})
    file_path = resp.json()["export_file_path"]

    with open(file_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 1
    assert rows[0]["job_number"] == job.job_number


def test_export_wrong_status_returns_409(client, db):
    """POST /export on a job that is not approved returns 409."""
    from tests.fixtures.factories import scenario_a_initialized
    job = scenario_a_initialized(db)
    db.flush()

    resp = client.post(f"/api/v1/jobs/{job.job_id}/export", json={})
    assert resp.status_code == 409
    assert resp.json()["error"] == "invalid_status_for_export"


def test_export_creates_status_history_row(client, db):
    """Export must insert an approved → exported history row."""
    from sqlalchemy import select
    from service_photo.models.listing_job_status_history import ListingJobStatusHistory

    job = scenario_f_approved(db)
    db.flush()
    before = db.execute(select(ListingJobStatusHistory).where(ListingJobStatusHistory.job_id == job.job_id)).scalars().all()

    client.post(f"/api/v1/jobs/{job.job_id}/export", json={})

    after = db.execute(select(ListingJobStatusHistory).where(ListingJobStatusHistory.job_id == job.job_id)).scalars().all()
    assert len(after) == len(before) + 1

    last = max(after, key=lambda r: r.changed_at)
    assert last.old_status == "approved"
    assert last.new_status == "exported"


def test_export_payload_snapshot_populated(client, db):
    """listing_exports.export_payload_snapshot must be non-null and contain job data."""
    from sqlalchemy import select
    from service_photo.models.listing_exports import ListingExport as ListingExportORM

    job = scenario_f_approved(db)
    db.flush()

    resp = client.post(f"/api/v1/jobs/{job.job_id}/export", json={})
    export_id = resp.json()["export_id"]

    import uuid
    row = db.get(ListingExportORM, uuid.UUID(export_id))
    assert row.export_payload_snapshot is not None
    assert "job" in row.export_payload_snapshot
    assert row.export_payload_snapshot["job"]["job_number"] == job.job_number


def test_export_does_not_read_draft_tables(client, db):
    """
    Verify that the exported CSV values come from review tables, not draft tables.
    We know draft product_name is 'Canon EOS R6 Mirrorless Camera Body' and
    review product_name is the same (in scenario_f), but we can assert the
    export_payload_snapshot has no draft-specific keys.
    """
    job = scenario_f_approved(db)
    db.flush()

    resp = client.post(f"/api/v1/jobs/{job.job_id}/export", json={})
    snapshot = resp.json()["export_payload_snapshot"]

    # Snapshot must reference 'review' key, not 'draft'.
    assert "review" in snapshot
    assert "draft" not in snapshot
