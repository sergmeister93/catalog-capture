# Service Photo POC — Database Schema Architecture Documentation

## 1. Purpose

This document defines the recommended database architecture for the **Service Photo POC**, a human-in-the-loop workflow that converts uploaded camera equipment photos into editable listing drafts, optionally enriches those drafts with web-based reviews and pricing, and exports approved records for downstream use.

This design assumes:
- **All fields are user-editable during review**
- **Required sections** are: Overview, Description, Specifications, Accessories
- **Optional sections** are: Reviews, Price Details
- The system is a **POC**, so the design should favor clarity, traceability, and easy iteration over premature optimization

---

## 2. Database Design Goals

The schema should support the following core needs:

1. **Track one listing job per item**
2. **Store uploaded images and job status history**
3. **Persist AI-extracted draft content separately from reviewed/final content**
4. **Allow full user override of every field**
5. **Support optional web enrichment for reviews and pricing**
6. **Preserve traceability and auditability across the workflow**
7. **Support CSV or downstream export after approval**

---

## 3. High-Level Data Model

The recommended schema uses a **job-centered architecture**.

At the center is a `listing_jobs` table, with related child tables for:
- uploaded images
- AI extraction results
- user-reviewed content
- reviews enrichment
- price enrichment
- exports
- job status history

### Core Entity Flow

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
  ├── listing_review_reviews
  ├── listing_review_price_details
  ├── listing_price_comparables
  ├── listing_review_sources
  └── listing_exports
