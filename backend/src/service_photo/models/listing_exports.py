"""ORM model for listing_exports — one record per generated export file."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from service_photo.db.base import Base


class ListingExport(Base):
    __tablename__ = "listing_exports"

    export_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("listing_jobs.job_id", ondelete="CASCADE"), nullable=False)
    export_type: Mapped[str] = mapped_column(Text, nullable=False)
    export_file_name: Mapped[str] = mapped_column(Text, nullable=False)
    export_file_path: Mapped[str] = mapped_column(Text, nullable=False)
    exported_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    exported_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    export_status: Mapped[str] = mapped_column(Text, nullable=False)
    # JSONB snapshot of the exact reviewed content used in this export.
    export_payload_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    job = relationship("ListingJob", back_populates="exports")

    __table_args__ = (
        Index("idx_listing_exports_job_id", "job_id"),
        Index("idx_listing_exports_exported_at", "exported_at"),
    )
