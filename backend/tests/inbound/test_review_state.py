"""
Tests for the Phase 7A server-side review layer: save/approve/unapprove
endpoints, the append-only audit trail, SQLite-backed durability (state
visible to a "different process" via a fresh connection), and the DB half
of Clear Data.
"""

import json
import sqlite3

from service_photo.services import inbound_store

from .conftest import seed_artifact

REVIEW_URL = "/api/v1/inbound/review"

_EDITED = {
    "overview": {"product_name": "Nikon Z6 II", "brand": "Nikon", "model": "Z6 II"},
    "description": {"short_title": "Nikon Z6 II body — edited"},
    "specifications": {},
    "accessories": {},
}


class TestSaveReview:
    def test_unknown_artifact_404(self, inbound_client):
        r = inbound_client.put(
            f"{REVIEW_URL}/extraction_nope", json={"response": _EDITED, "pricing": None}
        )
        assert r.status_code == 404
        assert r.json()["error"] == "extraction_not_found"

    def test_bad_extraction_id_400(self, inbound_client):
        # '$' fails the safe-filename pattern; traversal sequences like ../
        # never even reach the handler (the router 405s them first).
        r = inbound_client.put(
            f"{REVIEW_URL}/evil$id", json={"response": _EDITED, "pricing": None}
        )
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_extraction_id"

    def test_save_then_listing_includes_review(self, inbound_client, data_dirs):
        extraction_id = seed_artifact(data_dirs)
        r = inbound_client.put(
            f"{REVIEW_URL}/{extraction_id}", json={"response": _EDITED, "pricing": None}
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["approved"] is False
        assert body["edited_response"]["overview"]["product_name"] == "Nikon Z6 II"

        # GET /inbound now carries the saved state for this card.
        listing = inbound_client.get("/api/v1/inbound").json()
        item = next(i for i in listing["items"] if i["extraction_id"] == extraction_id)
        assert item["review"] is not None
        assert item["review"]["edited_response"]["description"]["short_title"].endswith("edited")

    def test_save_does_not_touch_approval(self, inbound_client, data_dirs):
        extraction_id = seed_artifact(data_dirs)
        inbound_client.post(
            f"{REVIEW_URL}/{extraction_id}/approve", json={"response": _EDITED, "pricing": None}
        )
        # A later content save must not clear the approval flag.
        r = inbound_client.put(
            f"{REVIEW_URL}/{extraction_id}", json={"response": _EDITED, "pricing": None}
        )
        assert r.json()["approved"] is True


class TestApproval:
    def test_approve_records_actor_from_cloudflare_header(self, inbound_client, data_dirs):
        extraction_id = seed_artifact(data_dirs)
        r = inbound_client.post(
            f"{REVIEW_URL}/{extraction_id}/approve",
            json={"response": _EDITED, "pricing": None},
            headers={"Cf-Access-Authenticated-User-Email": "sergey@example.com"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["approved"] is True
        assert body["approved_by"] == "sergey@example.com"
        assert body["approved_at_utc"] is not None

    def test_approve_without_header_falls_back_to_local_dev(self, inbound_client, data_dirs):
        extraction_id = seed_artifact(data_dirs)
        r = inbound_client.post(
            f"{REVIEW_URL}/{extraction_id}/approve", json={"response": _EDITED, "pricing": None}
        )
        assert r.json()["approved_by"] == "local-dev"

    def test_unapprove_clears_flag_keeps_content(self, inbound_client, data_dirs):
        extraction_id = seed_artifact(data_dirs)
        inbound_client.post(
            f"{REVIEW_URL}/{extraction_id}/approve", json={"response": _EDITED, "pricing": None}
        )
        r = inbound_client.delete(f"{REVIEW_URL}/{extraction_id}/approve")
        assert r.status_code == 200
        body = r.json()
        assert body["approved"] is False
        assert body["approved_at_utc"] is None
        # Content snapshot survives the un-approval.
        assert body["edited_response"]["overview"]["model"] == "Z6 II"

    def test_unapprove_with_no_review_row_404(self, inbound_client, data_dirs):
        extraction_id = seed_artifact(data_dirs)
        r = inbound_client.delete(f"{REVIEW_URL}/{extraction_id}/approve")
        assert r.status_code == 404


class TestAuditTrail:
    def _events(self):
        """Read the audit rows straight from the SQLite file — a deliberate
        out-of-band check that the trail actually landed on disk."""
        with sqlite3.connect(inbound_store.DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(
                "SELECT * FROM review_events ORDER BY event_id"
            ).fetchall()

    def test_full_lifecycle_is_audited(self, inbound_client, data_dirs):
        extraction_id = seed_artifact(data_dirs)
        headers = {"Cf-Access-Authenticated-User-Email": "sergey@example.com"}

        inbound_client.put(
            f"{REVIEW_URL}/{extraction_id}", json={"response": _EDITED, "pricing": None},
            headers=headers,
        )
        inbound_client.post(
            f"{REVIEW_URL}/{extraction_id}/approve", json={"response": _EDITED, "pricing": None},
            headers=headers,
        )
        inbound_client.delete(f"{REVIEW_URL}/{extraction_id}/approve", headers=headers)
        inbound_client.post(
            f"{REVIEW_URL}/{extraction_id}/approve", json={"response": _EDITED, "pricing": None},
            headers=headers,
        )
        export = inbound_client.post(
            "/api/v1/inbound/export", json={"extraction_ids": [extraction_id]},
            headers=headers,
        )
        assert export.status_code == 201

        events = self._events()
        assert [e["event_type"] for e in events] == [
            "edited", "approved", "unapproved", "approved", "exported",
        ]
        assert all(e["actor"] == "sergey@example.com" for e in events)
        # The edit event snapshots the saved content.
        edited_detail = json.loads(events[0]["detail"])
        assert edited_detail["response"]["overview"]["product_name"] == "Nikon Z6 II"
        # The export event names the CSV it landed in.
        export_detail = json.loads(events[-1]["detail"])
        assert export_detail["csv_filename"] == export.json()["csv_filename"]

    def test_export_is_recorded_in_exports_table(self, inbound_client, data_dirs):
        extraction_id = seed_artifact(data_dirs)
        inbound_client.post(
            f"{REVIEW_URL}/{extraction_id}/approve", json={"response": _EDITED, "pricing": None}
        )
        r = inbound_client.post(
            "/api/v1/inbound/export", json={"extraction_ids": [extraction_id]}
        )
        with sqlite3.connect(inbound_store.DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM exports").fetchall()
        assert len(rows) == 1
        assert rows[0]["csv_filename"] == r.json()["csv_filename"]
        assert json.loads(rows[0]["extraction_ids"]) == [extraction_id]


class TestDurability:
    def test_review_state_survives_a_fresh_connection(self, inbound_client, data_dirs):
        """Simulates a server restart / second worker: a brand-new sqlite3
        connection (not the store's) sees the state the API wrote."""
        extraction_id = seed_artifact(data_dirs)
        inbound_client.post(
            f"{REVIEW_URL}/{extraction_id}/approve", json={"response": _EDITED, "pricing": None}
        )
        with sqlite3.connect(inbound_store.DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM review_items WHERE extraction_id = ?", (extraction_id,)
            ).fetchone()
        assert row is not None
        assert row["approved"] == 1
        assert json.loads(row["edited_response"])["overview"]["brand"] == "Nikon"


class TestClearData:
    def test_clear_data_wipes_db_tables(self, inbound_client, data_dirs):
        extraction_id = seed_artifact(data_dirs)
        inbound_client.post(
            f"{REVIEW_URL}/{extraction_id}/approve", json={"response": _EDITED, "pricing": None}
        )

        r = inbound_client.delete("/api/v1/inbound/data")
        assert r.status_code == 200
        body = r.json()
        # 1 review row + 1 'approved' audit event at minimum.
        assert body["db_rows_deleted"] >= 2
        assert body["inbound_deleted"] == 1

        assert inbound_store.get_all_reviews() == {}
