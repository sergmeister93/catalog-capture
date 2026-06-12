"""
Tests for the inbound CSV export path: cell normalization rules (including
the spreadsheet formula-injection defense), the Phase 7A approval gate
(only server-approved content can be exported), and the download endpoint's
path-traversal defenses.
"""

import csv
import io

from service_photo.api.inbound_routes import _normalize_cell

from .conftest import seed_artifact


# --- _normalize_cell unit tests ------------------------------------------------

class TestNormalizeCell:
    def test_none_becomes_blank(self):
        assert _normalize_cell("brand", None) == ""

    def test_whitespace_only_becomes_blank(self):
        assert _normalize_cell("brand", "   ") == ""

    def test_plain_text_is_trimmed(self):
        assert _normalize_cell("brand", "  Nikon  ") == "Nikon"

    def test_bool_serializes_as_word_not_number(self):
        assert _normalize_cell("serial_number_visible", True) == "true"
        assert _normalize_cell("serial_number_visible", False) == "false"

    def test_integral_float_drops_decimal_point(self):
        assert _normalize_cell("megapixels", 33.0) == "33"

    def test_non_integral_float_kept(self):
        assert _normalize_cell("fair_price", 449.99) == "449.99"

    def test_negative_number_not_escaped(self):
        # Numbers are safe by construction — a negative price must not grow
        # a quote prefix.
        assert _normalize_cell("fair_price", -5) == "-5"

    def test_newlines_flattened_in_longform_fields(self):
        text = "Line one.\r\nLine two.\nLine three."
        assert _normalize_cell("description_text", text) == "Line one. Line two. Line three."

    def test_newlines_preserved_outside_longform_fields(self):
        # Only the spec's long-form fields get flattened.
        assert "\n" in _normalize_cell("brand", "a\nb") or _normalize_cell("brand", "a\nb") == "a\nb"

    def test_formula_injection_equals_escaped(self):
        assert _normalize_cell("short_title", "=HYPERLINK(\"http://evil\")").startswith("'=")

    def test_formula_injection_plus_escaped(self):
        assert _normalize_cell("short_title", "+1+2") == "'+1+2"

    def test_formula_injection_at_escaped(self):
        assert _normalize_cell("short_title", "@SUM(A1)") == "'@SUM(A1)"

    def test_formula_injection_leading_dash_text_escaped(self):
        # Text starting with '-' is a formula trigger in Excel; LLM text could
        # legitimately start with a dash, so it renders with a hidden quote.
        assert _normalize_cell("short_title", "-2+3") == "'-2+3"

    def test_normal_text_not_escaped(self):
        assert _normalize_cell("short_title", "Nikon Z6 II body") == "Nikon Z6 II body"


# --- Export endpoint ------------------------------------------------------------
#
# Phase 7A contract: the client sends extraction_ids only. Content comes from
# the server-stored, approved review snapshots — so every test first seeds an
# artifact, then approves it (carrying the content), then exports.

_RESPONSE = {
    "overview": {"product_name": "Nikon Z6", "brand": "Nikon", "model": "Z6"},
    "description": {"short_title": "Nikon Z6 body", "description_text": "Solid.\nClean."},
    "specifications": {"megapixels": 24.5},
    "accessories": {"included_accessories_text": "Strap, cap"},
}

_PRICING = {
    "market_valuation": {"fair_price": 800, "deal_threshold": 650},
    "pricing": {"ebay_sold_avg": 820.5},
    "market_summary": "Stable\nmarket.",
    "sources": [{"platform": "ebay", "price": 820.5}],
    "fetched_at_utc": "2026-06-12T00:00:00Z",
}


