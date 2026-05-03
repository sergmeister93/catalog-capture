# Service Photo POC — Backend Workflow Specification

## Purpose

This document specifies the complete backend workflow for the Service Photo POC:
the sequence of operations, status transitions, database writes, and error handling
for each stage of the listing job lifecycle.

This is the authoritative reference for backend API implementation. Read alongside:
- `physical_schema_spec.md` — PostgreSQL table and column definitions
- `openapi_service_photo_poc.yaml` — endpoint contracts and payload schemas
- `approval_validation_rules.md` — approval gate logic

---

## 1. Status Lifecycle

### Core Flow (happy path)

```
initialized
  → submitted_to_ai
  → ai_response_received
  → ready_for_review
  → under_review
  → approved
  → exported
```

### Exception States

| Status | Triggered By |
|---|---|
| `validation_failed` | Gemini response fails schema validation |
| `ai_error` | Gemini API call fails or returns an error |
| `needs_rework` | Reviewer explicitly flags the job for rework |
| `rejected` | Job is explicitly rejected and will not be processed |

### Recovery from Exception States

| From Status | Allowed Recovery |
|---|---|
| `validation_failed` | Re-submit via `POST /jobs/{job_id}/submit` |
| `ai_error` | Re-submit via `POST /jobs/{job_id}/submit` |
| `needs_rework` | Re-submit or continue editing in `under_review` context |
| `rejected` | Terminal; no automatic recovery in Phase 1 |

### Status History Rule

Every status transition must insert a row into `listing_job_status_history`.
Never skip this insert, even for intermediate machine-driven transitions.
Never update prior history rows; history is append-only.

---

## 2. Endpoint Workflow Details

---

### 2.1 POST /jobs — Create Listing Job

**Purpose:** Initialize a new listing job for one used item.

**Preconditions:** None.

**Backend Steps:**

1. Generate a UUID for `job_id`
2. Generate a human-friendly `job_number` (example format: `JOB-YYYYMMDD-NNN`)
3. Insert row into `listing_jobs`:
   - `status = 'initialized'`
   - `is_reviews_enriched = false`
   - `is_price_enriched = false`
   - `created_at = now()`
   - `updated_at = now()`
4. Insert row into `listing_job_status_history`:
   - `old_status = null`
   - `new_status = 'initialized'`
   - `change_reason = 'Job created'`

**Returns:** Full `listing_jobs` record (HTTP 201).

---

### 2.2 POST /jobs/{job_id}/images — Register Job Image

**Purpose:** Record metadata for an image file already written to storage.

**Preconditions:**
- Job must exist
- Job must not be in a terminal status (`approved`, `exported`, `rejected`)
- `image_order` must be unique for this `job_id`

**Backend Steps:**

1. Validate job exists and is not terminal
2. Validate `image_order` is not already taken for this job
3. Insert row into `listing_job_images`
4. Set `listing_jobs.updated_at = now()`

**Returns:** New `listing_job_images` record (HTTP 201).

**Error Cases:**

| Condition | HTTP | Error Code |
|---|---|---|
| Job not found | 404 | `job_not_found` |
| Job in terminal status | 409 | `job_not_editable` |
| image_order conflict | 409 | `image_order_conflict` |

---

### 2.3 POST /jobs/{job_id}/submit — Submit Job to AI

**Purpose:** Trigger Gemini analysis for the job.

**Preconditions:**
- Job must exist
- Job must be in `initialized` status (or `validation_failed` / `ai_error` for resubmission)
- Job must have at least one registered image in `listing_job_images`

**Backend Steps:**

1. Validate preconditions
2. Set status → `submitted_to_ai`, log history
3. Set `listing_jobs.updated_at = now()`
4. Assemble images (ordered by `image_order` ascending) and prompt
5. Call Gemini API
6. **On Gemini success:**
   a. Set status → `ai_response_received`, log history
   b. Validate response structure against the Gemini response schema
   c. **On validation success:**
      - Upsert into `listing_draft_overview`
      - Upsert into `listing_draft_description`
      - Upsert into `listing_draft_specifications`
      - Upsert into `listing_draft_accessories`
      - Set status → `ready_for_review`, log history
      - Update `listing_jobs.updated_at = now()`
   d. **On validation failure:**
      - Set status → `validation_failed`, log history
      - Return error response (HTTP 200 with error detail on the job record, or HTTP 422)
7. **On Gemini error:**
   - Set status → `ai_error`, log history
   - Update `listing_jobs.updated_at = now()`
   - Return error response

**Returns:** Updated `listing_jobs` record (HTTP 200).

**Draft Table Upsert Rule:**
If a prior draft row exists for this job (resubmission case), replace it entirely.
Draft rows are one-to-one with jobs (`UNIQUE(job_id)`). Use `ON CONFLICT (job_id) DO UPDATE`.

