"""ORM model for listing_draft_specifications — AI-generated structured specs."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from service_photo.db.base import Base


class ListingDraftSpecifications(Base):
    __tablename__ = "listing_draft_specifications"

    draft_specifications_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("listing_jobs.job_id", ondelete="CASCADE"), nullable=False, unique=True)
    sensor_format: Mapped[str | None] = mapped_column(Text, nullable=True)
    megapixels: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    lens_mount: Mapped[str | None] = mapped_column(Text, nullable=True)
    focal_length: Mapped[str | None] = mapped_column(Text, nullable=True)
    aperture: Mapped[str | None] = mapped_column(Text, nullable=True)
    iso_range: Mapped[str | None] = mapped_column(Text, nullable=True)
    shutter_range: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_capabilities: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_media: Mapped[str | None] = mapped_column(Text, nullable=True)
    connectivity: Mapped[str | None] = mapped_column(Text, nullable=True)
    weight_grams: Mapped[int | None] = mapped_column(Integer, nullable=True)
    other_specifications: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confidence_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    job = relationship("ListingJob", back_populates="draft_specifications")

    __table_args__ = (
        Index("idx_listing_draft_specifications_job_id", "job_id"),
    )
