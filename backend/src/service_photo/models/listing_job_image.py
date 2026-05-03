"""ORM model for listing_job_images — image metadata per job."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, Text, TIMESTAMP, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from service_photo.db.base import Base


class ListingJobImage(Base):
    __tablename__ = "listing_job_images"

    image_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("listing_jobs.job_id", ondelete="CASCADE"), nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_type: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    image_order: Mapped[int] = mapped_column(Integer, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    uploaded_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    uploaded_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum: Mapped[str | None] = mapped_column(Text, nullable=True)

    job = relationship("ListingJob", back_populates="images")

    __table_args__ = (
        UniqueConstraint("job_id", "image_order", name="uq_listing_job_images_job_order"),
        Index("idx_listing_job_images_job_id", "job_id"),
        Index("idx_listing_job_images_uploaded_at", "uploaded_at"),
    )
