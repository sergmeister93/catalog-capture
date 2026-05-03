"""Unit tests for CSV transform helper functions."""

from decimal import Decimal
from datetime import datetime, timezone

from service_photo.exports.csv_generator import (
    _trim,
    _normalize_linebreaks,
    _format_timestamp,
    _format_decimal,
    _format_integer,
    _format_json,
    CSV_COLUMNS,
)


def test_trim_strips_whitespace():
    assert _trim("  hello  ") == "hello"
    assert _trim(None) == ""
    assert _trim("   ") == ""


def test_normalize_linebreaks_flattens_crlf():
    assert _normalize_linebreaks("line1\r\nline2") == "line1 line2"
    assert _normalize_linebreaks("line1\nline2") == "line1 line2"
    assert _normalize_linebreaks("line1\rline2") == "line1 line2"
    assert _normalize_linebreaks(None) == ""


def test_format_timestamp_utc():
    dt = datetime(2026, 4, 19, 21, 45, 30, tzinfo=timezone.utc)
    assert _format_timestamp(dt) == "2026-04-19T21:45:30Z"
    assert _format_timestamp(None) == ""


def test_format_decimal():
    assert _format_decimal(20.1) == "20.1"
    assert _format_decimal(Decimal("24.2")) == "24.2"
    assert _format_decimal(24) == "24"
    assert _format_decimal(None) == ""


def test_format_integer():
    assert _format_integer(680) == "680"
    assert _format_integer(None) == ""


def test_format_json():
    assert _format_json({"a": 1}) == '{"a":1}'
    assert _format_json(None) == ""


def test_csv_column_order_matches_spec():
    """Column order must exactly match contracts/csv_export_schema.md."""
    expected = [
        "job_number", "item_category", "product_name", "brand", "model",
        "product_family", "variant", "mount_type", "serial_number_visible",
        "condition_summary", "short_title", "description_text", "visible_wear_notes",
        "key_selling_points", "sensor_format", "megapixels", "lens_mount",
        "focal_length", "aperture", "iso_range", "shutter_range",
        "video_capabilities", "storage_media", "connectivity", "weight_grams",
        "other_specifications_json", "included_accessories_text",
        "inferred_accessories_text", "missing_typical_accessories_text",
        "approved_at", "approved_by", "exported_at",
    ]
    assert CSV_COLUMNS == expected
