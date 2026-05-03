"""ORM model for listing_draft_description — AI-generated listing copy."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from service_photo.db.base import Base


class ListingDraftDescription(Base):
    __tablename__ = "listing_draft_description"

    draft_description_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("listing_jobs.job_id", ondelete="CASCADE"), nullable=False, unique=True)
    short_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    visible_wear_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_selling_points: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    job = relationship("ListingJob", back_populates="draft_description")

    __table_args__ = (
        Index("idx_listing_draft_description_job_id", "job_id"),
    )