**Error Cases:**

| Condition | HTTP | Error Code |
|---|---|---|
| Job not found | 404 | `job_not_found` |
| Invalid status | 409 | `invalid_status_for_submit` |
| No images registered | 400 | `no_images_registered` |
| Gemini API error | 200 (job) | status=`ai_error` |
| Response validation failure | 200 (job) | status=`validation_failed` |

---

### 2.4 GET /jobs/{job_id} — Get Job by ID

**Purpose:** Return the job record with images and status history.

**Backend Steps:**

1. Fetch `listing_jobs` by `job_id`
2. Fetch all `listing_job_images` WHERE `job_id = :job_id` ORDER BY `image_order ASC`
3. Fetch all `listing_job_status_history` WHERE `job_id = :job_id` ORDER BY `changed_at ASC`
4. Compose and return `ListingJobDetail`

**Returns:** `ListingJobDetail` (HTTP 200).

---

### 2.5 GET /jobs/{job_id}/review-payload — Get Review Payload

**Purpose:** Return all draft and review content for the review UI.

**Preconditions:**
- Job must exist
- Job must be in one of: `ready_for_review`, `under_review`, `approved`, `exported`

**Backend Steps:**

1. Validate job exists and status is review-eligible
2. Fetch `listing_jobs`
3. Fetch `listing_job_images` ORDER BY `image_order ASC`
4. Fetch draft layer (all four tables) — LEFT JOIN, may be null
5. Fetch review layer (all four tables) — LEFT JOIN, may be null
6. Compose and return `ReviewPayload`

**Returns:** `ReviewPayload` (HTTP 200). Any unwritten section is returned as `null`.

**Error Cases:**

| Condition | HTTP | Error Code |
|---|---|---|
| Job not found | 404 | `job_not_found` |
| Job not review-eligible | 409 | `job_not_ready_for_review` |

---

### 2.6 PUT /jobs/{job_id}/review — Save Reviewed Content

**Purpose:** Upsert one or more reviewed content sections.

**Preconditions:**
- Job must exist
- Job must be in `ready_for_review` or `under_review` status
- Request body must include at least one section

**Backend Steps:**

1. Validate preconditions
2. If status is `ready_for_review`:
   - Set status → `under_review`, log history
3. For each section present in the request body, upsert the corresponding reviewed table:
   - `listing_review_overview` — using `ON CONFLICT (job_id) DO UPDATE`
   - `listing_review_description` — using `ON CONFLICT (job_id) DO UPDATE`
   - `listing_review_specifications` — using `ON CONFLICT (job_id) DO UPDATE`
   - `listing_review_accessories` — using `ON CONFLICT (job_id) DO UPDATE`
4. Set `last_edited_at = now()` and `last_edited_by` from request body on each upserted row
5. Set `listing_jobs.reviewed_by` = value from request body (nullable)
6. Set `listing_jobs.updated_at = now()`

**Returns:** `ReviewContent` object containing the current state of all four reviewed
sections (including sections not updated in this call). HTTP 200.

**Section Independence Rule:**
Only the sections explicitly present in the request body are written. Absent sections
are not cleared. This allows the UI to save individual sections without overwriting others.

**Error Cases:**

| Condition | HTTP | Error Code |
|---|---|---|
| Job not found | 404 | `job_not_found` |
| Invalid status | 409 | `invalid_status_for_review` |
| No sections in body | 400 | `no_review_sections_provided` |

---

### 2.7 POST /jobs/{job_id}/approve — Approve Job

**Purpose:** Run approval validation and transition job to `approved`.

**Preconditions:**
- Job must exist
- Job must be in `under_review` status

**Backend Steps:**

1. Validate job exists and is in `under_review`
2. Run all approval validation rules (see `approval_validation_rules.md`):
   - Collect all failing rules; do not short-circuit
3. **If any rules fail:**
   - Return HTTP 400 with `ApprovalValidationError` listing all failures
   - Do not change job status
4. **If all rules pass:**
   - Set `listing_jobs.status = 'approved'`
   - Set `listing_jobs.approved_at = now()`
   - Set `listing_jobs.approved_by` = value from request body
   - Set `listing_jobs.updated_at = now()`
   - Insert status history: `under_review → approved`
   - Return updated `listing_jobs` record (HTTP 200)

---

### 2.8 POST /jobs/{job_id}/export — Export Job

**Purpose:** Generate a CSV export from reviewed content and record it.

**Preconditions:**
- Job must exist
- Job must be in `approved` status

**Backend Steps:**

