# Service Photo POC — Approval Validation Rules

## Purpose

This document defines the exact validation gate that must pass before a listing job
can be approved (status transition to `approved`). These rules are enforced by the
`POST /jobs/{job_id}/approve` endpoint and are the authoritative specification for
the backend approval logic.

All validation runs against the **reviewed content layer only**. Draft layer content
is never used for approval checks.

---

## Pre-Condition: Eligible Job Status

A job is only eligible for approval if its current status is `under_review`.

Any attempt to approve a job in any other status must return HTTP 409 with error code
`invalid_status_for_approval`.

---

## Required Reviewed Sections

All four reviewed sections must exist as rows in the database before approval is
permitted. A missing row (null from a LEFT JOIN) fails the gate.

| Table | Missing Row Error Code |
|---|---|
| `listing_review_overview` | `missing_review_overview` |
| `listing_review_description` | `missing_review_description` |
| `listing_review_specifications` | `missing_review_specifications` |
| `listing_review_accessories` | `missing_review_accessories` |

---

## Field-Level Validation Rules

### Section: listing_review_overview

| Rule ID | Field | Condition | Error Code |
|---|---|---|---|
| OVR-01 | `product_name` | Must not be null | `review_overview.product_name_null` |
| OVR-02 | `product_name` | Must not be blank (empty or whitespace only) | `review_overview.product_name_blank` |
| OVR-03 | `condition_summary` | Must not be null | `review_overview.condition_summary_null` |
| OVR-04 | `condition_summary` | Must not be blank | `review_overview.condition_summary_blank` |

### Section: listing_review_description

| Rule ID | Field | Condition | Error Code |
|---|---|---|---|
| DSC-01 | `short_title` | Must not be null | `review_description.short_title_null` |
| DSC-02 | `short_title` | Must not be blank | `review_description.short_title_blank` |
| DSC-03 | `description_text` | Must not be null | `review_description.description_text_null` |
| DSC-04 | `description_text` | Must not be blank | `review_description.description_text_blank` |

### Section: listing_review_specifications

At least one of the following fields must be non-null and non-blank for the record
to be considered meaningfully populated.

Qualifying fields (any one is sufficient):

| Field | Type |
|---|---|
| `sensor_format` | TEXT |
| `megapixels` | NUMERIC — must not be null |
| `lens_mount` | TEXT |
| `focal_length` | TEXT |
| `aperture` | TEXT |
| `iso_range` | TEXT |
| `shutter_range` | TEXT |
| `video_capabilities` | TEXT |
| `storage_media` | TEXT |
| `connectivity` | TEXT |
| `weight_grams` | INTEGER — must not be null |

For TEXT fields: the field must be non-null and not empty/whitespace-only to count.
For NUMERIC/INTEGER fields: the field must be non-null to count.

Entries in `other_specifications` (JSONB) do **not** count as a qualifying field for
the approval gate. The gate requires at least one of the explicitly named columns
above.

| Rule ID | Condition | Error Code |
|---|---|---|
| SPC-01 | At least one qualifying spec field is populated | `review_specifications.no_meaningful_spec` |

### Section: listing_review_accessories

| Rule ID | Field | Condition | Error Code |
|---|---|---|---|
| ACC-01 | `included_accessories_text` | Must not be null | `review_accessories.included_accessories_text_null` |
| ACC-02 | `included_accessories_text` | Must not be blank | `review_accessories.included_accessories_text_blank` |

---

## Validation Response

If any rule fails, the endpoint returns HTTP 400 with the following structure:

```json
{
  "error": "approval_validation_failed",
  "message": "Job cannot be approved; required content is missing or invalid",
  "validation_failures": [
    {
      "rule": "review_overview.product_name_blank",
      "detail": "product_name is blank in listing_review_overview"
    },
    {
      "rule": "review_specifications.no_meaningful_spec",
      "detail": "No qualifying specification field is populated in listing_review_specifications"
    }
  ]
}
```

All failing rules must be returned in a single response. Do not short-circuit on
the first failure.

---

## On Successful Approval

When all rules pass:

1. Set `listing_jobs.status = 'approved'`
2. Set `listing_jobs.approved_at = now()`
3. Set `listing_jobs.approved_by` to the value from the request body (nullable)
4. Set `listing_jobs.updated_at = now()`
5. Insert a row into `listing_job_status_history`:
   - `old_status = 'under_review'`
   - `new_status = 'approved'`
   - `changed_at = now()`
   - `changed_by` = value from request body (nullable)
   - `change_reason = 'Approval gate passed'`

Return the updated `listing_jobs` record with HTTP 200.

---

## Optional Sections — Not Required for Approval

The following reviewed sections are intentionally out of scope for the approval gate
in Phase 1. Their absence does not block approval.

- `listing_review_reviews`
- `listing_review_price_details`
- `listing_review_sources`
- `listing_price_comparables`

---

## Note on Export

Approval does not trigger export. Export is a separate explicit action
(`POST /jobs/{job_id}/export`) that requires the job to already be in `approved` status.
Export uses the reviewed content layer only and must not read from any draft table.

---

## Note on Draft Content

Draft content from the following tables is **never** used in the approval gate:

- `listing_draft_overview`
- `listing_draft_description`
- `listing_draft_specifications`
- `listing_draft_accessories`

These tables are preserved for traceability, debugging, and prompt tuning. They are
not overwritten or modified during the approval workflow.
