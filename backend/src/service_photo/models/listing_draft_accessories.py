"""ORM model for listing_draft_accessories — AI-generated accessory observations."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from service_photo.db.base import Base


class ListingDraftAccessories(Base):
    __tablename__ = "listing_draft_accessories"

    draft_accessories_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("listing_jobs.job_id", ondelete="CASCADE"), nullable=False, unique=True)
    included_accessories_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    inferred_accessories_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    missing_typical_accessories_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    job = relationship("ListingJob", back_populates="draft_accessories")

    __table_args__ = (
        Index("idx_listing_draft_accessories_job_id", "job_id"),
    )