1. Validate preconditions
2. Fetch all four reviewed tables (overview, description, specifications, accessories)
3. Map reviewed content to CSV columns per the export field mapping
4. Write CSV file to storage
5. Insert row into `listing_exports`:
   - `export_type = 'csv'`
   - `export_file_name` = generated file name
   - `export_file_path` = storage path
   - `exported_at = now()`
   - `exported_by` = value from request body
   - `export_status = 'success'`
   - `export_payload_snapshot` = JSONB snapshot of the full reviewed content at time of export
6. Set `listing_jobs.status = 'exported'`
7. Set `listing_jobs.exported_at = now()`
8. Set `listing_jobs.updated_at = now()`
9. Insert status history: `approved → exported`

**Returns:** `ListingExport` record (HTTP 201).

**Export Source Rule:**
Export must read exclusively from the four reviewed tables. Draft table content must
never appear in an export output.

**Export Snapshot Rule:**
The `export_payload_snapshot` JSONB field must capture the exact reviewed content
used to generate the export. This snapshot is for traceability only and is never
modified after the export record is created.

**Error Cases:**

| Condition | HTTP | Error Code |
|---|---|---|
| Job not found | 404 | `job_not_found` |
| Job not in approved status | 409 | `invalid_status_for_export` |
| File write failure | 500 | `export_write_failed` |

---

## 3. Two-Layer Content Model Summary

| Layer | Tables | Purpose | Writeable By |
|---|---|---|---|
| Draft | `listing_draft_overview`, `listing_draft_description`, `listing_draft_specifications`, `listing_draft_accessories` | AI-generated source material | Backend (AI step only) |
| Review | `listing_review_overview`, `listing_review_description`, `listing_review_specifications`, `listing_review_accessories` | Human-reviewed, authoritative output | Backend (review save step) |

**The review layer is the source of truth.** Approval and export never touch the draft layer.

The draft layer is preserved for:
- debugging AI output
- prompt tuning
- comparison analytics between AI and human values

---

## 4. Status Transition Table

| From Status | Action | To Status | Notes |
|---|---|---|---|
| (none) | Create job | `initialized` | First row creation |
| `initialized` | Submit to AI | `submitted_to_ai` | Immediate |
| `submitted_to_ai` | AI response received | `ai_response_received` | Machine transition |
| `ai_response_received` | Validation passes | `ready_for_review` | Machine transition |
| `ai_response_received` | Validation fails | `validation_failed` | Exception |
| `submitted_to_ai` | Gemini error | `ai_error` | Exception |
| `ready_for_review` | First review save | `under_review` | Triggered by PUT /review |
| `under_review` | Approve | `approved` | Requires validation gate pass |
| `approved` | Export | `exported` | Triggered by POST /export |
| `validation_failed` | Resubmit | `submitted_to_ai` | Retry path |
| `ai_error` | Resubmit | `submitted_to_ai` | Retry path |
| `needs_rework` | Continue editing | `under_review` | Manual recovery |
| `under_review` | Flag for rework | `needs_rework` | Reviewer action |
| `under_review` | Reject | `rejected` | Terminal in Phase 1 |

---

## 5. General Implementation Rules

### UUID Generation
Generate UUIDs in the application layer using a standard UUID v4 library.
Alternatively, use PostgreSQL `gen_random_uuid()` if the ORM supports it.

### Timestamp Management
All `created_at`, `updated_at`, `last_edited_at`, `changed_at`, `uploaded_at`,
`exported_at` values are set by the application at write time.
Use UTC for all timestamps.

### Atomicity
Multi-table writes within a single workflow step (e.g., writing all four draft tables
during AI response handling) must be wrapped in a single database transaction.
If any write fails, roll back all writes in that step.

### Job Number Format
`job_number` is application-generated. Suggested format: `JOB-YYYYMMDD-NNN` where
NNN is a zero-padded sequential number per day. Must be unique in `listing_jobs`.

### actor_id / user fields
Phase 1 has no authentication system. All `created_by`, `reviewed_by`, `approved_by`,
`uploaded_by`, `changed_by`, `exported_by` fields accept free-text strings and are
nullable. Pass through whatever value the caller provides; do not validate.

### Error Response Shape
All error responses must use the `ErrorResponse` schema:
```json
{
  "error": "machine_readable_error_code",
  "message": "Human-readable description"
}
```
Approval failures use `ApprovalValidationError` (superset of ErrorResponse).

---

## 6. Phase 1 Deferred Items

The following are explicitly out of scope for Phase 1 and should not be implemented:

- Web enrichment for reviews (`listing_review_reviews`, `listing_review_sources`)
- Pricing enrichment (`listing_review_price_details`, `listing_price_comparables`)
- User authentication or role-based access control
- Direct marketplace posting
- Automated re-submission on AI failure
- Soft deletes on any table
- Full-text search indexes
- Pagination on any list endpoint
