# Service Photo POC — CSV Export Field Mapping Specification

## Purpose

This document defines the Phase 1 CSV export contract for the Service Photo POC.

It specifies:
- the source of truth for export values
- the exact CSV columns
- the source table/field for each column
- transformation and formatting rules
- null/blank handling rules
- export validation rules

This document is intended to support backend implementation of:

- `POST /jobs/{job_id}/export`
- CSV file generation
- export payload snapshot creation
- downstream testing

---

## Export Source of Truth

Phase 1 export must read from the **reviewed content layer only**.

### Allowed source tables
- `listing_jobs`
- `listing_review_overview`
- `listing_review_description`
- `listing_review_specifications`
- `listing_review_accessories`

### Explicitly disallowed as export sources
- `listing_draft_overview`
- `listing_draft_description`
- `listing_draft_specifications`
- `listing_draft_accessories`

Draft content must never appear in exported output.

---

## Export Granularity

Phase 1 export produces **one CSV row per listing job**.

Each exported row represents one approved used-item listing.

There is no one-to-many row expansion in Phase 1.

---

## CSV File Rules

### File format
- UTF-8 encoded CSV
- Comma-delimited
- Include header row
- Double-quote fields when required by CSV encoding rules
- One row per approved job

### File naming recommendation
`service_photo_export_<job_number>_<timestamp_utc>.csv`

Example:
`service_photo_export_JOB-20260419-001_20260419T214530Z.csv`

---

## Column Order

The CSV columns must appear in this exact order:

1. `job_number`
2. `item_category`
3. `product_name`
4. `brand`
5. `model`
6. `product_family`
7. `variant`
8. `mount_type`
9. `serial_number_visible`
10. `condition_summary`
11. `short_title`
12. `description_text`
13. `visible_wear_notes`
14. `key_selling_points`
15. `sensor_format`
16. `megapixels`
17. `lens_mount`
18. `focal_length`
19. `aperture`
20. `iso_range`
21. `shutter_range`
22. `video_capabilities`
23. `storage_media`
24. `connectivity`
25. `weight_grams`
26. `other_specifications_json`
27. `included_accessories_text`
28. `inferred_accessories_text`
29. `missing_typical_accessories_text`
30. `fair_price`
31. `deal_threshold`
32. `ebay_sold_avg`
33. `mpb_retail`
34. `keh_retail`
35. `bh_used`
36. `market_summary`
37. `pricing_sources_json`
38. `pricing_fetched_at_utc`
39. `approved_at`
40. `approved_by`
41. `exported_at`

> **Phase 5 note.** Columns 30–38 are the pricing-enrichment block added in
> Phase 5. They are populated from the `pricing` block on each inbound
> artifact, which is written by `POST /api/v1/inbound/price`. Rows that were
> never priced (or whose pricing pass failed) leave columns 30–38 blank;
> that is a supported state, not an error.

---

## Field Mapping Matrix

