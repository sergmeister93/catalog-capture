"""
Tests for the extraction job lifecycle: start, poll, the single-active-run
lock (409), and failure handling. The actual Gemini work is monkeypatched —
these tests exercise the job registry and threading glue, not the API call.
"""

import sqlite3
import threading
import time

from service_photo.api import inbound_routes
from service_photo.services import inbound_store
from service_photo.services.inbound_extraction import ExtractionSummary

from .conftest import JPEG_BYTES, seed_artifact

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


class TestSqliteDurability:
    def test_completed_job_survives_fresh_connection(self, inbound_client, data_dirs, monkeypatch):
        """A finished job's record is on disk — readable by a brand-new
        sqlite3 connection, i.e. by another worker process or after restart."""
        _seed_images(data_dirs)
        monkeypatch.setattr(inbound_routes, "run_extraction", lambda **kw: _fake_summary())
        r = inbound_client.post(EXTRACT_URL, json={})
        job_id = r.json()["job_id"]
        _wait_for_status(inbound_client, job_id, "completed")

        with sqlite3.connect(inbound_store.DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM extraction_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        assert row is not None
        assert row["status"] == "completed"
        assert row["model"] == "fake-model"

    def test_orphaned_running_job_flips_to_failed_on_read(self, inbound_client, data_dirs, monkeypatch):
        """A job left 'running' by a dead server (stale heartbeat) must not
        wedge the UI or block new extractions forever."""
        stale_time = "2026-06-12T00:00:00Z"  # far older than the stale threshold
        # The store creates the schema lazily on its own connections — force
        # it first so the raw insert below has tables to write to.
        inbound_store.init_db()
        with sqlite3.connect(inbound_store.DB_PATH) as conn:
            conn.execute(
                """INSERT INTO extraction_jobs
                   (job_id, status, total, started_at_utc, updated_at_utc)
                   VALUES ('orphan1', 'running', 3, ?, ?)""",
                (stale_time, stale_time),
            )
            conn.commit()

        body = inbound_client.get(f"{EXTRACT_URL}/orphan1").json()
        assert body["status"] == "failed"
        assert "restarted" in body["error"]

        # And a new extraction is allowed despite the orphan.
        _seed_images(data_dirs)
        monkeypatch.setattr(inbound_routes, "run_extraction", lambda **kw: _fake_summary())
        r = inbound_client.post(EXTRACT_URL, json={})
        assert r.status_code == 202
        _wait_for_status(inbound_client, r.json()["job_id"], "completed")

    def test_new_extraction_purges_review_rows(self, inbound_client, data_dirs, monkeypatch):
        """Starting a new run wipes review state — its artifacts are about to
        be purged, so rows pointing at them are meaningless."""
        extraction_id = seed_artifact(data_dirs)
        approve = inbound_client.post(
            f"/api/v1/inbound/review/{extraction_id}/approve",
            json={"response": {"overview": {}, "description": {}, "specifications": {}, "accessories": {}}, "pricing": None},
        )
        assert approve.status_code == 200
        assert inbound_store.get_all_reviews() != {}

        _seed_images(data_dirs)
        monkeypatch.setattr(inbound_routes, "run_extraction", lambda **kw: _fake_summary())
        r = inbound_client.post(EXTRACT_URL, json={})
        _wait_for_status(inbound_client, r.json()["job_id"], "completed")

        assert inbound_store.get_all_reviews() == {}


class TestHealthz:
    def test_healthz_ok(self, inbound_client):
        r = inbound_client.get("/healthz")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