def _seed_and_approve(client, data_dirs, response=None, pricing=_PRICING, actor=None):
    """Seed one artifact and approve it through the API. Returns its id."""
    extraction_id = seed_artifact(data_dirs)
    headers = {"Cf-Access-Authenticated-User-Email": actor} if actor else {}
    r = client.post(
        f"/api/v1/inbound/review/{extraction_id}/approve",
        json={"response": response or _RESPONSE, "pricing": pricing},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return extraction_id


class TestExportEndpoint:
    def test_empty_ids_rejected(self, inbound_client):
        r = inbound_client.post("/api/v1/inbound/export", json={"extraction_ids": []})
        assert r.status_code == 400
        assert r.json()["error"] == "no_items"

    def test_unapproved_id_rejected(self, inbound_client, data_dirs):
        # An artifact exists but was never approved — the gate must refuse it.
        extraction_id = seed_artifact(data_dirs)
        r = inbound_client.post(
            "/api/v1/inbound/export", json={"extraction_ids": [extraction_id]}
        )
        assert r.status_code == 400
        assert r.json()["error"] == "not_approved"
        assert extraction_id in r.json()["message"]

    def test_export_writes_csv_with_expected_row(self, inbound_client, data_dirs):
        extraction_id = _seed_and_approve(
            inbound_client, data_dirs, actor="sergey@example.com"
        )
        r = inbound_client.post(
            "/api/v1/inbound/export", json={"extraction_ids": [extraction_id]}
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["row_count"] == 1

        csv_file = data_dirs["exports"] / body["csv_filename"]
        assert csv_file.is_file()

        rows = list(csv.DictReader(io.StringIO(csv_file.read_text(encoding="utf-8"))))
        assert len(rows) == 1
        row = rows[0]
        assert row["brand"] == "Nikon"
        assert row["megapixels"] == "24.5"
        # Newlines flattened in long-form fields.
        assert row["description_text"] == "Solid. Clean."
        assert row["market_summary"] == "Stable market."
        # Pricing flattening.
        assert row["fair_price"] == "800"
        assert row["ebay_sold_avg"] == "820.5"
        assert "ebay" in row["pricing_sources_json"]
        # Provenance comes from the approval record (Cloudflare Access email).
        assert row["approved_by"] == "sergey@example.com"
        assert row["approved_at"] != ""

    def test_export_neutralizes_formula_cells(self, inbound_client, data_dirs):
        hostile = dict(_RESPONSE)
        hostile["description"] = {
            "short_title": "=cmd|'/C calc'!A0",
            "description_text": "@SUM(1,2)",
        }
        extraction_id = _seed_and_approve(inbound_client, data_dirs, response=hostile)
        r = inbound_client.post(
            "/api/v1/inbound/export", json={"extraction_ids": [extraction_id]}
        )
        assert r.status_code == 201
        csv_text = (data_dirs["exports"] / r.json()["csv_filename"]).read_text(encoding="utf-8")
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        assert rows[0]["short_title"].startswith("'=")
        assert rows[0]["description_text"].startswith("'@")

    def test_download_roundtrip(self, inbound_client, data_dirs):
        extraction_id = _seed_and_approve(inbound_client, data_dirs)
        r = inbound_client.post(
            "/api/v1/inbound/export", json={"extraction_ids": [extraction_id]}
        )
        filename = r.json()["csv_filename"]

        dl = inbound_client.get(f"/api/v1/inbound/exports/{filename}")
        assert dl.status_code == 200
        assert dl.headers["content-type"].startswith("text/csv")
        assert "attachment" in dl.headers.get("content-disposition", "")


class TestExportDownloadTraversal:
    def test_non_csv_filename_rejected(self, inbound_client):
        r = inbound_client.get("/api/v1/inbound/exports/secrets.txt")
        assert r.status_code == 400

    def test_traversal_filename_rejected(self, inbound_client):
        # URL-encoded ../ — must not escape the exports dir.
        r = inbound_client.get("/api/v1/inbound/exports/..%2F..%2F.env.csv")
        assert r.status_code in (400, 404)

    def test_missing_file_404(self, inbound_client):
        r = inbound_client.get("/api/v1/inbound/exports/listings_nope.csv")
        assert r.status_code == 404