| CSV Column | Source Table | Source Field | Required for Export | Transform Rule |
|---|---|---|---|---|
| `job_number` | `listing_jobs` | `job_number` | Yes | Export as-is |
| `item_category` | `listing_jobs` | `item_category` | No | Export as-is or blank |
| `product_name` | `listing_review_overview` | `product_name` | Yes | Trim leading/trailing whitespace |
| `brand` | `listing_review_overview` | `brand` | No | Trim |
| `model` | `listing_review_overview` | `model` | No | Trim |
| `product_family` | `listing_review_overview` | `product_family` | No | Trim |
| `variant` | `listing_review_overview` | `variant` | No | Trim |
| `mount_type` | `listing_review_overview` | `mount_type` | No | Trim |
| `serial_number_visible` | `listing_review_overview` | `serial_number_visible` | No | Trim |
| `condition_summary` | `listing_review_overview` | `condition_summary` | Yes | Trim |
| `short_title` | `listing_review_description` | `short_title` | Yes | Trim |
| `description_text` | `listing_review_description` | `description_text` | Yes | Preserve inner punctuation and line meaning; normalize line breaks |
| `visible_wear_notes` | `listing_review_description` | `visible_wear_notes` | No | Normalize line breaks |
| `key_selling_points` | `listing_review_description` | `key_selling_points` | No | Normalize line breaks |
| `sensor_format` | `listing_review_specifications` | `sensor_format` | Conditionally | Trim |
| `megapixels` | `listing_review_specifications` | `megapixels` | Conditionally | Export numeric as plain decimal string |
| `lens_mount` | `listing_review_specifications` | `lens_mount` | Conditionally | Trim |
| `focal_length` | `listing_review_specifications` | `focal_length` | Conditionally | Trim |
| `aperture` | `listing_review_specifications` | `aperture` | Conditionally | Trim |
| `iso_range` | `listing_review_specifications` | `iso_range` | Conditionally | Trim |
| `shutter_range` | `listing_review_specifications` | `shutter_range` | Conditionally | Trim |
| `video_capabilities` | `listing_review_specifications` | `video_capabilities` | Conditionally | Normalize line breaks |
| `storage_media` | `listing_review_specifications` | `storage_media` | Conditionally | Trim |
| `connectivity` | `listing_review_specifications` | `connectivity` | Conditionally | Trim |
| `weight_grams` | `listing_review_specifications` | `weight_grams` | Conditionally | Export integer as plain string |
| `other_specifications_json` | `listing_review_specifications` | `other_specifications` | No | Serialize JSONB to compact JSON string |
| `included_accessories_text` | `listing_review_accessories` | `included_accessories_text` | Yes | Normalize line breaks |
| `inferred_accessories_text` | `listing_review_accessories` | `inferred_accessories_text` | No | Normalize line breaks |
| `missing_typical_accessories_text` | `listing_review_accessories` | `missing_typical_accessories_text` | No | Normalize line breaks |
| `fair_price` | inbound artifact `pricing.market_valuation.fair_price` | (none) | No | Plain decimal string in USD; blank if unpriced |
| `deal_threshold` | inbound artifact `pricing.market_valuation.deal_threshold` | (none) | No | Plain decimal string in USD; blank if unpriced |
| `ebay_sold_avg` | inbound artifact `pricing.pricing.ebay_sold_avg` | (none) | No | Plain decimal string in USD; blank if unpriced |
| `mpb_retail` | inbound artifact `pricing.pricing.mpb_retail` | (none) | No | Plain decimal string in USD; blank if unpriced |
| `keh_retail` | inbound artifact `pricing.pricing.keh_retail` | (none) | No | Plain decimal string in USD; blank if unpriced |
| `bh_used` | inbound artifact `pricing.pricing.bh_used` | (none) | No | Plain decimal string in USD; blank if unpriced |
| `market_summary` | inbound artifact `pricing.market_summary` | (none) | No | Normalize line breaks |
| `pricing_sources_json` | inbound artifact `pricing.sources` | (none) | No | Serialize the sources array to compact JSON string; blank if unpriced |
| `pricing_fetched_at_utc` | inbound artifact `pricing.fetched_at_utc` | (none) | No | Export ISO-8601 UTC timestamp; blank if unpriced |
| `approved_at` | `listing_jobs` | `approved_at` | Yes | Export ISO-8601 UTC timestamp |
| `approved_by` | `listing_jobs` | `approved_by` | No | Export as-is or blank |
| `exported_at` | `listing_jobs` | `exported_at` | No at extraction time | Populate with export transaction timestamp |

---

## Export Validation Gate

A job is eligible for export only if:

1. `listing_jobs.status = 'approved'`
2. Required reviewed section rows exist:
   - `listing_review_overview`
   - `listing_review_description`
   - `listing_review_specifications`
   - `listing_review_accessories`
3. Required export fields are present and valid
4. The export process reads reviewed content only

### Minimum required values

#### `listing_review_overview`
- `product_name` must be non-null and non-blank
- `condition_summary` must be non-null and non-blank

#### `listing_review_description`
- `short_title` must be non-null and non-blank
- `description_text` must be non-null and non-blank

#### `listing_review_specifications`
At least one meaningful specification field must be populated:
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
- `weight_grams`

#### `listing_review_accessories`
- `included_accessories_text` must be non-null and non-blank

These rules align to the approval gate. Export should assume approval has already enforced them, but should still fail safely if data is unexpectedly missing.

---

## Transformation Rules

### 1. Trim rule
For ordinary text fields:
- remove leading whitespace
- remove trailing whitespace

Do not collapse meaningful internal spacing except where line-break normalization applies.

### 2. Line-break normalization
For long-form text fields:
- replace CRLF with LF
- replace CR with LF
- optionally flatten LF to a single space for single-line CSV output

