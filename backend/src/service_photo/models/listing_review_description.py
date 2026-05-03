"""ORM model for listing_review_description — human-reviewed listing copy."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from service_photo.db.base import Base


class ListingReviewDescription(Base):
    __tablename__ = "listing_review_description"

    review_description_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("listing_jobs.job_id", ondelete="CASCADE"), nullable=False, unique=True)
    # Both fields are required for approval.
    short_title: Mapped[str] = mapped_column(Text, nullable=False)
    description_text: Mapped[str] = mapped_column(Text, nullable=False)
    visible_wear_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_selling_points: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_edited_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    last_edited_by: Mapped[str | None] = mapped_column(Text, nullable=True)

    job = relationship("ListingJob", back_populates="review_description")

    __table_args__ = (
        Index("idx_listing_review_description_job_id", "job_id"),
    )
