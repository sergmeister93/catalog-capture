# Service Photo POC — Initial PostgreSQL Migration Script

## Purpose

This document provides the **initial PostgreSQL migration SQL** for the Phase 1
Service Photo POC database.

It creates the core schema required to support:

- listing job creation
- image registration
- job status history
- AI draft content storage
- reviewed content storage
- export tracking

This migration is aligned to the Phase 1 physical schema and backend workflow.

The runnable SQL file is at:
`backend/src/service_photo/db/migrations/initial_schema.sql`

---

## Assumptions

- PostgreSQL 15+
- UUID values are generated in the application layer
- Timestamps are managed by the application layer unless otherwise noted
- Binary image files are stored outside PostgreSQL; only metadata is stored here
- Optional enrichment tables are **not** included in this migration

---

## Migration SQL

```sql
BEGIN;

-- ============================================================================
-- TABLE: listing_jobs
-- ============================================================================
CREATE TABLE listing_jobs (
    job_id UUID PRIMARY KEY,
    job_number TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by TEXT,
    reviewed_by TEXT,
    approved_by TEXT,
    status TEXT NOT NULL,
    item_category TEXT,
    is_reviews_enriched BOOLEAN NOT NULL DEFAULT false,
    is_price_enriched BOOLEAN NOT NULL DEFAULT false,
    approved_at TIMESTAMPTZ,
    exported_at TIMESTAMPTZ,
    notes TEXT
);

CREATE INDEX idx_listing_jobs_status
    ON listing_jobs (status);

CREATE INDEX idx_listing_jobs_created_at
    ON listing_jobs (created_at);

CREATE INDEX idx_listing_jobs_item_category
    ON listing_jobs (item_category);

-- ============================================================================
-- TABLE: listing_job_images
-- ============================================================================
CREATE TABLE listing_job_images (
    image_id UUID PRIMARY KEY,
    job_id UUID NOT NULL,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_size_bytes BIGINT,
    image_order INTEGER NOT NULL,
    is_primary BOOLEAN NOT NULL DEFAULT false,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    uploaded_by TEXT,
    checksum TEXT,
    CONSTRAINT fk_listing_job_images_job
        FOREIGN KEY (job_id)
        REFERENCES listing_jobs (job_id)
        ON DELETE CASCADE,
    CONSTRAINT uq_listing_job_images_job_order
        UNIQUE (job_id, image_order)
);

CREATE INDEX idx_listing_job_images_job_id
    ON listing_job_images (job_id);

CREATE INDEX idx_listing_job_images_uploaded_at
    ON listing_job_images (uploaded_at);

-- Optional future improvement:
-- Create a partial unique index to enforce only one primary image per job.
-- Example:
-- CREATE UNIQUE INDEX uq_listing_job_images_one_primary_per_job
--     ON listing_job_images (job_id)
--     WHERE is_primary = true;

-- ============================================================================
-- TABLE: listing_job_status_history
-- ============================================================================
CREATE TABLE listing_job_status_history (
    status_history_id UUID PRIMARY KEY,
    job_id UUID NOT NULL,
    old_status TEXT,
    new_status TEXT NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    changed_by TEXT,
    change_reason TEXT,
    CONSTRAINT fk_listing_job_status_history_job
        FOREIGN KEY (job_id)
        REFERENCES listing_jobs (job_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_listing_job_status_history_job_id
    ON listing_job_status_history (job_id);

CREATE INDEX idx_listing_job_status_history_changed_at
    ON listing_job_status_history (changed_at);

-- ============================================================================
-- TABLE: listing_draft_overview
-- ============================================================================
CREATE TABLE listing_draft_overview (
    draft_overview_id UUID PRIMARY KEY,
    job_id UUID NOT NULL UNIQUE,
    product_name TEXT,
    brand TEXT,
    model TEXT,
    product_family TEXT,
    variant TEXT,
    mount_type TEXT,
    serial_number_visible TEXT,
    condition_summary TEXT,
    confidence_notes TEXT,
    -- Top-level Gemini response field; stored here as it accompanies the
    -- overview extraction and has no natural home in a section-specific table.
    extraction_warnings JSONB,
    raw_source_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_listing_draft_overview_job
        FOREIGN KEY (job_id)
        REFERENCES listing_jobs (job_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_listing_draft_overview_job_id
    ON listing_draft_overview (job_id);

-- ============================================================================
-- TABLE: listing_draft_description
-- ============================================================================
CREATE TABLE listing_draft_description (
    draft_description_id UUID PRIMARY KEY,
    job_id UUID NOT NULL UNIQUE,
    short_title TEXT,
    description_text TEXT,
    visible_wear_notes TEXT,
    key_selling_points TEXT,
    confidence_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_listing_draft_description_job
        FOREIGN KEY (job_id)
        REFERENCES listing_jobs (job_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_listing_draft_description_job_id
    ON listing_draft_description (job_id);

-- ============================================================================
-- TABLE: listing_draft_specifications
-- ============================================================================
CREATE TABLE listing_draft_specifications (
    draft_specifications_id UUID PRIMARY KEY,
    job_id UUID NOT NULL UNIQUE,
    sensor_format TEXT,
    megapixels NUMERIC(6,2),
    lens_mount TEXT,
    focal_length TEXT,
    aperture TEXT,
    iso_range TEXT,
    shutter_range TEXT,
    video_capabilities TEXT,
    storage_media TEXT,
    connectivity TEXT,
    weight_grams INTEGER,
    other_specifications JSONB,
    confidence_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_listing_draft_specifications_job
        FOREIGN KEY (job_id)
        REFERENCES listing_jobs (job_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_listing_draft_specifications_job_id
    ON listing_draft_specifications (job_id);

-- ============================================================================
-- TABLE: listing_draft_accessories
-- ============================================================================
CREATE TABLE listing_draft_accessories (
    draft_accessories_id UUID PRIMARY KEY,
    job_id UUID NOT NULL UNIQUE,
    included_accessories_text TEXT,
    inferred_accessories_text TEXT,
    missing_typical_accessories_text TEXT,
    confidence_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_listing_draft_accessories_job
        FOREIGN KEY (job_id)
        REFERENCES listing_jobs (job_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_listing_draft_accessories_job_id
    ON listing_draft_accessories (job_id);

-- ============================================================================
-- TABLE: listing_review_overview
-- ============================================================================
CREATE TABLE listing_review_overview (
    review_overview_id UUID PRIMARY KEY,
    job_id UUID NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    brand TEXT,
    model TEXT,
    product_family TEXT,
    variant TEXT,
    mount_type TEXT,
    serial_number_visible TEXT,
    condition_summary TEXT NOT NULL,
    review_notes TEXT,
    last_edited_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_edited_by TEXT,
    CONSTRAINT fk_listing_review_overview_job
        FOREIGN KEY (job_id)
        REFERENCES listing_jobs (job_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_listing_review_overview_job_id
    ON listing_review_overview (job_id);

CREATE INDEX idx_listing_review_overview_brand_model
    ON listing_review_overview (brand, model);

-- ============================================================================
-- TABLE: listing_review_description
-- ============================================================================
CREATE TABLE listing_review_description (
    review_description_id UUID PRIMARY KEY,
    job_id UUID NOT NULL UNIQUE,
    short_title TEXT NOT NULL,
    description_text TEXT NOT NULL,
    visible_wear_notes TEXT,
    key_selling_points TEXT,
    review_notes TEXT,
    last_edited_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_edited_by TEXT,
    CONSTRAINT fk_listing_review_description_job
        FOREIGN KEY (job_id)
        REFERENCES listing_jobs (job_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_listing_review_description_job_id
    ON listing_review_description (job_id);

-- ============================================================================
-- TABLE: listing_review_specifications
-- ============================================================================
CREATE TABLE listing_review_specifications (
    review_specifications_id UUID PRIMARY KEY,
    job_id UUID NOT NULL UNIQUE,
    sensor_format TEXT,
    megapixels NUMERIC(6,2),
    lens_mount TEXT,
    focal_length TEXT,
    aperture TEXT,
    iso_range TEXT,
    shutter_range TEXT,
    video_capabilities TEXT,
    storage_media TEXT,
    connectivity TEXT,
    weight_grams INTEGER,
    other_specifications JSONB,
    review_notes TEXT,
    last_edited_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_edited_by TEXT,
    CONSTRAINT fk_listing_review_specifications_job
        FOREIGN KEY (job_id)
        REFERENCES listing_jobs (job_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_listing_review_specifications_job_id
    ON listing_review_specifications (job_id);

-- ============================================================================
-- TABLE: listing_review_accessories
-- ============================================================================
CREATE TABLE listing_review_accessories (
    review_accessories_id UUID PRIMARY KEY,
    job_id UUID NOT NULL UNIQUE,
    included_accessories_text TEXT NOT NULL,
    inferred_accessories_text TEXT,
    missing_typical_accessories_text TEXT,
    review_notes TEXT,
    last_edited_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_edited_by TEXT,
    CONSTRAINT fk_listing_review_accessories_job
        FOREIGN KEY (job_id)
        REFERENCES listing_jobs (job_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_listing_review_accessories_job_id
    ON listing_review_accessories (job_id);

-- ============================================================================
-- TABLE: listing_exports
-- ============================================================================
CREATE TABLE listing_exports (
    export_id UUID PRIMARY KEY,
    job_id UUID NOT NULL,
    export_type TEXT NOT NULL,
    export_file_name TEXT NOT NULL,
    export_file_path TEXT NOT NULL,
    exported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    exported_by TEXT,
    export_status TEXT NOT NULL,
    export_payload_snapshot JSONB,
    CONSTRAINT fk_listing_exports_job
        FOREIGN KEY (job_id)
        REFERENCES listing_jobs (job_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_listing_exports_job_id
    ON listing_exports (job_id);

CREATE INDEX idx_listing_exports_exported_at
    ON listing_exports (exported_at);

COMMIT;
```

