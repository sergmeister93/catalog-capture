"""
Export service.

Handles POST /jobs/{job_id}/export: reads reviewed content only, generates a
one-row CSV, writes it to storage, creates the listing_exports row, and
transitions the job to 'exported'.

Reads exclusively from the review tables. Draft content is never used.
"""

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from service_photo.models.listing_job import ListingJob
from service_photo.repositories import jobs as job_repo
from service_photo.repositories import review as review_repo
from service_photo.repositories import exports as export_repo
from service_photo.exports.csv_generator import generate_csv_row, write_csv_to_storage
from service_photo.schemas.export import ListingExport as ListingExportSchema


def export_job(
    db: Session,
    job: ListingJob,
    exported_by: str | None,
) -> ListingExportSchema:
    """
    Generate a CSV export for the given approved job.

    Raises HTTPException:
      - 409 if job is not in 'approved' status
      - 500 if the CSV file write fails
    """
    if job.status != "approved":
        raise HTTPException(
            status_code=409,
            detail={"error": "invalid_status_for_export", "message": f"Job must be in approved status to export. Current: '{job.status}'."},
        )

    # Fetch reviewed content — export must never read draft tables.
    r_overview = review_repo.get_review_overview(db, job.job_id)
    r_description = review_repo.get_review_description(db, job.job_id)
    r_specifications = review_repo.get_review_specifications(db, job.job_id)
    r_accessories = review_repo.get_review_accessories(db, job.job_id)

    # Belt-and-suspenders: the approval gate should have enforced these, but
    # fail safely if data is unexpectedly missing.
    missing = [
        name for name, row in [
            ("listing_review_overview", r_overview),
            ("listing_review_description", r_description),
            ("listing_review_specifications", r_specifications),
            ("listing_review_accessories", r_accessories),
        ] if row is None
    ]
    if missing:
        raise HTTPException(
            status_code=500,
            detail={"error": "export_write_failed", "message": f"Required reviewed sections are missing: {missing}"},
        )

    export_timestamp = datetime.now(timezone.utc)

    # Build the CSV row data dict.
    row_data = generate_csv_row(job, r_overview, r_description, r_specifications, r_accessories, export_timestamp)

    # Write the CSV file to storage.
    try:
        file_name, file_path = write_csv_to_storage(job.job_number, row_data, export_timestamp)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "export_write_failed", "message": f"Failed to write export file: {exc}"},
        ) from exc

    # Build the payload snapshot.
    export_snapshot = {
        "job": {
            "job_id": str(job.job_id),
            "job_number": job.job_number,
            "item_category": job.item_category,
            "approved_at": job.approved_at.isoformat() if job.approved_at else None,
            "approved_by": job.approved_by,
        },
        "review": {
            "overview": _orm_to_dict(r_overview, ["review_overview_id", "job_id", "last_edited_at", "last_edited_by", "review_notes"]),
            "description": _orm_to_dict(r_description, ["review_description_id", "job_id", "last_edited_at", "last_edited_by", "review_notes"]),
            "specifications": _orm_to_dict(r_specifications, ["review_specifications_id", "job_id", "last_edited_at", "last_edited_by", "review_notes"]),
            "accessories": _orm_to_dict(r_accessories, ["review_accessories_id", "job_id", "last_edited_at", "last_edited_by", "review_notes"]),
        },
        "export": {
            "export_type": "csv",
            "exported_at": export_timestamp.isoformat(),
        },
    }

    # Insert the export record.
    export_row = export_repo.create_export(
        db=db,
        job_id=job.job_id,
        export_type="csv",
        export_file_name=file_name,
        export_file_path=file_path,
        exported_at=export_timestamp,
        exported_by=exported_by,
        export_status="success",
        export_payload_snapshot=export_snapshot,
    )

    # Transition job → exported.
    job_repo.update_job_status(db, job, "exported", export_timestamp, exported_at=export_timestamp)
    job_repo.add_status_history(db, job.job_id, "approved", "exported", exported_by, "CSV export generated", export_timestamp)

    return ListingExportSchema.model_validate(export_row)


def _orm_to_dict(orm_obj, exclude_fields: list[str]) -> dict:
    """Serialize a simple ORM row to a plain dict, excluding specified fields."""
    if orm_obj is None:
        return {}
    result = {}
    for col in orm_obj.__table__.columns:
        if col.name in exclude_fields:
            continue
        value = getattr(orm_obj, col.name)
        if isinstance(value, datetime):
            result[col.name] = value.isoformat()
        elif isinstance(value, Decimal):
            # JSONB column uses default json.dumps, which can't serialize
            # Decimal. Store as string to preserve precision (float would
            # round). Consumers that need arithmetic can cast back.
            result[col.name] = str(value)
        else:
            result[col.name] = value
    return result
