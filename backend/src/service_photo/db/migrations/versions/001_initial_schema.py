"""Initial schema — all 12 Phase 1 tables.

Revision ID: 001
Revises:
Create Date: 2026-04-19

This migration is equivalent to running initial_schema.sql directly but
is managed through Alembic so subsequent migrations can build on it.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # listing_jobs
    op.create_table(
        "listing_jobs",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_number", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("item_category", sa.Text(), nullable=True),
        sa.Column("is_reviews_enriched", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_price_enriched", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("approved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("exported_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("job_id"),
        sa.UniqueConstraint("job_number"),
    )
    op.create_index("idx_listing_jobs_status", "listing_jobs", ["status"])
    op.create_index("idx_listing_jobs_created_at", "listing_jobs", ["created_at"])
    op.create_index("idx_listing_jobs_item_category", "listing_jobs", ["item_category"])

    # listing_job_images
    op.create_table(
        "listing_job_images",
        sa.Column("image_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("file_type", sa.Text(), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("image_order", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("uploaded_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("uploaded_by", sa.Text(), nullable=True),
        sa.Column("checksum", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["listing_jobs.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("image_id"),
        sa.UniqueConstraint("job_id", "image_order", name="uq_listing_job_images_job_order"),
    )
    op.create_index("idx_listing_job_images_job_id", "listing_job_images", ["job_id"])
    op.create_index("idx_listing_job_images_uploaded_at", "listing_job_images", ["uploaded_at"])

    # listing_job_status_history
    op.create_table(
        "listing_job_status_history",
        sa.Column("status_history_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("old_status", sa.Text(), nullable=True),
        sa.Column("new_status", sa.Text(), nullable=False),
        sa.Column("changed_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("changed_by", sa.Text(), nullable=True),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["listing_jobs.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("status_history_id"),
    )
    op.create_index("idx_listing_job_status_history_job_id", "listing_job_status_history", ["job_id"])
    op.create_index("idx_listing_job_status_history_changed_at", "listing_job_status_history", ["changed_at"])

    # listing_draft_overview
    op.create_table(
        "listing_draft_overview",
        sa.Column("draft_overview_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_name", sa.Text(), nullable=True),
        sa.Column("brand", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("product_family", sa.Text(), nullable=True),
        sa.Column("variant", sa.Text(), nullable=True),
        sa.Column("mount_type", sa.Text(), nullable=True),
        sa.Column("serial_number_visible", sa.Text(), nullable=True),
        sa.Column("condition_summary", sa.Text(), nullable=True),
        sa.Column("confidence_notes", sa.Text(), nullable=True),
        sa.Column("extraction_warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_source_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["job_id"], ["listing_jobs.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("draft_overview_id"),
        sa.UniqueConstraint("job_id"),
    )
    op.create_index("idx_listing_draft_overview_job_id", "listing_draft_overview", ["job_id"])

    # listing_draft_description
    op.create_table(
        "listing_draft_description",
        sa.Column("draft_description_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("short_title", sa.Text(), nullable=True),
        sa.Column("description_text", sa.Text(), nullable=True),
        sa.Column("visible_wear_notes", sa.Text(), nullable=True),
        sa.Column("key_selling_points", sa.Text(), nullable=True),
        sa.Column("confidence_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["job_id"], ["listing_jobs.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("draft_description_id"),
        sa.UniqueConstraint("job_id"),
    )
    op.create_index("idx_listing_draft_description_job_id", "listing_draft_description", ["job_id"])

    # listing_draft_specifications
    op.create_table(
        "listing_draft_specifications",
        sa.Column("draft_specifications_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sensor_format", sa.Text(), nullable=True),
        sa.Column("megapixels", sa.Numeric(6, 2), nullable=True),
        sa.Column("lens_mount", sa.Text(), nullable=True),
        sa.Column("focal_length", sa.Text(), nullable=True),
        sa.Column("aperture", sa.Text(), nullable=True),
        sa.Column("iso_range", sa.Text(), nullable=True),
        sa.Column("shutter_range", sa.Text(), nullable=True),
        sa.Column("video_capabilities", sa.Text(), nullable=True),
        sa.Column("storage_media", sa.Text(), nullable=True),
        sa.Column("connectivity", sa.Text(), nullable=True),
        sa.Column("weight_grams", sa.Integer(), nullable=True),
        sa.Column("other_specifications", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confidence_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["job_id"], ["listing_jobs.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("draft_specifications_id"),
        sa.UniqueConstraint("job_id"),
    )
    op.create_index("idx_listing_draft_specifications_job_id", "listing_draft_specifications", ["job_id"])

    # listing_draft_accessories
    op.create_table(
        "listing_draft_accessories",
        sa.Column("draft_accessories_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("included_accessories_text", sa.Text(), nullable=True),
        sa.Column("inferred_accessories_text", sa.Text(), nullable=True),
        sa.Column("missing_typical_accessories_text", sa.Text(), nullable=True),
        sa.Column("confidence_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["job_id"], ["listing_jobs.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("draft_accessories_id"),
        sa.UniqueConstraint("job_id"),
    )
    op.create_index("idx_listing_draft_accessories_job_id", "listing_draft_accessories", ["job_id"])

    # listing_review_overview
    op.create_table(
        "listing_review_overview",
        sa.Column("review_overview_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_name", sa.Text(), nullable=False),
        sa.Column("brand", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("product_family", sa.Text(), nullable=True),
        sa.Column("variant", sa.Text(), nullable=True),
        sa.Column("mount_type", sa.Text(), nullable=True),
        sa.Column("serial_number_visible", sa.Text(), nullable=True),
        sa.Column("condition_summary", sa.Text(), nullable=False),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("last_edited_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_edited_by", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["listing_jobs.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("review_overview_id"),
        sa.UniqueConstraint("job_id"),
    )
    op.create_index("idx_listing_review_overview_job_id", "listing_review_overview", ["job_id"])
    op.create_index("idx_listing_review_overview_brand_model", "listing_review_overview", ["brand", "model"])

    # listing_review_description
    op.create_table(
        "listing_review_description",
        sa.Column("review_description_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("short_title", sa.Text(), nullable=False),
        sa.Column("description_text", sa.Text(), nullable=False),
        sa.Column("visible_wear_notes", sa.Text(), nullable=True),
        sa.Column("key_selling_points", sa.Text(), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("last_edited_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_edited_by", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["listing_jobs.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("review_description_id"),
        sa.UniqueConstraint("job_id"),
    )
    op.create_index("idx_listing_review_description_job_id", "listing_review_description", ["job_id"])

    # listing_review_specifications
    op.create_table(
        "listing_review_specifications",
        sa.Column("review_specifications_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sensor_format", sa.Text(), nullable=True),
        sa.Column("megapixels", sa.Numeric(6, 2), nullable=True),
        sa.Column("lens_mount", sa.Text(), nullable=True),
        sa.Column("focal_length", sa.Text(), nullable=True),
        sa.Column("aperture", sa.Text(), nullable=True),
        sa.Column("iso_range", sa.Text(), nullable=True),
        sa.Column("shutter_range", sa.Text(), nullable=True),
        sa.Column("video_capabilities", sa.Text(), nullable=True),
        sa.Column("storage_media", sa.Text(), nullable=True),
        sa.Column("connectivity", sa.Text(), nullable=True),
        sa.Column("weight_grams", sa.Integer(), nullable=True),
        sa.Column("other_specifications", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("last_edited_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_edited_by", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["listing_jobs.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("review_specifications_id"),
        sa.UniqueConstraint("job_id"),
    )
    op.create_index("idx_listing_review_specifications_job_id", "listing_review_specifications", ["job_id"])

    # listing_review_accessories
    op.create_table(
        "listing_review_accessories",
        sa.Column("review_accessories_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("included_accessories_text", sa.Text(), nullable=False),
        sa.Column("inferred_accessories_text", sa.Text(), nullable=True),
        sa.Column("missing_typical_accessories_text", sa.Text(), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("last_edited_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_edited_by", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["listing_jobs.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("review_accessories_id"),
        sa.UniqueConstraint("job_id"),
    )
    op.create_index("idx_listing_review_accessories_job_id", "listing_review_accessories", ["job_id"])

    # listing_exports
    op.create_table(
        "listing_exports",
        sa.Column("export_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("export_type", sa.Text(), nullable=False),
        sa.Column("export_file_name", sa.Text(), nullable=False),
        sa.Column("export_file_path", sa.Text(), nullable=False),
        sa.Column("exported_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("exported_by", sa.Text(), nullable=True),
        sa.Column("export_status", sa.Text(), nullable=False),
        sa.Column("export_payload_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["listing_jobs.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("export_id"),
    )
    op.create_index("idx_listing_exports_job_id", "listing_exports", ["job_id"])
    op.create_index("idx_listing_exports_exported_at", "listing_exports", ["exported_at"])


def downgrade() -> None:
    op.drop_table("listing_exports")
    op.drop_table("listing_review_accessories")
    op.drop_table("listing_review_specifications")
    op.drop_table("listing_review_description")
    op.drop_table("listing_review_overview")
    op.drop_table("listing_draft_accessories")
    op.drop_table("listing_draft_specifications")
    op.drop_table("listing_draft_description")
    op.drop_table("listing_draft_overview")
    op.drop_table("listing_job_status_history")
    op.drop_table("listing_job_images")
    op.drop_table("listing_jobs")
