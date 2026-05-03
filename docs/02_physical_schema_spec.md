# Service Photo POC — Physical Schema Specification

## 1. Purpose

This document defines the **physical database schema** for the core phase of the **Service Photo POC**. It translates the logical, normalized design into an implementation-ready PostgreSQL schema that can be used to generate:

- SQL migration scripts
- ORM/data models
- backend validation models
- seed/test data
- API payload contracts

This physical schema is intentionally scoped to the **core POC workflow** only:

1. Create one listing job per item
2. Upload and store source images
3. Persist Gemini draft output
4. Persist user-reviewed/finalized content
5. Track workflow status changes
6. Export approved records

Optional enrichment for web reviews and price comparables is intentionally deferred to a later phase.

---

## 2. Technology Assumptions

### Database Engine
**PostgreSQL 15+**

### Design Conventions
- Use `UUID` primary keys for major entities
- Use `TIMESTAMPTZ` for audit timestamps
- Use `TEXT` unless a strict bounded `VARCHAR(n)` adds business value
- Use `JSONB` only where flexibility is necessary
- Enforce referential integrity with foreign keys
- Enforce one-to-one child table relationships with `UNIQUE(job_id)`
- Keep binary image files in storage; store only metadata/paths in the database

### Naming Conventions
- Table names: `snake_case`, plural where appropriate
- Column names: `snake_case`
- Primary keys: `<entity>_id`
- Foreign keys: `<parent>_id`
- Timestamps: `created_at`, `updated_at`, `last_edited_at`, `changed_at`, `exported_at`

---

## 3. Scope of Phase 1 Physical Schema

### Included Tables
- `listing_jobs`
- `listing_job_images`
- `listing_job_status_history`
- `listing_draft_overview`
- `listing_draft_description`
- `listing_draft_specifications`
- `listing_draft_accessories`
- `listing_review_overview`
- `listing_review_description`
- `listing_review_specifications`
- `listing_review_accessories`
- `listing_exports`

### Deferred Tables
The following are **not included** in this phase:
- review enrichment tables
- pricing recommendation tables
- source citation tables
- price comparables tables
- user/auth tables
- inventory integration tables

---

## 4. Workflow Model Supported by This Schema

```text
listing_jobs
  ├── listing_job_images
  ├── listing_job_status_history
  ├── listing_draft_overview
  ├── listing_draft_description
  ├── listing_draft_specifications
  ├── listing_draft_accessories
  ├── listing_review_overview
  ├── listing_review_description
  ├── listing_review_specifications
  ├── listing_review_accessories
  └── listing_exports
```

### Design Principle
This schema uses a **two-layer content model**:

- **Draft layer** = AI/system-generated output
- **Review layer** = human-reviewed, editable, authoritative output

The review layer is the source of truth for approval and export.

---

## 5. Status Lifecycle

### Supported Core Statuses
- `uploaded`
- `initialized`
- `submitted_to_ai`
- `ai_response_received`
- `ready_for_review`
- `under_review`
- `approved`
- `exported`

### Supported Exception Statuses
- `validation_failed`
- `ai_error`
- `needs_rework`
- `rejected`

### Recommendation
Implement status values as application-controlled strings in phase 1. If the product hardens later, this can be migrated to a PostgreSQL enum or lookup table.

---

## 6. Table Specifications

---

## 6.1 `listing_jobs`

### Purpose
Primary parent record representing one end-to-end listing workflow for one used item.

