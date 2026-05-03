"""ORM model for listing_review_overview — human-reviewed identification and condition."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from service_photo.db.base import Base


class ListingReviewOverview(Base):
    __tablename__ = "listing_review_overview"

    review_overview_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("listing_jobs.job_id", ondelete="CASCADE"), nullable=False, unique=True)
    # Required for approval per approval_validation_rules.md.
    product_name: Mapped[str] = mapped_column(Text, nullable=False)
    brand: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_family: Mapped[str | None] = mapped_column(Text, nullable=True)
    variant: Mapped[str | None] = mapped_column(Text, nullable=True)
    mount_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    serial_number_visible: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Required for approval.
    condition_summary: Mapped[str] = mapped_column(Text, nullable=False)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_edited_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    last_edited_by: Mapped[str | None] = mapped_column(Text, nullable=True)

    job = relationship("ListingJob", back_populates="review_overview")

    __table_args__ = (
        Index("idx_listing_review_overview_job_id", "job_id"),
        Index("idx_listing_review_overview_brand_model", "brand", "model"),
    )
