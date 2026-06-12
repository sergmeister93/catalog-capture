"""
Tests for the upload endpoint (POST /inbound/input-images) — filename rules,
extension whitelist, magic-byte content check, size/count caps, collision
renaming — and the image-serving endpoint's path-traversal defenses.
"""

from service_photo.api import inbound_routes

from .conftest import JPEG_BYTES, PNG_BYTES, WEBP_BYTES, NOT_AN_IMAGE_BYTES

UPLOAD_URL = "/api/v1/inbound/input-images"


def _upload(client, *files):
    """files: tuples of (filename, bytes, content_type)."""
    return client.post(
        UPLOAD_URL,
        files=[("files", (name, data, ctype)) for name, data, ctype in files],
    )


class TestUploadValidation:
    def test_valid_jpeg_accepted(self, inbound_client, data_dirs):
        r = _upload(inbound_client, ("camera.jpg", JPEG_BYTES, "image/jpeg"))
        assert r.status_code == 200
        result = r.json()["results"][0]
        assert result["ok"] is True
        assert result["saved_name"] == "camera.jpg"
        assert (data_dirs["input_images"] / "camera.jpg").is_file()

    def test_valid_png_and_webp_accepted(self, inbound_client):
        r = _upload(
            inbound_client,
            ("a.png", PNG_BYTES, "image/png"),
            ("b.webp", WEBP_BYTES, "image/webp"),
        )
        assert all(res["ok"] for res in r.json()["results"])

    def test_unsupported_extension_rejected(self, inbound_client, data_dirs):
        r = _upload(inbound_client, ("notes.txt", b"hello", "text/plain"))
        result = r.json()["results"][0]
        assert result["ok"] is False
        assert "unsupported file type" in result["error"]
        assert not (data_dirs["input_images"] / "notes.txt").exists()

    def test_spoofed_extension_rejected_by_magic_bytes(self, inbound_client, data_dirs):
        # An executable renamed to .jpg passes the extension check but must
        # fail the content sniff.
        r = _upload(inbound_client, ("evil.jpg", NOT_AN_IMAGE_BYTES, "image/jpeg"))
        result = r.json()["results"][0]
        assert result["ok"] is False
        assert "does not match a supported image format" in result["error"]
        assert not (data_dirs["input_images"] / "evil.jpg").exists()

    def test_empty_file_rejected(self, inbound_client):
        r = _upload(inbound_client, ("empty.jpg", b"", "image/jpeg"))
        result = r.json()["results"][0]
        assert result["ok"] is False
        assert result["error"] == "empty file"

    def test_unsafe_filename_rejected(self, inbound_client):
        r = _upload(inbound_client, ("we ird name!.jpg", JPEG_BYTES, "image/jpeg"))
        result = r.json()["results"][0]
        assert result["ok"] is False

    def test_collision_appends_counter(self, inbound_client, data_dirs):
        (data_dirs["input_images"] / "dup.jpg").write_bytes(JPEG_BYTES)
        r = _upload(inbound_client, ("dup.jpg", JPEG_BYTES, "image/jpeg"))
        result = r.json()["results"][0]
        assert result["ok"] is True
        assert result["saved_name"] == "dup-1.jpg"

    def test_too_many_files_rejected(self, inbound_client, monkeypatch):
        # Lower the cap so the test doesn't build 51 multipart parts.
        monkeypatch.setattr(inbound_routes, "_MAX_FILES_PER_UPLOAD", 2)
        r = _upload(
            inbound_client,
            ("a.jpg", JPEG_BYTES, "image/jpeg"),
            ("b.jpg", JPEG_BYTES, "image/jpeg"),
            ("c.jpg", JPEG_BYTES, "image/jpeg"),
        )
        assert r.status_code == 400
        assert r.json()["error"] == "too_many_files"

    def test_oversize_file_rejected(self, inbound_client, monkeypatch):
        monkeypatch.setattr(inbound_routes, "_MAX_UPLOAD_BYTES", 16)
        r = _upload(inbound_client, ("big.jpg", JPEG_BYTES + b"\x00" * 64, "image/jpeg"))
        result = r.json()["results"][0]
        assert result["ok"] is False
        assert "limit" in result["error"]


class TestImageServing:
    def test_serves_existing_image(self, inbound_client, data_dirs):
        (data_dirs["input_images"] / "ok.jpg").write_bytes(JPEG_BYTES)
        r = inbound_client.get("/api/v1/inbound/images/ok.jpg")
        assert r.status_code == 200
        assert r.content == JPEG_BYTES

    def test_missing_image_404(self, inbound_client):
        r = inbound_client.get("/api/v1/inbound/images/nope.jpg")
        assert r.status_code == 404

    def test_traversal_chars_rejected(self, inbound_client):
        r = inbound_client.get("/api/v1/inbound/images/..%2F..%2F.env")
        assert r.status_code in (400, 404)

    def test_unsafe_chars_rejected(self, inbound_client):
        r = inbound_client.get("/api/v1/inbound/images/a%20b.jpg")
        assert r.status_code == 400


class TestSniffImageFormat:
    def test_known_formats(self):
        assert inbound_routes._sniff_image_format(JPEG_BYTES) == "jpeg"
        assert inbound_routes._sniff_image_format(PNG_BYTES) == "png"
        assert inbound_routes._sniff_image_format(WEBP_BYTES) == "webp"

    def test_heic_brand(self):
        data = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 16
        assert inbound_routes._sniff_image_format(data) == "heif"

    def test_garbage_rejected(self):
        assert inbound_routes._sniff_image_format(NOT_AN_IMAGE_BYTES) is None
        assert inbound_routes._sniff_image_format(b"") is None
        assert inbound_routes._sniff_image_format(b"short") is None
