# Service Photo POC — Seed Data and Test Scenario Specification

## Purpose

This document defines the minimum seed/test data Claude Code should create for the backend build.

The goal is to make the schema immediately usable for:
- local API testing
- validation testing
- export testing
- frontend integration later

---

## 1. Recommended Seed Strategy

Use one of these approaches:

### Preferred
Python fixture builders / factory functions for tests

### Also Useful
Optional SQL seed script for manual local verification

Recommended split:
- automated tests use Python fixtures/factories
- local manual demo can use a small SQL seed file

---

## 2. Required Seed Scenarios

Claude Code should create at least these scenarios.

## Scenario A — Initialized Job
Purpose: verify base job creation state.

Data shape:
- one `listing_jobs` row in `initialized`
- one status history row
- zero images
- no draft rows
- no review rows
- no export rows

---

## Scenario B — Job with Images Registered
Purpose: verify image registration rules.

Data shape:
- one `listing_jobs` row in `initialized`
- three `listing_job_images` rows with `image_order` 1, 2, 3
- one image marked `is_primary = true`
- status history includes `initialized`

---

## Scenario C — AI Draft Created / Ready for Review
Purpose: verify submit flow and review payload retrieval.

Data shape:
- one job in `ready_for_review`
- 2–4 image rows
- draft rows present for all four sections
- no review rows yet
- status history includes:
  - `initialized`
  - `submitted_to_ai`
  - `ai_response_received`
  - `ready_for_review`

Draft values should look realistic for a used camera listing.

---

## Scenario D — Under Review with Partial Reviewed Data
Purpose: verify partial upsert behavior.

Data shape:
- one job in `under_review`
- draft rows exist
- review rows exist for only two sections
  - example: overview + description
- review specification/accessories rows absent
- status history includes `under_review`

This validates that partial review saves are preserved and omitted sections remain untouched.

---

## Scenario E — Approval Failure Case
Purpose: verify approval gate catches all issues.

Data shape:
- one job in `under_review`
- all four review rows exist
- but values intentionally fail validation, for example:
  - blank `product_name`
  - blank `description_text`
  - no meaningful specification field populated
  - blank `included_accessories_text`

Expected result:
- approval attempt returns all failures in one response
- job remains `under_review`

---

## Scenario F — Approved Job
Purpose: verify export precondition.

Data shape:
- one job in `approved`
- all four review rows valid and complete
- `approved_at` populated
- `approved_by` populated
- no export yet

---

## Scenario G — Exported Job
Purpose: verify export record behavior.

Data shape:
- one job in `exported`
- valid review rows
- one `listing_exports` row
- `export_payload_snapshot` populated
- `exported_at` populated on both job and export row
- status history includes `approved → exported`

---

## 3. Recommended Sample Item Types

Use realistic examples like:
- camera body
- camera lens
- small accessory bundle

Suggested set:
1. Canon EOS R6 body
2. Sony FE 24-70mm lens
3. Nikon flash/accessory bundle

This gives enough variation to exercise optional spec fields.

---

## 4. Required Test Assertions by Scenario

## Scenario A
- job exists
- status = `initialized`
- one history row only

## Scenario B
- image order unique
- primary image exists
- images sort correctly

## Scenario C
- review payload returns draft sections
- review sections are null

## Scenario D
- saving one section does not erase other sections
- omitted sections remain unchanged

## Scenario E
- approval returns HTTP 400
- all failures returned together
- status unchanged

## Scenario F
- export endpoint allowed
- approval endpoint no longer needed

## Scenario G
- export file exists
- export snapshot exists
- CSV columns are in correct order

---

## 5. Seed Data Design Rules

1. IDs should be deterministic in tests when helpful.
2. Timestamps should be realistic and ordered.
3. Draft data should differ slightly from review data so correction paths can be observed.
4. Approval-failure scenario should fail for multiple reasons at once.
5. Export scenario should include at least one JSONB spec field in `other_specifications`.

---

## 6. Recommended Deliverables Claude Code Should Produce

1. `tests/factories.py` or equivalent
2. `tests/fixtures.py` or equivalent
3. `tests/test_workflow_e2e.py`
4. `tests/test_approval_validation.py`
5. `tests/test_export_mapping.py`
6. Optional `scripts/seed_demo_data.sql`

---

## 7. Immediate Next Step After Seed Data

After seed data is in place, Claude Code should implement:

1. database models
2. mock Gemini client
3. job/image/review/export endpoints
4. end-to-end test flow
