# Service Photo POC — Project Documentation

## 1. Project Overview

### Project Name
Service Photo POC

### Purpose
Build a lightweight proof of concept that helps a camera store create faster, more standardized used-equipment listings from product photos.

### Business Problem
Store staff currently take photos of used camera equipment and then manually gather product details, write listing titles and descriptions, and prepare listing data for online posting. This process is time-consuming and inconsistent.

### Proposed Solution
Create a human-in-the-loop application that:
- accepts photos of one used item
- sends those photos to Gemini for analysis
- returns structured draft listing data
- allows a user to review and edit the results
- exports the final approved data to CSV

### POC Framing
This is an **AI-assisted listing generation workflow**, not a fully automated listing engine.

---

## 2. POC Objective

### Primary Objective
Validate that Gemini can produce useful draft listing data from real used-equipment photos with enough quality to reduce manual listing effort.

### Success Criteria
The POC should demonstrate that staff can:
- upload product photos
- receive structured draft item details
- review and correct the output quickly
- export clean, usable listing data to CSV

---

## 3. Scope

## In Scope
- local/manual image upload
- one listing job per used item
- Gemini-based image analysis
- structured draft response handling
- user review and editing step
- CSV export
- local file/job storage
- request/response logging

## Out of Scope
- direct posting to eBay, Shopify, or other marketplaces
- pricing automation
- barcode scanning
- inventory management integration
- user authentication
- production deployment hardening
- full workflow automation with no review step

---

## 4. Core Workflow

1. User uploads photos for one used camera item.
2. Application creates a listing job.
3. Backend prepares prompt + images + schema for Gemini.
4. Gemini returns structured draft listing data.
5. Backend validates and normalizes the response.
6. User reviews and edits extracted details.
7. User approves the listing.
8. Application exports approved data to CSV.
9. Job artifacts are stored for traceability.

---

## 5. High-Level Architecture

### Major Components
- **User / Reviewer**
- **Review Application / Shell UI**
- **Backend Orchestrator**
- **Gemini API Integration**
- **Storage Layer**
- **CSV Export Layer**

### Architecture Flow
```text
Store Employee
→ Upload Product Photos
→ Create Listing Job
→ Backend Orchestrator
→ Gemini API Request
→ Gemini Structured Response
→ Validation / Transformation
→ Review UI
→ Human Edit / Approve
→ CSV Export
→ Archive Job Data
```

---

## 6. Functional Components

## A. Review App / Shell UI
Purpose:
- allow users to upload and preview item photos
- trigger Gemini analysis
- review extracted data
- edit listing fields
- approve and export final output

### Key Features
- image upload
- photo preview
- extracted field display
- editable form fields
- review warnings / low-confidence markers
- export action

## B. Backend Orchestrator
Purpose:
- control workflow state
- manage Gemini request creation
- validate responses
- map reviewed data into CSV format

### Responsibilities
- job creation
- status tracking
- payload assembly
- response validation
- logging
- export generation

## C. Gemini Integration
Purpose:
- analyze uploaded item photos
- identify visible details
- draft listing content
- return structured JSON output

### Expected Use
Gemini should be prompted to:
- identify item type
- identify brand/model when visible
- extract visible specs when supported by the image
- identify accessories
- note visible condition issues
- draft listing title
- draft listing description
- flag uncertainty or missing information

## D. Storage Layer
Purpose:
- retain source images and job artifacts

### Stored Artifacts
- uploaded image files
- job metadata
- raw AI response
- validated AI output
- user-corrected output
- exported CSV files
- logs

## E. Export Layer
Purpose:
- map approved data into final listing CSV format

---

## 7. Suggested Job Status Lifecycle

```text
Uploaded
→ Initialized
→ Submitted to AI
→ AI Response Received
→ Ready for Review
→ Under Review
→ Approved
→ Exported
```

### Optional Exception States
```text
Validation Failed
AI Error
Needs Rework
Rejected
```

---

## 8. Initial Data Model Concept

## Listing Job
- job_id
- created_at
- created_by
- status
- source_images[]
- raw_ai_response
- validated_ai_output
- reviewer_output
- export_file_path

## Extracted Listing Fields
- category
- brand
- product_family
- model_name
- mount_type
- focal_length
- aperture
- serial_number
- condition_grade
- visible_wear_notes
- included_accessories
- missing_accessories
- draft_title
- draft_description
- confidence_flags
- manual_review_notes

---

## 9. Business Rules

### AI Output Rules
- AI output is treated as draft content only.
- Visually unsupported assumptions should not be trusted as final.
- Uncertain fields should be flagged for manual review.
- Human reviewer edits override AI output.

### Listing Workflow Rules
- One listing job represents one item.
- Images remain associated with the originating listing job.
- Only approved listings can be exported.
- CSV export must validate required fields before final output.

---

## 10. Risks and Considerations

## Key Risks
- Gemini may misidentify visually similar camera models.
- Product labels or serial numbers may be unreadable.
- Accessories may be omitted or partially hidden.
- Condition assessments may be subjective.
- Users may over-trust AI-generated details.

