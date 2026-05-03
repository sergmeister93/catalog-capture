"""Pydantic schemas for review (human-edited) content layers and request inputs."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from service_photo.schemas.jobs import ListingJob, ListingJobImage
    from service_photo.schemas.draft import DraftContent


# ---------------------------------------------------------------------------
# Review section response schemas (read)
# ---------------------------------------------------------------------------

class ReviewOverview(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    review_overview_id: uuid.UUID
    job_id: uuid.UUID
    product_name: str
    brand: str | None = None
    model: str | None = None
    product_family: str | None = None
    variant: str | None = None
    mount_type: str | None = None
    serial_number_visible: str | None = None
    condition_summary: str
    review_notes: str | None = None
    last_edited_at: datetime
    last_edited_by: str | None = None


class ReviewDescription(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    review_description_id: uuid.UUID
    job_id: uuid.UUID
    short_title: str
    description_text: str
    visible_wear_notes: str | None = None
    key_selling_points: str | None = None
    review_notes: str | None = None
    last_edited_at: datetime
    last_edited_by: str | None = None


class ReviewSpecifications(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    review_specifications_id: uuid.UUID
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
    review_notes: str | None = None
    last_edited_at: datetime
    last_edited_by: str | None = None


class ReviewAccessories(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    review_accessories_id: uuid.UUID
    job_id: uuid.UUID
    included_accessories_text: str
    inferred_accessories_text: str | None = None
    missing_typical_accessories_text: str | None = None
    review_notes: str | None = None
    last_edited_at: datetime
    last_edited_by: str | None = None


class ReviewContent(BaseModel):
    """All four review sections combined; any section may be None before the reviewer saves it."""
    overview: ReviewOverview | None = None
    description: ReviewDescription | None = None
    specifications: ReviewSpecifications | None = None
    accessories: ReviewAccessories | None = None


# ---------------------------------------------------------------------------
# Review payload (GET /jobs/{id}/review-payload response)
# ---------------------------------------------------------------------------

class ReviewPayload(BaseModel):
    """Full review payload: job + images + draft + review."""
    job: "ListingJob"
    images: list["ListingJobImage"]
    draft: "DraftContent"
    review: ReviewContent


# ---------------------------------------------------------------------------
# Review section input schemas (write)
# ---------------------------------------------------------------------------

class ReviewOverviewInput(BaseModel):
    product_name: str = Field(min_length=1)
    brand: str | None = None
    model: str | None = None
    product_family: str | None = None
    variant: str | None = None
    mount_type: str | None = None
    serial_number_visible: str | None = None
    condition_summary: str = Field(min_length=1)
    review_notes: str | None = None


class ReviewDescriptionInput(BaseModel):
    short_title: str = Field(min_length=1)
    description_text: str = Field(min_length=1)
    visible_wear_notes: str | None = None
    key_selling_points: str | None = None
    review_notes: str | None = None


class ReviewSpecificationsInput(BaseModel):
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
    review_notes: str | None = None


class ReviewAccessoriesInput(BaseModel):
    included_accessories_text: str = Field(min_length=1)
    inferred_accessories_text: str | None = None
    missing_typical_accessories_text: str | None = None
    review_notes: str | None = None


class SaveReviewInput(BaseModel):
    """PUT /jobs/{id}/review request body; at least one section must be present."""
    reviewed_by: str | None = None
    overview: ReviewOverviewInput | None = None
    description: ReviewDescriptionInput | None = None
    specifications: ReviewSpecificationsInput | None = None
    accessories: ReviewAccessoriesInput | None = None


# ---------------------------------------------------------------------------
# Resolve forward references at module import time.
#
# ReviewPayload references ListingJob / ListingJobImage / DraftContent as
# string forward refs (gated behind TYPE_CHECKING above so we don't get
# circular-import headaches at the top of the file). FastAPI builds a
# TypeAdapter for ReviewPayload the moment the @router.get(..., response_model=
# ReviewPayload) decorator runs in api/routes.py, so those forward refs MUST
# be resolved before routes.py imports this module. Doing the real imports +
# model_rebuild() at the bottom here guarantees that: by the time anyone
# successfully imports ReviewPayload from this module, it is fully built.
# ---------------------------------------------------------------------------
from service_photo.schemas.jobs import ListingJob, ListingJobImage  # noqa: E402
from service_photo.schemas.draft import DraftContent  # noqa: E402

ReviewPayload.model_rebuild()
