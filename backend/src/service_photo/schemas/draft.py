"""Pydantic schemas for draft (AI-generated) content layers."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class DraftOverview(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    draft_overview_id: uuid.UUID
    job_id: uuid.UUID
    product_name: str | None = None
    brand: str | None = None
    model: str | None = None
    product_family: str | None = None
    variant: str | None = None
    mount_type: str | None = None
    serial_number_visible: str | None = None
    condition_summary: str | None = None
    confidence_notes: str | None = None
    # extraction_warnings excluded from review payload per review_payload_schema.json
    raw_source_payload: dict | None = None
    created_at: datetime


class DraftDescription(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    draft_description_id: uuid.UUID
    job_id: uuid.UUID
    short_title: str | None = None
    description_text: str | None = None
    visible_wear_notes: str | None = None
    key_selling_points: str | None = None
    confidence_notes: str | None = None
    created_at: datetime


class DraftSpecifications(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    draft_specifications_id: uuid.UUID
    job_id: uuid.UUID
    sensor_format: str | None = None
    megapixels: Decimal | None = None
    lens_mount: str | None = None
    focal_length: str | None = None
    aperture: str | None = None
    iso_range: str | None = None
    shutter_range: str | None = None
    video_capabilities: str | None = None
    storage_media: str | None = None
    connectivity: str | None = None
    weight_grams: int | None = None
    other_specifications: dict | None = None
    confidence_notes: str | None = None
    created_at: datetime


class DraftAccessories(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    draft_accessories_id: uuid.UUID
    job_id: uuid.UUID
    included_accessories_text: str | None = None
    inferred_accessories_text: str | None = None
    missing_typical_accessories_text: str | None = None
    confidence_notes: str | None = None
    created_at: datetime


class DraftContent(BaseModel):
    """All four draft sections combined; any section may be None."""
    overview: DraftOverview | None = None
    description: DraftDescription | None = None
    specifications: DraftSpecifications | None = None
    accessories: DraftAccessories | None = None
