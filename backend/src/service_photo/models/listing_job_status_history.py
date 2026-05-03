"""ORM model for listing_job_status_history — append-only status audit log."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from service_photo.db.base import Base


class ListingJobStatusHistory(Base):
    __tablename__ = "listing_job_status_history"

    status_history_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("listing_jobs.job_id", ondelete="CASCADE"), nullable=False)
    old_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_status: Mapped[str] = mapped_column(Text, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    changed_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    job = relationship("ListingJob", back_populates="status_history")

    __table_args__ = (
        Index("idx_listing_job_status_history_job_id", "job_id"),
        Index("idx_listing_job_status_history_changed_at", "changed_at"),
    )
