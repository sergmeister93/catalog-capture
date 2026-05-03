"""ORM model for listing_draft_overview — AI-generated identification and condition summary."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Text, TIMESTAMP, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from service_photo.db.base import Base


class ListingDraftOverview(Base):
    __tablename__ = "listing_draft_overview"

    draft_overview_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("listing_jobs.job_id", ondelete="CASCADE"), nullable=False, unique=True)
    product_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_family: Mapped[str | None] = mapped_column(Text, nullable=True)
    variant: Mapped[str | None] = mapped_column(Text, nullable=True)
    mount_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    serial_number_visible: Mapped[str | None] = mapped_column(Text, nullable=True)
    condition_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Top-level Gemini response field; JSON array of warning strings or null.
    extraction_warnings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Full raw Gemini JSON response for debugging/traceability.
    raw_source_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    job = relationship("ListingJob", back_populates="draft_overview")

    __table_args__ = (
        Index("idx_listing_draft_overview_job_id", "job_id"),
    )
