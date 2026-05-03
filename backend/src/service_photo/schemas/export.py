"""Pydantic schema for listing_exports responses."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ListingExport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    export_id: uuid.UUID
    job_id: uuid.UUID
    export_type: Literal["csv"]
    export_file_name: str
    export_file_path: str
    exported_at: datetime
    exported_by: str | None = None
    export_status: Literal["success", "failed"]
    export_payload_snapshot: dict | None = None