```

---

## 4. Recommended Design Pattern

Use a **two-layer content model**:

### Layer 1: Draft / System-Generated Content
Stores what the system inferred or generated from:
- uploaded images
- Gemini extraction
- optional web enrichment

### Layer 2: Reviewed / User-Finalized Content
Stores what the user explicitly reviewed, edited, and approved.

This separation is important because:
- it preserves the original AI output for debugging and prompt tuning
- it allows comparison between AI and human-corrected values
- it makes auditability much cleaner
- it prevents reviewed content from overwriting raw/generated content

---

## 5. Main Tables

## 5.1 `listing_jobs`

Primary parent record for one item listing workflow.

### Purpose
Represents one end-to-end job for one used item.

### Suggested Fields
- `job_id` (PK, UUID)
- `job_number` (human-friendly identifier, unique)
- `created_at`
- `updated_at`
- `created_by`
- `reviewed_by`
- `approved_by`
- `status`
- `item_category`
- `is_reviews_enriched` (boolean)
- `is_price_enriched` (boolean)
- `approved_at`
- `exported_at`
- `notes`

### Notes
- One job = one item
- `status` should align to the workflow lifecycle
- `item_category` is useful for filtering and later analytics

---

## 5.2 `listing_job_images`

Stores metadata for all uploaded images associated with a job.

### Purpose
Tracks image files used as source material.

### Suggested Fields
- `image_id` (PK, UUID)
- `job_id` (FK → `listing_jobs.job_id`)
- `file_name`
- `file_path`
- `file_type`
- `file_size_bytes`
- `image_order`
- `is_primary`
- `uploaded_at`
- `uploaded_by`
- `checksum`

### Notes
- Keep image metadata in the database and image binaries in file/object storage
- `image_order` supports deterministic prompt construction and UI display
- `is_primary` can be useful for the lead listing image

---

## 5.3 `listing_job_status_history`

Tracks status transitions over time.

### Purpose
Provides workflow auditability.

### Suggested Fields
- `status_history_id` (PK, UUID)
- `job_id` (FK)
- `old_status`
- `new_status`
- `changed_at`
- `changed_by`
- `change_reason`

### Notes
Recommended statuses:
- Uploaded
- Initialized
- Submitted to AI
- AI Response Received
- Ready for Review
- Under Review
- Approved
- Exported
- Validation Failed
- AI Error
- Needs Rework
- Rejected

---

## 6. Draft Content Tables

These store system-generated content before user review.

## 6.1 `listing_draft_overview`

### Purpose
Stores the extracted identification and overview block.

### Suggested Fields
- `draft_overview_id` (PK, UUID)
- `job_id` (FK, unique)
- `product_name`
- `brand`
- `model`
- `product_family`
- `variant`
- `mount_type`
- `serial_number_visible`
- `condition_summary`
- `confidence_notes`
- `raw_source_payload` (JSON or text)
- `created_at`

### Notes
This table should contain the system's best first-pass structured identification output.

---

## 6.2 `listing_draft_description`

### Purpose
Stores generated English-language listing copy.

### Suggested Fields
- `draft_description_id` (PK, UUID)
- `job_id` (FK, unique)
- `short_title`
- `description_text`
- `visible_wear_notes`
- `key_selling_points`
- `confidence_notes`
- `created_at`

---

## 6.3 `listing_draft_specifications`

### Purpose
Stores structured extracted specifications.

### Suggested Fields
- `draft_specifications_id` (PK, UUID)
- `job_id` (FK, unique)
- `sensor_format`
- `megapixels`
- `lens_mount`
- `focal_length`
- `aperture`
- `iso_range`
- `shutter_range`
- `video_capabilities`
- `storage_media`
- `connectivity`
- `weight`
- `other_specifications` (JSON or text)
- `confidence_notes`
- `created_at`

### Notes
A JSON field for `other_specifications` is useful because camera/lens specs vary widely by product type.

---

## 6.4 `listing_draft_accessories`

### Purpose
Stores system-detected or inferred accessories from the uploaded photos.

### Suggested Fields
- `draft_accessories_id` (PK, UUID)
- `job_id` (FK, unique)
- `included_accessories_text`
- `inferred_accessories_text`
- `missing_typical_accessories_text`
- `confidence_notes`
- `created_at`

### Notes
For a POC, storing these as text or JSON arrays is acceptable.

---

## 7. Reviewed / Final Content Tables

These store the user-edited values that become the source of truth for export.

## 7.1 `listing_review_overview`

### Purpose
Stores final user-reviewed overview content.

### Suggested Fields
- `review_overview_id` (PK, UUID)
- `job_id` (FK, unique)
- `product_name`
- `brand`
- `model`
- `product_family`
- `variant`
- `mount_type`
- `serial_number_visible`
- `condition_summary`
- `review_notes`
- `last_edited_at`
- `last_edited_by`

---

## 7.2 `listing_review_description`

### Purpose
Stores final user-reviewed description content.

### Suggested Fields
- `review_description_id` (PK, UUID)
- `job_id` (FK, unique)
- `short_title`
- `description_text`
- `visible_wear_notes`
- `key_selling_points`
- `review_notes`
- `last_edited_at`
- `last_edited_by`

---

## 7.3 `listing_review_specifications`

### Purpose
Stores final user-reviewed specifications.

### Suggested Fields
- `review_specifications_id` (PK, UUID)
- `job_id` (FK, unique)
- `sensor_format`
- `megapixels`
- `lens_mount`
- `focal_length`
- `aperture`
- `iso_range`
- `shutter_range`
- `video_capabilities`
- `storage_media`
- `connectivity`
- `weight`
- `other_specifications` (JSON or text)
- `review_notes`
- `last_edited_at`
- `last_edited_by`

---

## 7.4 `listing_review_accessories`

### Purpose
Stores final user-reviewed accessories content.

### Suggested Fields
- `review_accessories_id` (PK, UUID)
- `job_id` (FK, unique)
- `included_accessories_text`
- `inferred_accessories_text`
- `missing_typical_accessories_text`
- `review_notes`
- `last_edited_at`
- `last_edited_by`

---

## 8. Optional Enrichment Tables

These support optional web-based enrichment for reviews and pricing.

## 8.1 `listing_review_reviews`

### Purpose
Stores editable review summary content for a job.

### Suggested Fields
- `review_reviews_id` (PK, UUID)
- `job_id` (FK, unique)
- `review_summary`
- `pros_text`
- `cons_text`
- `review_notes`
- `last_edited_at`
- `last_edited_by`

### Notes
This section is optional and should not block approval or export unless business rules change.

---

## 8.2 `listing_review_sources`

### Purpose
Stores the supporting web sources used for review or price enrichment.

### Suggested Fields
- `source_id` (PK, UUID)
- `job_id` (FK)
- `source_type` (`review`, `price`, or `mixed`)
- `source_name`
- `source_url`
- `source_title`
- `captured_at`
- `source_summary`

### Notes
This gives traceability to what the enrichment was based on.

---

## 8.3 `listing_review_price_details`

### Purpose
Stores editable price recommendation information.

### Suggested Fields
- `review_price_details_id` (PK, UUID)
- `job_id` (FK, unique)
- `recommended_list_price`
- `recommended_quick_sale_price`
- `pricing_notes`
- `price_summary`
- `last_edited_at`
- `last_edited_by`

### Notes
This is the editable roll-up table for final price guidance.

---

## 8.4 `listing_price_comparables`

### Purpose
Stores multiple source comparables behind the final price recommendation.

### Suggested Fields
- `comparable_id` (PK, UUID)
- `job_id` (FK)
- `source_name`
- `listing_title`
- `condition_text`
- `price_amount`
- `currency_code`
- `listing_status` (`sold`, `listed`, `unknown`)
- `listing_url`
- `captured_at`
- `notes`

### Notes
This should support 2–3 comparables minimum, but it is intentionally one-to-many.

---

## 9. Export Tables

## 9.1 `listing_exports`

### Purpose
Tracks generated exports for approved jobs.

### Suggested Fields
- `export_id` (PK, UUID)
- `job_id` (FK)
- `export_type` (`csv`, future extensible)
- `export_file_name`
- `export_file_path`
- `exported_at`
- `exported_by`
- `export_status`
- `export_payload_snapshot` (JSON or text)

### Notes
The export snapshot is valuable because it preserves exactly what was sent downstream at time of export.

---

## 10. Recommended Relationships

### One-to-One
- `listing_jobs` → `listing_draft_overview`
- `listing_jobs` → `listing_draft_description`
- `listing_jobs` → `listing_draft_specifications`
- `listing_jobs` → `listing_draft_accessories`
- `listing_jobs` → `listing_review_overview`
- `listing_jobs` → `listing_review_description`
- `listing_jobs` → `listing_review_specifications`
- `listing_jobs` → `listing_review_accessories`
- `listing_jobs` → `listing_review_reviews` (optional)
- `listing_jobs` → `listing_review_price_details` (optional)

### One-to-Many
- `listing_jobs` → `listing_job_images`
- `listing_jobs` → `listing_job_status_history`
- `listing_jobs` → `listing_review_sources`
- `listing_jobs` → `listing_price_comparables`
- `listing_jobs` → `listing_exports`

---

## 11. Required vs Optional Data Rules

## Required for Approval / Export
The following reviewed sections should exist before a job can be approved:
- `listing_review_overview`
- `listing_review_description`
- `listing_review_specifications`
- `listing_review_accessories`

## Optional for Approval / Export
The following may be null / absent:
- `listing_review_reviews`
- `listing_review_price_details`
- `listing_price_comparables`
- `listing_review_sources`

### Recommended Validation Rule
Approval should check for the presence of the required reviewed records and required field-level content inside them.

---

## 12. Why Separate Draft and Review Tables

This design is preferable to storing everything in one row because it gives you:

### Auditability
You can compare:
- what Gemini extracted
- what enrichment returned
- what the reviewer finalized

### Safer Editing
The user-edited layer becomes the authoritative export layer without destroying the generated source material.

### Better Prompt Tuning
You can later measure where AI output was consistently corrected.

### Easier Future Analytics
This opens the door for metrics like:
- most commonly corrected fields
- extraction confidence by category
- average review time
- approval rate by product type

---

## 13. Alternative Simplified POC Option

If you want to move faster, there is a simpler version:

### Simplified Model
- `listing_jobs`
- `listing_job_images`
- `listing_job_status_history`
- `listing_draft_payloads` (JSON)
- `listing_review_payloads` (JSON)
- `listing_review_sources`
- `listing_price_comparables`
- `listing_exports`

In that version:
- Overview, Description, Specifications, Accessories, Reviews, and Price Details all live inside JSON payloads
- relational child tables are only used where one-to-many behavior is clearly needed

### Tradeoff
- **Pros**: faster to build, more flexible, easier for a proof of concept
- **Cons**: weaker field-level validation, harder SQL reporting, less schema discipline

### Recommendation
For phase one, I recommend a **hybrid approach**:
- use structured relational tables for core reviewed sections
- allow JSON support for flexible spec fields and source payloads

---

## 14. Suggested Workflow Against the Schema

### Step 1: Job Creation
Create a `listing_jobs` row and initial `listing_job_images` rows.

### Step 2: AI Extraction
Write system output into:
- `listing_draft_overview`
- `listing_draft_description`
- `listing_draft_specifications`
- `listing_draft_accessories`

### Step 3: Optional Web Enrichment
Write enrichment into:
- `listing_review_reviews` or a draft equivalent if desired
- `listing_review_price_details` or a draft equivalent if desired
- `listing_review_sources`
- `listing_price_comparables`

### Step 4: Human Review
User edits and saves authoritative content into:
- `listing_review_overview`
- `listing_review_description`
- `listing_review_specifications`
- `listing_review_accessories`
- optionally `listing_review_reviews`
- optionally `listing_review_price_details`

### Step 5: Approval
Status changes to `Approved` once required reviewed data exists.

### Step 6: Export
Create `listing_exports` row and preserve the export snapshot.

---

## 15. Recommended Technical Constraints

### Keys
- Use UUID primary keys for all major entities
- Enforce unique `job_id` on one-to-one child tables

### Timestamps
Every table should include timestamp metadata appropriate to its function:
- `created_at`
- `updated_at`
- `last_edited_at`
- `captured_at`

### JSON Usage
Use JSON selectively for:
- raw AI payloads
- flexible specifications
- export snapshots
- source summaries if needed

### Soft Deletes
Consider soft delete columns only if the business expects record recovery needs.
For a POC, these may be unnecessary.

---

## 16. Future-State Extensions

This schema can later support:
- marketplace posting integrations
- pricing engine history
- confidence scoring by field
- multiple review passes
- approval queues
- user authentication and role tracking
- inventory system integration
- model-level performance analytics

---

## 17. Final Recommendation

For the **Service Photo POC**, the best database architecture is a **job-centered relational schema with separate draft and reviewed layers**, plus optional one-to-many enrichment tables for pricing sources and source references.

### Recommended Core Tables
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
- `listing_review_reviews`
- `listing_review_price_details`
- `listing_review_sources`
- `listing_price_comparables`
- `listing_exports`

This approach gives you enough structure to build phase one cleanly while preserving the flexibility needed for camera-specific variation and optional web enrichment.

---

## 18. Recommended Immediate Next Deliverable

After this document, the next artifact should be a **physical schema specification** that defines:
- exact SQL table names
- column names
- data types
- PK/FK constraints
- nullable rules
- indexes

That document can then be used directly in Claude Code to generate:
- migration scripts
- ORM models
- seed/test data
- backend validation models
