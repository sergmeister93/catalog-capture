"""Repository helpers for listing_exports."""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from service_photo.models.listing_exports import ListingExport


def create_export(
    db: Session,
    job_id: uuid.UUID,
    export_type: str,
    export_file_name: str,
    export_file_path: str,
    exported_at: datetime,
    exported_by: str | None,
    export_status: str,
    export_payload_snapshot: dict | None,
) -> ListingExport:
    """Insert a new listing_exports row and return it."""
    row = ListingExport(
        export_id=uuid.uuid4(),
        job_id=job_id,
        export_type=export_type,
        export_file_name=export_file_name,
        export_file_path=export_file_path,
        exported_at=exported_at,
        exported_by=exported_by,
        export_status=export_status,
        export_payload_snapshot=export_payload_snapshot,
    )
    db.add(row)
    db.flush()
    return row
