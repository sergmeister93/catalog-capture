"""ORM model for listing_jobs — the parent record for one item workflow."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Index, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from service_photo.db.base import Base


class ListingJob(Base):
    __tablename__ = "listing_jobs"

    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_number: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    created_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    item_category: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_reviews_enriched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_price_enriched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    exported_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    images = relationship("ListingJobImage", back_populates="job", cascade="all, delete-orphan", order_by="ListingJobImage.image_order")
    status_history = relationship("ListingJobStatusHistory", back_populates="job", cascade="all, delete-orphan", order_by="ListingJobStatusHistory.changed_at")
    draft_overview = relationship("ListingDraftOverview", back_populates="job", uselist=False, cascade="all, delete-orphan")
    draft_description = relationship("ListingDraftDescription", back_populates="job", uselist=False, cascade="all, delete-orphan")
    draft_specifications = relationship("ListingDraftSpecifications", back_populates="job", uselist=False, cascade="all, delete-orphan")
    draft_accessories = relationship("ListingDraftAccessories", back_populates="job", uselist=False, cascade="all, delete-orphan")
    review_overview = relationship("ListingReviewOverview", back_populates="job", uselist=False, cascade="all, delete-orphan")
    review_description = relationship("ListingReviewDescription", back_populates="job", uselist=False, cascade="all, delete-orphan")
    review_specifications = relationship("ListingReviewSpecifications", back_populates="job", uselist=False, cascade="all, delete-orphan")
    review_accessories = relationship("ListingReviewAccessories", back_populates="job", uselist=False, cascade="all, delete-orphan")
    exports = relationship("ListingExport", back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_listing_jobs_status", "status"),
        Index("idx_listing_jobs_created_at", "created_at"),
        Index("idx_listing_jobs_item_category", "item_category"),
    )