## Mitigations
- Encourage close-up photos of labels, badges, and serial plates.
- Surface low-confidence outputs for review.
- Require human approval before export.
- Log AI responses for prompt tuning and debugging.
- Keep the first version narrow and structured.

---

## 11. Recommended POC Boundaries

### Best Starting Point
Start with a narrow item class if needed, such as:
- camera lenses first
or
- one small set of common product categories

### Why
This reduces ambiguity and makes field extraction, prompt design, and validation easier in the first build phase.

---

## 12. Project Folder Structure

The repository uses the following layout. **This is the authoritative structure going forward** — it supersedes any earlier informal sketch.

```text
UsedItemsListing_App/
│
├── README.md                              # Project overview + quickstart
├── .gitignore
├── .env.example                           # Documented env vars (no secrets)
│
├── docs/                                  # Planning, reference, decisions
│   ├── 00_project_documentation.md        # This file
│   ├── 01_database_schema_architecture.md
│   ├── 02_physical_schema_spec.md
│   ├── 03_ui_design.md
│   ├── diagrams/
│   │   └── system_architecture.jsx
│   ├── decisions/                         # ADRs (dated markdown)
│   │   └── 0001-draft-vs-review-layers.md
│   └── progress.md                        # Cross-session task tracker
│
├── contracts/                             # Machine-consumable API contracts
│   ├── openapi_service_photo_poc.yaml
│   ├── review_payload_schema.json
│   ├── approval_validation_rules.md
│   └── backend_workflow_spec.md
│
├── backend/                               # Python service (FastAPI + PostgreSQL)
│   ├── README.md
│   ├── src/
│   │   └── service_photo/
│   │       ├── main.py                    # FastAPI app factory
│   │       ├── config.py
│   │       ├── api/                       # Thin route handlers
│   │       ├── services/                  # Business logic (thick)
│   │       ├── db/
│   │       │   ├── engine.py
│   │       │   ├── models.py              # SQLAlchemy
│   │       │   └── migrations/versions/   # Alembic
│   │       ├── schemas/                   # Pydantic I/O models
│   │       ├── prompts/                   # Gemini prompt templates (versioned)
│   │       └── utils/
│   └── tests/
│       ├── unit/
│       ├── integration/
│       └── fixtures/
│
├── frontend/                              # Review UI shell
│   ├── README.md
│   ├── public/
│   │   └── logo.png
│   ├── src/
│   └── tests/
│
├── test_data/                             # Committed fixtures for dev/testing
│   ├── sample_images/
│   └── image_legend.xlsx
│
├── scripts/                               # Dev/ops helpers (seed, reset, inspect)
│
└── storage/                               # Runtime artifacts (gitignored)
    ├── images/                            # Uploaded item photos
    ├── exports/                           # Generated CSVs
    └── logs/                              # Request/response logs
```

### 12.1 Folder Purpose Rules

| Folder | Role | Mutability |
|---|---|---|
| `docs/` | Human-authored planning, reference, and decisions | Evolves continuously |
| `contracts/` | Frozen agreements between backend and consumers | Change-reviewed |
| `backend/` | Python source only | Source-controlled |
| `frontend/` | Review UI source | Source-controlled |
| `test_data/` | Committed fixtures (sample images, legends) | Source-controlled |
| `scripts/` | Dev/ops utilities | Source-controlled |
| `storage/` | Runtime artifacts (images, exports, logs) | Gitignored, volatile |

### 12.2 Important Constraints

- **Runtime storage never lives inside `backend/` or `frontend/`.** All runtime writes go to `storage/`.
- **Prompts live inside `backend/src/service_photo/prompts/`** — they are loaded at runtime by backend code and are version-named (`listing_extraction_v1.md`, `_v2.md`, etc.).
- **`contracts/` is the single source of truth** for API shapes. Backend Pydantic models mirror these; the frontend consumes the OpenAPI spec directly.
- **Each ADR** in `docs/decisions/` is a dated markdown file capturing a significant decision, its alternatives, and its rationale.
- **Numbered doc prefixes (`00_`, `01_`, ...)** enforce reading order. Preserve the numbering when renaming or inserting new docs.
- **Progress tracking lives in `docs/progress.md`** — update at the end of each working session per the global CLAUDE.md session-management pattern.

---

## 13. Recommended Next Step

### Step One of the Build
Define the exact **input/output contract** for the application.

That means finalizing:
1. the CSV output schema
2. the Gemini JSON response schema
3. the review form fields

These three items should become the source of truth for the rest of the build.

---

## 14. Build Notes for the Next Chat

When resuming in a new chat, the immediate priority should be:

### Next Working Task
Create:
- the CSV schema
- the Gemini response schema
- the first-pass prompt specification

### Build Intent
The first build should prioritize:
- speed of validation
- clean structure
- easy manual review
- real-world testability with actual camera images

---

## 15. Summary

This project is a focused proof of concept for using Gemini to assist camera-store staff in creating used-equipment listings from photos. The architecture centers on structured AI extraction, human review, and clean CSV export. The system should remain lightweight, review-driven, and narrow in scope for the first iteration so the concept can be validated quickly with real item photos.