### DDL-Oriented Definition
| Column | Data Type | Nullable | Default | Constraints / Notes |
|---|---|---:|---|---|
| `job_id` | `UUID` | No | none | Primary key |
| `job_number` | `TEXT` | No | none | Unique, human-friendly identifier |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Audit timestamp |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` | Audit timestamp |
| `created_by` | `TEXT` | Yes | none | Username/email/actor identifier |
| `reviewed_by` | `TEXT` | Yes | none | Last reviewer identifier |
| `approved_by` | `TEXT` | Yes | none | Approver identifier |
| `status` | `TEXT` | No | none | Indexed; workflow state |
| `item_category` | `TEXT` | Yes | none | Example: camera body, lens, accessory |
| `is_reviews_enriched` | `BOOLEAN` | No | `false` | Reserved for future enrichment |
| `is_price_enriched` | `BOOLEAN` | No | `false` | Reserved for future enrichment |
| `approved_at` | `TIMESTAMPTZ` | Yes | none | Approval timestamp |
| `exported_at` | `TIMESTAMPTZ` | Yes | none | Final export timestamp |
| `notes` | `TEXT` | Yes | none | Internal workflow notes |

### Primary Key
- `PRIMARY KEY (job_id)`

### Unique Constraints
- `UNIQUE (job_number)`

### Recommended Indexes
- `INDEX idx_listing_jobs_status (status)`
- `INDEX idx_listing_jobs_created_at (created_at)`
- `INDEX idx_listing_jobs_item_category (item_category)`

### Notes
- One row = one item listing workflow
- `updated_at` should be refreshed on any write to this record
- `job_number` should be generated in the application, not manually entered

---

## 6.2 `listing_job_images`

### Purpose
Stores image metadata for files associated with a listing job.

### DDL-Oriented Definition
| Column | Data Type | Nullable | Default | Constraints / Notes |
|---|---|---:|---|---|
| `image_id` | `UUID` | No | none | Primary key |
| `job_id` | `UUID` | No | none | FK to `listing_jobs.job_id` |
| `file_name` | `TEXT` | No | none | Original or stored file name |
| `file_path` | `TEXT` | No | none | Object storage key or path |
| `file_type` | `TEXT` | No | none | Example: `image/jpeg` |
| `file_size_bytes` | `BIGINT` | Yes | none | File size metadata |
| `image_order` | `INTEGER` | No | none | Controls prompt/UI order |
| `is_primary` | `BOOLEAN` | No | `false` | Lead image indicator |
| `uploaded_at` | `TIMESTAMPTZ` | No | `now()` | Upload audit timestamp |
| `uploaded_by` | `TEXT` | Yes | none | Actor identifier |
| `checksum` | `TEXT` | Yes | none | Optional integrity field |

### Primary Key
- `PRIMARY KEY (image_id)`

### Foreign Keys
- `FOREIGN KEY (job_id) REFERENCES listing_jobs(job_id) ON DELETE CASCADE`

### Recommended Constraints
- `UNIQUE (job_id, image_order)`
- Optional future constraint: unique primary image per job via partial index

### Recommended Indexes
- `INDEX idx_listing_job_images_job_id (job_id)`
- `INDEX idx_listing_job_images_uploaded_at (uploaded_at)`

### Notes
- The actual binary file should not be stored in PostgreSQL in phase 1
- `image_order` is important because prompt ordering can affect AI output

---

## 6.3 `listing_job_status_history`

### Purpose
Tracks each status transition for auditability.

### DDL-Oriented Definition
| Column | Data Type | Nullable | Default | Constraints / Notes |
|---|---|---:|---|---|
| `status_history_id` | `UUID` | No | none | Primary key |
| `job_id` | `UUID` | No | none | FK to `listing_jobs.job_id` |
| `old_status` | `TEXT` | Yes | none | Previous state |
| `new_status` | `TEXT` | No | none | New state |
| `changed_at` | `TIMESTAMPTZ` | No | `now()` | Audit timestamp |
| `changed_by` | `TEXT` | Yes | none | Actor identifier |
| `change_reason` | `TEXT` | Yes | none | Optional explanation |

### Primary Key
- `PRIMARY KEY (status_history_id)`

### Foreign Keys
- `FOREIGN KEY (job_id) REFERENCES listing_jobs(job_id) ON DELETE CASCADE`

### Recommended Indexes
- `INDEX idx_listing_job_status_history_job_id (job_id)`
- `INDEX idx_listing_job_status_history_changed_at (changed_at)`

### Notes
- Always insert a new row when status changes; do not update prior history rows

---

## 6.4 `listing_draft_overview`

### Purpose
Stores AI/system-generated identification and high-level product details.

### DDL-Oriented Definition
| Column | Data Type | Nullable | Default | Constraints / Notes |
|---|---|---:|---|---|
| `draft_overview_id` | `UUID` | No | none | Primary key |
| `job_id` | `UUID` | No | none | Unique FK to `listing_jobs.job_id` |
| `product_name` | `TEXT` | Yes | none | AI-drafted name |
| `brand` | `TEXT` | Yes | none | Example: Canon, Nikon, Sony |
| `model` | `TEXT` | Yes | none | Model identifier |
| `product_family` | `TEXT` | Yes | none | Example: EOS, Alpha, Lumix |
| `variant` | `TEXT` | Yes | none | Variant/submodel text |
| `mount_type` | `TEXT` | Yes | none | Lens/body mount where applicable |
| `serial_number_visible` | `TEXT` | Yes | none | Visible serial only; do not infer |
| `condition_summary` | `TEXT` | Yes | none | AI-generated condition summary |
| `confidence_notes` | `TEXT` | Yes | none | Human-readable uncertainty text |
| `extraction_warnings` | `JSONB` | Yes | none | Top-level Gemini warnings array (from `gemini_response_schema.json`) |
| `raw_source_payload` | `JSONB` | Yes | none | Full raw Gemini response for traceability |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Audit timestamp |

### Primary Key
- `PRIMARY KEY (draft_overview_id)`

### Foreign Keys
- `FOREIGN KEY (job_id) REFERENCES listing_jobs(job_id) ON DELETE CASCADE`

### Unique Constraints
- `UNIQUE (job_id)`

### Recommended Indexes
- `INDEX idx_listing_draft_overview_job_id (job_id)`
- Optional search indexes later on `brand`, `model`

### Notes
- Keep this table narrow and interpretable
- `extraction_warnings` stores the top-level `extraction_warnings` array from the Gemini response; it belongs here because this is the first draft record written per job and serves as the anchor for job-level Gemini metadata
- `raw_source_payload` stores the full raw Gemini JSON response for traceability/debugging, not as the primary operational field source

---

## 6.5 `listing_draft_description`

### Purpose
Stores AI-generated listing copy and descriptive language.

### DDL-Oriented Definition
| Column | Data Type | Nullable | Default | Constraints / Notes |
|---|---|---:|---|---|
| `draft_description_id` | `UUID` | No | none | Primary key |
| `job_id` | `UUID` | No | none | Unique FK |
| `short_title` | `TEXT` | Yes | none | Draft listing title |
| `description_text` | `TEXT` | Yes | none | Draft English-language description |
| `visible_wear_notes` | `TEXT` | Yes | none | Draft condition/wear notes |
| `key_selling_points` | `TEXT` | Yes | none | Key strengths/value points |
| `confidence_notes` | `TEXT` | Yes | none | Uncertainty guidance |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Audit timestamp |

### Primary Key
- `PRIMARY KEY (draft_description_id)`

### Foreign Keys
- `FOREIGN KEY (job_id) REFERENCES listing_jobs(job_id) ON DELETE CASCADE`

### Unique Constraints
- `UNIQUE (job_id)`

### Recommended Indexes
- `INDEX idx_listing_draft_description_job_id (job_id)`

---

## 6.6 `listing_draft_specifications`

### Purpose
Stores AI/system-generated structured specifications.

### DDL-Oriented Definition
| Column | Data Type | Nullable | Default | Constraints / Notes |
|---|---|---:|---|---|
| `draft_specifications_id` | `UUID` | No | none | Primary key |
| `job_id` | `UUID` | No | none | Unique FK |
| `sensor_format` | `TEXT` | Yes | none | Camera body spec |
| `megapixels` | `NUMERIC(6,2)` | Yes | none | Numeric when known |
| `lens_mount` | `TEXT` | Yes | none | Camera/lens mount |
| `focal_length` | `TEXT` | Yes | none | Preserve flexible text for ranges |
| `aperture` | `TEXT` | Yes | none | Preserve flexible text |
| `iso_range` | `TEXT` | Yes | none | Flexible text |
| `shutter_range` | `TEXT` | Yes | none | Flexible text |
| `video_capabilities` | `TEXT` | Yes | none | Flexible text |
| `storage_media` | `TEXT` | Yes | none | Example: SD, CFexpress |
| `connectivity` | `TEXT` | Yes | none | Example: Wi-Fi, Bluetooth |
| `weight_grams` | `INTEGER` | Yes | none | Preferred normalized weight field |
| `other_specifications` | `JSONB` | Yes | none | Flexible spec storage |
| `confidence_notes` | `TEXT` | Yes | none | Uncertainty guidance |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Audit timestamp |

### Primary Key
- `PRIMARY KEY (draft_specifications_id)`

### Foreign Keys
- `FOREIGN KEY (job_id) REFERENCES listing_jobs(job_id) ON DELETE CASCADE`

### Unique Constraints
- `UNIQUE (job_id)`

### Recommended Indexes
- `INDEX idx_listing_draft_specifications_job_id (job_id)`

### Notes
- `TEXT` is preferable to over-normalizing fields like focal length or aperture in phase 1
- `weight_grams` is normalized because it is commonly comparable and machine-friendly
- `other_specifications` should hold product-type-specific details not worth modeling yet

---

## 6.7 `listing_draft_accessories`

### Purpose
Stores AI-detected accessories and packaging-related observations.

### DDL-Oriented Definition
| Column | Data Type | Nullable | Default | Constraints / Notes |
|---|---|---:|---|---|
| `draft_accessories_id` | `UUID` | No | none | Primary key |
| `job_id` | `UUID` | No | none | Unique FK |
| `included_accessories_text` | `TEXT` | Yes | none | Accessories visibly included |
| `inferred_accessories_text` | `TEXT` | Yes | none | Likely included/inferred accessories |
| `missing_typical_accessories_text` | `TEXT` | Yes | none | Possibly absent standard accessories |
| `confidence_notes` | `TEXT` | Yes | none | Uncertainty guidance |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Audit timestamp |

### Primary Key
- `PRIMARY KEY (draft_accessories_id)`

### Foreign Keys
- `FOREIGN KEY (job_id) REFERENCES listing_jobs(job_id) ON DELETE CASCADE`

### Unique Constraints
- `UNIQUE (job_id)`

### Recommended Indexes
- `INDEX idx_listing_draft_accessories_job_id (job_id)`

---

## 6.8 `listing_review_overview`

### Purpose
Stores the reviewed/final overview values that become authoritative for export.

### DDL-Oriented Definition
| Column | Data Type | Nullable | Default | Constraints / Notes |
|---|---|---:|---|---|
| `review_overview_id` | `UUID` | No | none | Primary key |
| `job_id` | `UUID` | No | none | Unique FK |
| `product_name` | `TEXT` | No | none | Required for approved listing |
| `brand` | `TEXT` | Yes | none | Editable |
| `model` | `TEXT` | Yes | none | Editable |
| `product_family` | `TEXT` | Yes | none | Editable |
| `variant` | `TEXT` | Yes | none | Editable |
| `mount_type` | `TEXT` | Yes | none | Editable |
| `serial_number_visible` | `TEXT` | Yes | none | Editable if business permits |
| `condition_summary` | `TEXT` | No | none | Required reviewed summary |
| `review_notes` | `TEXT` | Yes | none | Reviewer comments |
| `last_edited_at` | `TIMESTAMPTZ` | No | `now()` | Audit timestamp |
| `last_edited_by` | `TEXT` | Yes | none | Actor identifier |

### Primary Key
- `PRIMARY KEY (review_overview_id)`

### Foreign Keys
- `FOREIGN KEY (job_id) REFERENCES listing_jobs(job_id) ON DELETE CASCADE`

### Unique Constraints
- `UNIQUE (job_id)`

### Recommended Indexes
- `INDEX idx_listing_review_overview_job_id (job_id)`
- Optional later: `INDEX idx_listing_review_overview_brand_model (brand, model)`

### Notes
- `product_name` and `condition_summary` are marked non-null because they are likely core export fields

---

## 6.9 `listing_review_description`

### Purpose
Stores the reviewed/final descriptive copy.

### DDL-Oriented Definition
| Column | Data Type | Nullable | Default | Constraints / Notes |
|---|---|---:|---|---|
| `review_description_id` | `UUID` | No | none | Primary key |
| `job_id` | `UUID` | No | none | Unique FK |
| `short_title` | `TEXT` | No | none | Required reviewed title |
| `description_text` | `TEXT` | No | none | Required reviewed description |
| `visible_wear_notes` | `TEXT` | Yes | none | Editable condition notes |
| `key_selling_points` | `TEXT` | Yes | none | Editable highlights |
| `review_notes` | `TEXT` | Yes | none | Reviewer comments |
| `last_edited_at` | `TIMESTAMPTZ` | No | `now()` | Audit timestamp |
| `last_edited_by` | `TEXT` | Yes | none | Actor identifier |

### Primary Key
- `PRIMARY KEY (review_description_id)`

### Foreign Keys
- `FOREIGN KEY (job_id) REFERENCES listing_jobs(job_id) ON DELETE CASCADE`

### Unique Constraints
- `UNIQUE (job_id)`

### Recommended Indexes
- `INDEX idx_listing_review_description_job_id (job_id)`

---

## 6.10 `listing_review_specifications`

### Purpose
Stores reviewed/final specifications.

### DDL-Oriented Definition
| Column | Data Type | Nullable | Default | Constraints / Notes |
|---|---|---:|---|---|
| `review_specifications_id` | `UUID` | No | none | Primary key |
| `job_id` | `UUID` | No | none | Unique FK |
| `sensor_format` | `TEXT` | Yes | none | Editable |
| `megapixels` | `NUMERIC(6,2)` | Yes | none | Editable numeric spec |
| `lens_mount` | `TEXT` | Yes | none | Editable |
| `focal_length` | `TEXT` | Yes | none | Editable |
| `aperture` | `TEXT` | Yes | none | Editable |
| `iso_range` | `TEXT` | Yes | none | Editable |
| `shutter_range` | `TEXT` | Yes | none | Editable |
| `video_capabilities` | `TEXT` | Yes | none | Editable |
| `storage_media` | `TEXT` | Yes | none | Editable |
| `connectivity` | `TEXT` | Yes | none | Editable |
| `weight_grams` | `INTEGER` | Yes | none | Editable |
| `other_specifications` | `JSONB` | Yes | none | Flexible reviewed specs |
| `review_notes` | `TEXT` | Yes | none | Reviewer comments |
| `last_edited_at` | `TIMESTAMPTZ` | No | `now()` | Audit timestamp |
| `last_edited_by` | `TEXT` | Yes | none | Actor identifier |

### Primary Key
- `PRIMARY KEY (review_specifications_id)`

### Foreign Keys
- `FOREIGN KEY (job_id) REFERENCES listing_jobs(job_id) ON DELETE CASCADE`

### Unique Constraints
- `UNIQUE (job_id)`

### Recommended Indexes
- `INDEX idx_listing_review_specifications_job_id (job_id)`

### Notes
- Phase 1 should keep this lightweight rather than creating many separate subtype tables
- Business validation can require at least one meaningful specification rather than forcing every field non-null

---

## 6.11 `listing_review_accessories`

### Purpose
Stores reviewed/final accessories information.

### DDL-Oriented Definition
| Column | Data Type | Nullable | Default | Constraints / Notes |
|---|---|---:|---|---|
| `review_accessories_id` | `UUID` | No | none | Primary key |
| `job_id` | `UUID` | No | none | Unique FK |
| `included_accessories_text` | `TEXT` | No | none | Required reviewed accessories summary |
| `inferred_accessories_text` | `TEXT` | Yes | none | Optional reviewer-retained notes |
| `missing_typical_accessories_text` | `TEXT` | Yes | none | Optional reviewer notes |
| `review_notes` | `TEXT` | Yes | none | Reviewer comments |
| `last_edited_at` | `TIMESTAMPTZ` | No | `now()` | Audit timestamp |
| `last_edited_by` | `TEXT` | Yes | none | Actor identifier |

### Primary Key
- `PRIMARY KEY (review_accessories_id)`

### Foreign Keys
- `FOREIGN KEY (job_id) REFERENCES listing_jobs(job_id) ON DELETE CASCADE`

### Unique Constraints
- `UNIQUE (job_id)`

### Recommended Indexes
- `INDEX idx_listing_review_accessories_job_id (job_id)`

### Notes
- `included_accessories_text` is non-null because accessories are a required reviewed section in the current POC model

---

## 6.12 `listing_exports`

### Purpose
Tracks generated exports and preserves the exported payload snapshot.

### DDL-Oriented Definition
| Column | Data Type | Nullable | Default | Constraints / Notes |
|---|---|---:|---|---|
| `export_id` | `UUID` | No | none | Primary key |
| `job_id` | `UUID` | No | none | FK to `listing_jobs.job_id` |
| `export_type` | `TEXT` | No | none | Example: `csv` |
| `export_file_name` | `TEXT` | No | none | Generated export file name |
| `export_file_path` | `TEXT` | No | none | Storage path/key |
| `exported_at` | `TIMESTAMPTZ` | No | `now()` | Export timestamp |
| `exported_by` | `TEXT` | Yes | none | Actor identifier |
| `export_status` | `TEXT` | No | none | Example: success, failed |
| `export_payload_snapshot` | `JSONB` | Yes | none | Exact exported payload |

### Primary Key
- `PRIMARY KEY (export_id)`

### Foreign Keys
- `FOREIGN KEY (job_id) REFERENCES listing_jobs(job_id) ON DELETE CASCADE`

### Recommended Indexes
- `INDEX idx_listing_exports_job_id (job_id)`
- `INDEX idx_listing_exports_exported_at (exported_at)`

### Notes
- A job may have multiple exports over time, so this is intentionally one-to-many

---

## 7. Relationship Summary

### One-to-One by `UNIQUE(job_id)`
- `listing_jobs` → `listing_draft_overview`
- `listing_jobs` → `listing_draft_description`
- `listing_jobs` → `listing_draft_specifications`
- `listing_jobs` → `listing_draft_accessories`
- `listing_jobs` → `listing_review_overview`
- `listing_jobs` → `listing_review_description`
- `listing_jobs` → `listing_review_specifications`
- `listing_jobs` → `listing_review_accessories`

### One-to-Many
- `listing_jobs` → `listing_job_images`
- `listing_jobs` → `listing_job_status_history`
- `listing_jobs` → `listing_exports`

### Delete Behavior
Recommended delete behavior for phase 1:
- deleting a `listing_jobs` row cascades to all child rows

This keeps the POC simple and avoids orphan records.

---

## 8. Required Data Rules for Approval

A job should only be eligible for `approved` status when all of the following reviewed records exist:

- `listing_review_overview`
- `listing_review_description`
- `listing_review_specifications`
- `listing_review_accessories`

### Minimum Field-Level Validation Recommendation
Before approval, enforce at least:

#### `listing_review_overview`
- `product_name` is not null/blank
- `condition_summary` is not null/blank

#### `listing_review_description`
- `short_title` is not null/blank
- `description_text` is not null/blank

#### `listing_review_specifications`
- at least one meaningful specification field populated

#### `listing_review_accessories`
- `included_accessories_text` is not null/blank

---

## 9. JSON Usage Rules

### Approved JSONB Fields
Use JSONB only for:
- `listing_draft_overview.extraction_warnings` — top-level Gemini warnings array
- `listing_draft_overview.raw_source_payload` — full raw Gemini response
- `listing_draft_specifications.other_specifications`
- `listing_review_specifications.other_specifications`
- `listing_exports.export_payload_snapshot`

### Rationale
This preserves:
- raw source traceability
- flexible camera/lens-specific details
- exact export snapshot history

without collapsing the full model into opaque payloads.

---

## 10. Recommended PostgreSQL DDL Conventions

### UUID Generation
Choose one of the following patterns consistently:
- application-generated UUIDs
- or PostgreSQL-generated UUIDs using `gen_random_uuid()`

### Timestamp Updates
Use either:
- application-level timestamp management
- or a database trigger to refresh `updated_at`

For phase 1, application-managed timestamps are acceptable.

### Text Search
Do not optimize for full text search yet.
If needed later, add:
- GIN/trigram indexes for product search
- generated searchable columns

---

## 11. Suggested Migration Order

Recommended initial migration order:

1. `listing_jobs`
2. `listing_job_images`
3. `listing_job_status_history`
4. `listing_draft_overview`
5. `listing_draft_description`
6. `listing_draft_specifications`
7. `listing_draft_accessories`
8. `listing_review_overview`
9. `listing_review_description`
10. `listing_review_specifications`
11. `listing_review_accessories`
12. `listing_exports`

---

## 12. Suggested Future Extensions

The schema is intentionally designed to support later additions such as:

- review enrichment summaries
- price recommendations and comparables
- source citation tracking
- user authentication/roles
- approval queues
- analytics on AI-vs-human corrections
- marketplace posting integrations
- inventory system integration

These should be added only after the core phase is validated.

---

## 13. Final Recommendation

For the core Service Photo POC, the recommended physical schema is:

- **PostgreSQL**
- **job-centered**
- **draft vs reviewed layer separation**
- **relational structure for required sections**
- **JSONB used selectively for flexibility and traceability**
- **optional enrichment deferred until the first working slice is proven**

This structure gives the project the right balance of:
- clarity
- buildability
- auditability
- flexibility

without over-engineering the proof of concept.

---

## 14. Immediate Next Artifact After This Document

After approval of this physical schema spec, the next recommended deliverables are:

1. **Initial PostgreSQL migration script**
2. **Seed/test data for one or more listing jobs**
3. **Gemini response JSON schema**
4. **Review form field contract**
5. **CSV export field mapping spec**

