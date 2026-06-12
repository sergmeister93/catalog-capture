"""
Tests for real_gemini.prepare_image_bytes — the client-side image downscale
that runs before every Gemini upload (Phase 7 throughput pass).

What it covers:
  - a large image gets resized to the max-edge cap and re-encoded as JPEG,
    and the payload actually shrinks
  - a small image passes through byte-for-byte untouched (no re-encode)
  - max_edge_px=0 disables downscaling entirely
  - undecodable bytes fail open: original bytes are sent rather than erroring

No network and no Gemini client involved — prepare_image_bytes is a pure
module-level function operating on local files.
"""

import io

from PIL import Image

from service_photo.integrations.real_gemini import prepare_image_bytes


def _write_jpeg(path, width, height):
    """Create a synthetic JPEG of the given size with some non-uniform content
    (a gradient) so JPEG compression behaves like it would on a real photo."""
    img = Image.new("RGB", (width, height))
    # Cheap horizontal gradient — uniform-color images compress unrealistically well.
    for x in range(0, width, max(1, width // 64)):
        img.paste((x % 256, 100, 200), (x, 0, min(x + 64, width), height))
    img.save(path, format="JPEG", quality=95)
    return path


def test_large_image_is_downscaled_and_smaller(tmp_path):
    big = _write_jpeg(tmp_path / "big.jpg", 4000, 3000)
    original_size = big.stat().st_size

    data, mime = prepare_image_bytes(big, "image/jpeg", 1536)

    assert mime == "image/jpeg"
    assert len(data) < original_size
    with Image.open(io.BytesIO(data)) as resized:
        # Longest edge capped, aspect ratio preserved (4:3).
        assert max(resized.size) == 1536
        assert resized.size == (1536, 1152)


def test_small_image_passes_through_untouched(tmp_path):
    small = _write_jpeg(tmp_path / "small.jpg", 800, 600)
    original_bytes = small.read_bytes()

    data, mime = prepare_image_bytes(small, "image/jpeg", 1536)

    # Identical bytes — no lossy re-encode of an image that's already fine.
    assert data == original_bytes
    assert mime == "image/jpeg"


def test_zero_max_edge_disables_downscaling(tmp_path):
    big = _write_jpeg(tmp_path / "big.jpg", 4000, 3000)
    original_bytes = big.read_bytes()

    data, mime = prepare_image_bytes(big, "image/jpeg", 0)

    assert data == original_bytes
    assert mime == "image/jpeg"


def test_undecodable_image_fails_open(tmp_path):
    # A file whose extension claims JPEG but whose bytes Pillow can't decode.
    # The helper must send the original bytes rather than raise — a slow
    # Gemini call beats a failed extraction.
    bogus = tmp_path / "corrupt.jpg"
    bogus.write_bytes(b"not actually an image at all")

    data, mime = prepare_image_bytes(bogus, "image/jpeg", 1536)

    assert data == b"not actually an image at all"
    assert mime == "image/jpeg"


def test_png_with_alpha_flattens_to_jpeg(tmp_path):
    # JPEG has no alpha channel; an oversized transparent PNG must be
    # converted (not crash on save).
    png = tmp_path / "transparent.png"
    Image.new("RGBA", (3000, 2000), (255, 0, 0, 128)).save(png, format="PNG")

    data, mime = prepare_image_bytes(png, "image/png", 1536)

    assert mime == "image/jpeg"
    with Image.open(io.BytesIO(data)) as resized:
        assert resized.mode == "RGB"
        assert max(resized.size) == 1536
