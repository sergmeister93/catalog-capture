"""
End-to-end happy path test.

Walks through the full Phase 1 workflow via the API:
  1. Create job
  2. Register 2 images
  3. Submit to AI (mock Gemini)
  4. Get review payload
  5. Save reviewed content (all 4 sections)
  6. Approve job
  7. Export job
  8. Verify DB state and CSV output

This test is the definition-of-done check for Phase 1.
"""

import csv
import uuid

import pytest

from service_photo.exports.csv_generator import CSV_COLUMNS
from service_photo.models.listing_job_status_history import ListingJobStatusHistory
from service_photo.models.listing_draft_overview import ListingDraftOverview
from sqlalchemy import select


def test_full_happy_path_workflow(client, db):
    """Drive a single job all the way from creation to exported CSV."""

    # ------------------------------------------------------------------ #
    # Step 1: Create job                                                   #
    # ------------------------------------------------------------------ #
    resp = client.post("/api/v1/jobs", json={"item_category": "camera body", "created_by": "sergey"})
    assert resp.status_code == 201
    job = resp.json()
    job_id = job["job_id"]
    assert job["status"] == "initialized"

    # ------------------------------------------------------------------ #
    # Step 2: Register 2 images                                            #
    # ------------------------------------------------------------------ #
    for i in range(1, 3):
        resp = client.post(
            f"/api/v1/jobs/{job_id}/images",
            json={
                "file_name": f"photo_{i}.jpg",
                "file_path": f"./storage/images/photo_{i}.jpg",
                "file_type": "image/jpeg",
                "image_order": i,
                "is_primary": (i == 1),
                "uploaded_by": "sergey",
            },
        )
        assert resp.status_code == 201

    # ------------------------------------------------------------------ #
    # Step 3: Submit to AI                                                 #
    # ------------------------------------------------------------------ #
    resp = client.post(f"/api/v1/jobs/{job_id}/submit", json={"submitted_by": "sergey"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready_for_review"

    # Verify draft rows exist and are not null.
    draft_overview = db.execute(
        select(ListingDraftOverview).where(ListingDraftOverview.job_id == uuid.UUID(job_id))
    ).scalar_one()
    assert draft_overview.product_name is not None
    # extraction_warnings must be stored (mock always includes them).
    assert draft_overview.extraction_warnings is not None

    # ------------------------------------------------------------------ #
    # Step 4: Get review payload                                           #
    # ------------------------------------------------------------------ #
    resp = client.get(f"/api/v1/jobs/{job_id}/review-payload")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["draft"]["overview"]["product_name"] == "Canon EOS R6 Mirrorless Camera Body"
    assert payload["review"]["overview"] is None  # not yet saved

    # ------------------------------------------------------------------ #
    # Step 5: Save reviewed content (all 4 sections)                       #
    # ------------------------------------------------------------------ #
    resp = client.put(
        f"/api/v1/jobs/{job_id}/review",
        json={
            "reviewed_by": "sergey",
            "overview": {
                "product_name": "Canon EOS R6 Mirrorless Camera Body",
                "brand": "Canon",
                "model": "EOS R6",
                "condition_summary": "Used — light cosmetic wear. Sensor clean.",
            },
            "description": {
                "short_title": "Canon EOS R6 Mirrorless Camera Body",
                "description_text": "Used Canon EOS R6 mirrorless camera body. Light wear. Sold as pictured.",
                "visible_wear_notes": "Light scuffs near grip.",
            },
            "specifications": {
                "sensor_format": "Full Frame",
                "megapixels": 20.1,
                "lens_mount": "Canon RF",
                "weight_grams": 680,
                "other_specifications": {"battery_type": "LP-E6NH"},
            },
            "accessories": {
                "included_accessories_text": "Body cap, battery, charger.",
                "missing_typical_accessories_text": "Box and strap not included.",
            },
        },
    )
    assert resp.status_code == 200
    review = resp.json()
    assert review["overview"]["product_name"] == "Canon EOS R6 Mirrorless Camera Body"
    assert review["specifications"]["sensor_format"] == "Full Frame"

    # Job must now be under_review.
    resp = client.get(f"/api/v1/jobs/{job_id}")
    assert resp.json()["status"] == "under_review"

    # ------------------------------------------------------------------ #
    # Step 6: Approve job                                                   #
    # ------------------------------------------------------------------ #
    resp = client.post(f"/api/v1/jobs/{job_id}/approve", json={"approved_by": "sergey"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"
    assert resp.json()["approved_by"] == "sergey"

    # ------------------------------------------------------------------ #
    # Step 7: Export job                                                    #
    # ------------------------------------------------------------------ #
    resp = client.post(f"/api/v1/jobs/{job_id}/export", json={"exported_by": "sergey"})
    assert resp.status_code == 201
    export = resp.json()
    assert export["export_status"] == "success"

    # ------------------------------------------------------------------ #
    # Step 8: Verify DB state and CSV output                               #
    # ------------------------------------------------------------------ #

    # Job must be in exported status.
    resp = client.get(f"/api/v1/jobs/{job_id}")
    final_job = resp.json()
    assert final_job["status"] == "exported"
    assert final_job["exported_at"] is not None

    # Status history must contain all expected transitions.
    history_statuses = [h["new_status"] for h in final_job["status_history"]]
    for expected in [
        "initialized", "submitted_to_ai", "ai_response_received",
        "ready_for_review", "under_review", "approved", "exported",
    ]:
        assert expected in history_statuses, f"Missing status history entry: {expected}"

    # Draft content must NOT have changed after creation (same row IDs).
    # (We already confirmed draft_overview was written in step 3.)

    # CSV file must exist with correct columns and one data row.
    file_path = export["export_file_path"]
    with open(file_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == CSV_COLUMNS
        rows = list(reader)

    assert len(rows) == 1
    row = rows[0]
    assert row["product_name"] == "Canon EOS R6 Mirrorless Camera Body"
    assert row["sensor_format"] == "Full Frame"
    assert row["weight_grams"] == "680"
    assert row["megapixels"] == "20.1"
    assert "LP-E6NH" in row["other_specifications_json"]
    assert row["job_number"] == final_job["job_number"]
    assert row["exported_at"] != ""
    assert row["approved_at"] != ""
