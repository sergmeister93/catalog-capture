"""
CSV export generator.

Inputs:
  - ListingJob ORM instance
  - All four reviewed content ORM instances
  - export_timestamp (datetime)

Outputs:
  - A dict representing one CSV row
  - Written CSV file at STORAGE_BASE_PATH/exports/<filename>

Column order is EXACTLY as specified in contracts/csv_export_schema.md.
Transform rules are applied per spec:
  - trim: strip leading/trailing whitespace
  - line_break: flatten \\r\\n / \\r / \\n to single space
  - numeric: plain decimal / integer string
  - json_field: compact JSON string or blank
  - timestamp: ISO-8601 UTC string
"""

import csv
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from service_photo.core.config import settings

# Exact column order from contracts/csv_export_schema.md.
CSV_COLUMNS = [
    "job_number",
    "item_category",
    "product_name",
    "brand",
    "model",
    "product_family",
    "variant",
    "mount_type",
    "serial_number_visible",
    "condition_summary",
    "short_title",
    "description_text",
    "visible_wear_notes",
    "key_selling_points",
    "sensor_format",
    "megapixels",
    "lens_mount",
    "focal_length",
    "aperture",
    "iso_range",
    "shutter_range",
    "video_capabilities",
    "storage_media",
    "connectivity",
    "weight_grams",
    "other_specifications_json",
    "included_accessories_text",
    "inferred_accessories_text",
    "missing_typical_accessories_text",
    "approved_at",
    "approved_by",
    "exported_at",
]

# Fields that get the line-break flatten treatment.
_LINEBREAK_FIELDS = {
    "description_text",
    "visible_wear_notes",
    "key_selling_points",
    "video_capabilities",
    "included_accessories_text",
    "inferred_accessories_text",
    "missing_typical_accessories_text",
}


def _trim(value: str | None) -> str:
    """Strip leading/trailing whitespace; blank/null → empty string."""
    if value is None:
        return ""
    stripped = value.strip()
    return stripped


def _normalize_linebreaks(value: str | None) -> str:
    """Flatten CRLF/CR/LF to a single space; blank/null → empty string."""
    if value is None:
        return ""
    # Replace CRLF first, then CR, then bare LF.
    normalized = value.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    return normalized.strip()


def _format_timestamp(dt: datetime | None) -> str:
    """Format a datetime as ISO-8601 UTC string (e.g. 2026-04-19T21:45:30Z)."""
    if dt is None:
        return ""
    if dt.tzinfo is None:
        # Assume UTC if naive.
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_decimal(value) -> str:
    """Format a numeric value as a plain decimal string without trailing units."""
    if value is None:
        return ""
    dec = Decimal(str(value))
    # Remove trailing zeros after decimal point.
    normalized = dec.normalize()
    return str(normalized)


def _format_integer(value: int | None) -> str:
    """Format an integer as a plain string without units."""
    if value is None:
        return ""
    return str(int(value))


def _format_json(value: dict | None) -> str:
    """Serialize a JSONB field to compact JSON string; null → empty string."""
    if value is None:
        return ""
    return json.dumps(value, separators=(",", ":"))


def generate_csv_row(
    job,
    r_overview,
    r_description,
    r_specifications,
    r_accessories,
    export_timestamp: datetime,
) -> dict:
    """
    Build the ordered CSV row dict from reviewed ORM objects.

    Applies all transformation rules from contracts/csv_export_schema.md.
    All values are strings ready for csv.DictWriter.
    """
    row: dict[str, str] = {}

    # --- From listing_jobs ---
    row["job_number"] = _trim(job.job_number)
    row["item_category"] = _trim(job.item_category)
    row["approved_at"] = _format_timestamp(job.approved_at)
    row["approved_by"] = _trim(job.approved_by)
    row["exported_at"] = _format_timestamp(export_timestamp)

    # --- From listing_review_overview ---
    row["product_name"] = _trim(r_overview.product_name)
    row["brand"] = _trim(r_overview.brand)
    row["model"] = _trim(r_overview.model)
    row["product_family"] = _trim(r_overview.product_family)
    row["variant"] = _trim(r_overview.variant)
    row["mount_type"] = _trim(r_overview.mount_type)
    row["serial_number_visible"] = _trim(r_overview.serial_number_visible)
    row["condition_summary"] = _trim(r_overview.condition_summary)

    # --- From listing_review_description ---
    row["short_title"] = _trim(r_description.short_title)
    row["description_text"] = _normalize_linebreaks(r_description.description_text)
    row["visible_wear_notes"] = _normalize_linebreaks(r_description.visible_wear_notes)
    row["key_selling_points"] = _normalize_linebreaks(r_description.key_selling_points)

    # --- From listing_review_specifications ---
    row["sensor_format"] = _trim(r_specifications.sensor_format)
    row["megapixels"] = _format_decimal(r_specifications.megapixels)
    row["lens_mount"] = _trim(r_specifications.lens_mount)
    row["focal_length"] = _trim(r_specifications.focal_length)
    row["aperture"] = _trim(r_specifications.aperture)
    row["iso_range"] = _trim(r_specifications.iso_range)
    row["shutter_range"] = _trim(r_specifications.shutter_range)
    row["video_capabilities"] = _normalize_linebreaks(r_specifications.video_capabilities)
    row["storage_media"] = _trim(r_specifications.storage_media)
    row["connectivity"] = _trim(r_specifications.connectivity)
    row["weight_grams"] = _format_integer(r_specifications.weight_grams)
    row["other_specifications_json"] = _format_json(r_specifications.other_specifications)

    # --- From listing_review_accessories ---
    row["included_accessories_text"] = _normalize_linebreaks(r_accessories.included_accessories_text)
    row["inferred_accessories_text"] = _normalize_linebreaks(r_accessories.inferred_accessories_text)
    row["missing_typical_accessories_text"] = _normalize_linebreaks(r_accessories.missing_typical_accessories_text)

    # Return in defined column order (dict will be keyed but writer uses fieldnames).
    return row


def write_csv_to_storage(
    job_number: str,
    row_data: dict,
    export_timestamp: datetime,
) -> tuple[str, str]:
    """
    Write one-row CSV to STORAGE_BASE_PATH/exports/ and return (file_name, file_path).

    File naming: service_photo_export_<job_number>_<timestamp_utc>.csv
    """
    ts_str = export_timestamp.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    file_name = f"service_photo_export_{job_number}_{ts_str}.csv"

    exports_dir = Path(settings.STORAGE_BASE_PATH) / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    file_path = str(exports_dir / file_name)

    with open(file_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        # Write only the columns in CSV_COLUMNS order; extra keys are ignored.
        writer.writerow({col: row_data.get(col, "") for col in CSV_COLUMNS})

    return file_name, file_path
