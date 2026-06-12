"""
Fixtures for the /inbound pipeline tests.

These tests need NO database — the inbound pipeline is filesystem-backed.
The `inbound_client` fixture redirects the module-level directory constants
in inbound_routes to a per-test temp directory, so tests never touch the
real input_images/, inbound/, or exports/ folders (or the /data volume).

The root tests/conftest.py DB fixtures (test_engine, db, client) are lazy —
they only connect to PostgreSQL when a test requests them — so this package
runs green on a machine with no database at all.
"""

import json

import pytest
from fastapi.testclient import TestClient

from service_photo.api import inbound_routes
from service_photo.services import inbound_store


@pytest.fixture()
def data_dirs(tmp_path, monkeypatch):
    """
    Point the inbound routes at a fresh temp data dir and create the three
    managed subfolders. Returns the paths so tests can seed files directly.

    The SQLite store is redirected to a temp catalog.db too, so every test
    starts with a clean database — no job left "running" by one test can
    409 the next one, and no review state leaks across tests.
    """
    input_dir = tmp_path / "input_images"
    inbound_dir = tmp_path / "inbound"
    exports_dir = tmp_path / "exports"
    for d in (input_dir, inbound_dir, exports_dir):
        d.mkdir()

    monkeypatch.setattr(inbound_routes, "INPUT_IMAGES_DIR", input_dir)
    monkeypatch.setattr(inbound_routes, "INBOUND_DIR", inbound_dir)
    monkeypatch.setattr(inbound_routes, "EXPORTS_DIR", exports_dir)
    # Export responses report csv_path relative to APP_DATA_PATH — keep that
    # consistent with the temp layout so relative_to() doesn't blow up.
    monkeypatch.setattr(inbound_routes, "APP_DATA_PATH", tmp_path)
    # Fresh SQLite database per test.
    monkeypatch.setattr(inbound_store, "DB_PATH", tmp_path / "catalog.db")

    return {
        "root": tmp_path,
        "input_images": input_dir,
        "inbound": inbound_dir,
        "exports": exports_dir,
    }


@pytest.fixture()
def inbound_client(data_dirs):
    """TestClient wired to the temp data dirs + temp SQLite store."""
    from service_photo.main import app

    with TestClient(app) as client:
        yield client


def seed_artifact(data_dirs, extraction_id="extraction_2026-06-12T00-00-00Z__img1", **overrides):
    """Write a minimal extraction artifact into the temp inbound/ folder.

    Review endpoints 404 unless the extraction_id names a real artifact, so
    tests that exercise review/approve/export call this first. Returns the
    extraction_id for convenience.
    """
    artifact = {
        "meta": {"image_files": ["img1.jpg"], "model": "fake-model", "schema_valid": True},
        "response": {
            "overview": {"product_name": "Nikon Z6", "brand": "Nikon", "model": "Z6"},
            "description": {"short_title": "Nikon Z6 body"},
            "specifications": {},
            "accessories": {},
        },
        "pricing": None,
    }
    artifact.update(overrides)
    (data_dirs["inbound"] / f"{extraction_id}.json").write_text(
        json.dumps(artifact), encoding="utf-8"
    )
    return extraction_id


# --- Tiny real image payloads -------------------------------------------------
# Minimal valid headers for the magic-byte sniffer. Content beyond the header
# doesn't matter for upload tests — nothing decodes the pixels.

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
WEBP_BYTES = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 32
NOT_AN_IMAGE_BYTES = b"MZ\x90\x00" + b"\x00" * 32  # PE executable header
