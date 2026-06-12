"""
Tests for the extraction job lifecycle: start, poll, the single-active-run
lock (409), and failure handling. The actual Gemini work is monkeypatched —
these tests exercise the job registry and threading glue, not the API call.
"""

import threading
import time

from service_photo.api import inbound_routes
from service_photo.services.inbound_extraction import ExtractionSummary

from .conftest import JPEG_BYTES

EXTRACT_URL = "/api/v1/inbound/extract"


def _seed_images(data_dirs, count=2):
    for i in range(count):
        (data_dirs["input_images"] / f"img{i}.jpg").write_bytes(JPEG_BYTES)


def _fake_summary(model="fake-model"):
    return ExtractionSummary(
        total=2, succeeded=2, failed=0,
        run_timestamp="2026-06-12T00-00-00Z", model=model,
    )


def _wait_for_status(client, job_id, wanted, timeout_s=5.0):
    """Poll the status endpoint until the job reaches `wanted` or timeout."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        body = client.get(f"{EXTRACT_URL}/{job_id}").json()
        if body["status"] == wanted:
            return body
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} never reached status {wanted!r}; last: {body}")


class TestStartExtraction:
    def test_no_images_400(self, inbound_client):
        r = inbound_client.post(EXTRACT_URL, json={})
        assert r.status_code == 400
        assert r.json()["error"] == "no_images_found"

    def test_happy_path_completes(self, inbound_client, data_dirs, monkeypatch):
        _seed_images(data_dirs)
        monkeypatch.setattr(inbound_routes, "run_extraction", lambda **kw: _fake_summary())

        r = inbound_client.post(EXTRACT_URL, json={"batch_name": "test batch"})
        assert r.status_code == 202
        body = r.json()
        assert body["status"] == "queued"
        assert body["total"] == 2

        done = _wait_for_status(inbound_client, body["job_id"], "completed")
        assert done["model"] == "fake-model"
        assert done["finished_at_utc"] is not None
        assert done["current_image"] is None

    def test_unknown_job_404(self, inbound_client):
        r = inbound_client.get(f"{EXTRACT_URL}/deadbeef")
        assert r.status_code == 404

    def test_failure_marks_job_failed(self, inbound_client, data_dirs, monkeypatch):
        _seed_images(data_dirs)

        def boom(**kwargs):
            raise FileNotFoundError("prompt template missing")

        monkeypatch.setattr(inbound_routes, "run_extraction", boom)
        r = inbound_client.post(EXTRACT_URL, json={})
        failed = _wait_for_status(inbound_client, r.json()["job_id"], "failed")
        assert "prompt template missing" in failed["error"]


class TestSingleActiveRunLock:
    def test_second_start_while_running_409(self, inbound_client, data_dirs, monkeypatch):
        _seed_images(data_dirs)

        release = threading.Event()

        def slow_run(**kwargs):
            # Hold the job in "running" until the test releases it.
            assert release.wait(timeout=10), "test never released the fake run"
            return _fake_summary()

        monkeypatch.setattr(inbound_routes, "run_extraction", slow_run)

        first = inbound_client.post(EXTRACT_URL, json={})
        assert first.status_code == 202

        try:
            second = inbound_client.post(EXTRACT_URL, json={})
            assert second.status_code == 409
            assert second.json()["error"] == "extraction_already_running"
        finally:
            release.set()

        # After the first run completes, a new run is allowed again.
        _wait_for_status(inbound_client, first.json()["job_id"], "completed")
        third = inbound_client.post(EXTRACT_URL, json={})
        assert third.status_code == 202
        _wait_for_status(inbound_client, third.json()["job_id"], "completed")


class TestHealthz:
    def test_healthz_ok(self, inbound_client):
        r = inbound_client.get("/healthz")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
