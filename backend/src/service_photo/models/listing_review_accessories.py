"""ORM model for listing_review_accessories — human-reviewed accessories."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from service_photo.db.base import Base


class ListingReviewAccessories(Base):
    __tablename__ = "listing_review_accessories"

    review_accessories_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("listing_jobs.job_id", ondelete="CASCADE"), nullable=False, unique=True)
    # Required for approval.
    included_accessories_text: Mapped[str] = mapped_column(Text, nullable=False)
    inferred_accessories_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    missing_typical_accessories_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_edited_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    last_edited_by: Mapped[str | None] = mapped_column(Text, nullable=True)

    job = relationship("ListingJob", back_populates="review_accessories")

    __table_args__ = (
        Index("idx_listing_review_accessories_job_id", "job_id"),
    )