---

## What This Migration Creates

This migration creates the full Phase 1 relational structure for the core workflow:

- one parent job row per item
- one-to-many image records per job
- append-only status history per job
- one-to-one draft tables for AI output
- one-to-one review tables for human-edited content
- one-to-many export records per job

The reviewed layer is the source of truth for approval and export.

---

## Notes for Implementation

### 1. Status values
For Phase 1, `status`, `old_status`, `new_status`, and `export_status` are stored as
plain `TEXT` values. Application code should enforce valid values.

**Valid core statuses** (from `docs/02_physical_schema_spec.md §5`):
- `uploaded`
- `initialized`
- `submitted_to_ai`
- `ai_response_received`
- `ready_for_review`
- `under_review`
- `approved`
- `exported`

**Valid exception statuses:**
- `validation_failed`
- `ai_error`
- `needs_rework`
- `rejected`

### 2. UUID generation
This migration assumes UUIDs are generated by the application. If preferred, this can
be changed later to use PostgreSQL-generated UUIDs via `gen_random_uuid()`.

### 3. Timestamp ownership
The DDL uses `DEFAULT now()` for safety, but the application should still explicitly
set timestamps to maintain deterministic workflow behavior.

### 4. Approval enforcement
This migration does **not** embed the approval gate in database check constraints.
Approval rules should be enforced by backend application logic per
`contracts/approval_validation_rules.md`.

### 5. JSONB usage
JSONB is used only where flexible payload storage is valuable:

- `listing_draft_overview.extraction_warnings` — top-level Gemini warnings array
- `listing_draft_overview.raw_source_payload` — full raw Gemini response for traceability
- `listing_draft_specifications.other_specifications`
- `listing_review_specifications.other_specifications`
- `listing_exports.export_payload_snapshot`

### 6. extraction_warnings
The `extraction_warnings` field is a top-level field in the Gemini response schema
(`contracts/gemini_response_schema.json`). It captures high-level extraction warnings
that are not section-specific. It is stored on `listing_draft_overview` because that
is the first draft record written for a job and serves as the natural anchor for
job-level Gemini metadata. It is stored as `JSONB` to hold the JSON array (or null)
returned by Gemini without transformation.

---

## Recommended Next Step

After this migration, the next project artifact should be **seed/test data** covering:

- a newly initialized job
- a job with registered images
- a job with AI draft output
- a job under review with reviewed content
- an approved job
- an exported job
- at least one failed approval scenario

That will give the backend something realistic to run against before API implementation.