Recommended Phase 1 export behavior:
- flatten all line breaks to single spaces before CSV write

Applies to:
- `description_text`
- `visible_wear_notes`
- `key_selling_points`
- `included_accessories_text`
- `inferred_accessories_text`
- `missing_typical_accessories_text`

### 3. Blank-string normalization
If a nullable text field is:
- null → export blank field
- empty string → export blank field
- whitespace-only string → export blank field

### 4. Numeric formatting
#### `megapixels`
- export as plain decimal string
- do not append units
- examples:
  - `24`
  - `24.2`

#### `weight_grams`
- export as integer string
- do not append `g`

### 5. JSON serialization
#### `other_specifications_json`
- if null, export blank field
- if object, serialize to valid compact JSON string
- preserve keys exactly as stored

Example:
`{"battery_type":"LP-E6NH","screen_size":"3.0 in"}`

### 6. Timestamp formatting
Use ISO-8601 UTC timestamps.

Examples:
- `2026-04-19T21:45:30Z`
- `2026-04-19T21:45:30.123Z`

Recommended:
- normalize to UTC
- use one consistent precision across the application

---

## Null and Blank Handling

| Source Value | CSV Output |
|---|---|
| `NULL` | blank field |
| `""` | blank field |
| `"   "` | blank field |
| JSON `null` | blank field |
| missing reviewed row | export must fail |

---

## Exported At Behavior

The `exported_at` CSV column should reflect the export transaction timestamp.

Recommended backend order:

1. Read approved reviewed content
2. Generate export payload
3. Set `export_timestamp = now()`
4. Write CSV row using `export_timestamp` in `exported_at`
5. Insert `listing_exports` row
6. Update `listing_jobs.status = 'exported'`
7. Update `listing_jobs.exported_at = export_timestamp`

This keeps the CSV and database export record aligned.

---

## Suggested Export Query Shape

The export implementation should effectively assemble a single flattened row using:

- `listing_jobs`
- inner join `listing_review_overview`
- inner join `listing_review_description`
- inner join `listing_review_specifications`
- inner join `listing_review_accessories`

Recommended join key:
- `job_id`

Do not join any draft tables.

---

## Example CSV Header

```csv
job_number,item_category,product_name,brand,model,product_family,variant,mount_type,serial_number_visible,condition_summary,short_title,description_text,visible_wear_notes,key_selling_points,sensor_format,megapixels,lens_mount,focal_length,aperture,iso_range,shutter_range,video_capabilities,storage_media,connectivity,weight_grams,other_specifications_json,included_accessories_text,inferred_accessories_text,missing_typical_accessories_text,approved_at,approved_by,exported_at
```

---

## Example CSV Row

```csv
JOB-20260419-001,camera body,Canon EOS R6 Mirrorless Camera Body,Canon,EOS R6,EOS R,,Canon RF,,Used camera body with light visible cosmetic wear.,Canon EOS R6 Mirrorless Camera Body,Used Canon EOS R6 mirrorless camera body shown with light cosmetic wear. Sold as pictured.,Light surface wear visible on the body exterior.,Popular full-frame mirrorless body; clean overall presentation.,Full Frame,20.1,Canon RF,,,,,,,680,"{\"battery_type\":\"LP-E6NH\"}","Body cap, battery, charger",,"Box and strap not visible",2026-04-19T21:30:00Z,sergey,2026-04-19T21:45:30Z
```

---

## Export Payload Snapshot Recommendation

The `listing_exports.export_payload_snapshot` field should capture the exact reviewed content used to create the CSV row.

Recommended snapshot shape:

```json
{
  "job": {
    "job_id": "<uuid>",
    "job_number": "JOB-20260419-001",
    "item_category": "camera body",
    "approved_at": "2026-04-19T21:30:00Z",
    "approved_by": "sergey"
  },
  "review": {
    "overview": { "...": "..." },
    "description": { "...": "..." },
    "specifications": { "...": "..." },
    "accessories": { "...": "..." }
  },
  "export": {
    "export_type": "csv",
    "exported_at": "2026-04-19T21:45:30Z"
  }
}
```

---

## Final Recommendation

Phase 1 export should remain intentionally simple:

- one approved job in
- one flattened CSV row out
- reviewed layer only
- deterministic column order
- minimal transformation
- full snapshot preservation in `listing_exports`

This gives the POC a stable downstream contract without overcomplicating the first working slice.
