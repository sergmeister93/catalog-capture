"""Integration tests for POST /jobs/{job_id}/images."""

import pytest
from tests.fixtures.factories import scenario_a_initialized, scenario_f_approved


def test_register_image_returns_201(client, db):
    """POST /jobs/{job_id}/images registers an image and returns 201."""
    job = scenario_a_initialized(db)
    db.flush()

    resp = client.post(
        f"/api/v1/jobs/{job.job_id}/images",
        json={
            "file_name": "front.jpg",
            "file_path": "./storage/images/front.jpg",
            "file_type": "image/jpeg",
            "image_order": 1,
            "is_primary": True,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["image_order"] == 1
    assert data["is_primary"] is True
    assert data["job_id"] == str(job.job_id)


def test_image_order_conflict_returns_409(client, db):
    """Registering the same image_order twice returns 409."""
    job = scenario_a_initialized(db)
    db.flush()

    payload = {"file_name": "img.jpg", "file_path": "./storage/img.jpg", "file_type": "image/jpeg", "image_order": 1}
    client.post(f"/api/v1/jobs/{job.job_id}/images", json=payload)

    resp = client.post(f"/api/v1/jobs/{job.job_id}/images", json=payload)
    assert resp.status_code == 409
    assert resp.json()["error"] == "image_order_conflict"


def test_terminal_job_rejects_image(client, db):
    """Cannot register an image on an approved job."""
    job = scenario_f_approved(db)
    db.flush()

    resp = client.post(
        f"/api/v1/jobs/{job.job_id}/images",
        json={"file_name": "x.jpg", "file_path": "./x.jpg", "file_type": "image/jpeg", "image_order": 99},
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "job_not_editable"
