# Service Photo POC — Claude Code Backend Implementation Guide

## Purpose

This document is the implementation handoff for Claude Code to build the first working backend slice of the Service Photo POC.

It translates the approved architecture, schema, workflow, approval rules, and API contract into a practical build plan.

---

## 1. Current Source-of-Truth Artifacts

Claude Code should treat the following as authoritative:

1. `docs/02_physical_schema_spec.md`
2. `contracts/backend_workflow_spec.md`
3. `contracts/approval_validation_rules.md`
4. `contracts/openapi_service_photo_poc.yaml`
5. `contracts/review_payload_schema.json`
6. `contracts/csv_export_schema.md`
7. `contracts/gemini_response_schema.json`
8. `docs/04_initial_migration.md`
9. `backend/src/service_photo/db/migrations/initial_schema.sql`

Do not invent new workflow behavior that conflicts with these files.

---

## 2. Build Objective

Deliver a local, testable backend that supports the full core Phase 1 happy path:

1. Create listing job
2. Register images
3. Submit job to AI
4. Persist draft content
5. Return review payload
6. Save reviewed content
7. Approve job
8. Export CSV

The backend should be designed for local development first, not production hardening.

---

## 3. Recommended Technical Shape

## Suggested Stack
- Python 3.11+
- FastAPI
- Pydantic v2
- SQLAlchemy 2.x
- Alembic
- PostgreSQL 15+
- pytest

## Project Structure (already scaffolded — do not reorganize)

```text
backend/
  src/
    service_photo/        ← Python package root
      api/               ← FastAPI route handlers
      core/              ← Config, settings, env loading
      db/                ← Session management, declarative base
        migrations/      ← Alembic env + versions
          versions/
      exports/           ← CSV generation logic
      integrations/      ← Gemini client interface, mock, and real
      models/            ← SQLAlchemy ORM models
      repositories/      ← Data access helpers (DB read/write)
      schemas/           ← Pydantic request/response schemas
      services/          ← Business logic (one service per workflow step)
      utils/             ← Shared utilities
      prompts/           ← Gemini prompt templates
  tests/
    fixtures/            ← Test factories and seed builders
    integration/         ← Integration tests (hit real DB)
    unit/                ← Unit tests (no DB)
  pyproject.toml         ← Dependency management (not requirements.txt)
  README.md
```

See §15 for the rationale behind this structure.

---

## 4. Required Backend Modules

## A. Database Layer
Implement:
- SQLAlchemy models for every Phase 1 table
- migration execution support
- DB session management
- transaction wrapper for multi-table writes

## B. API Layer
Implement endpoints matching the OpenAPI contract exactly:
- `POST /jobs`
- `GET /jobs/{job_id}`
- `POST /jobs/{job_id}/images`
- `POST /jobs/{job_id}/submit`
- `GET /jobs/{job_id}/review-payload`
- `PUT /jobs/{job_id}/review`
- `POST /jobs/{job_id}/approve`
- `POST /jobs/{job_id}/export`

## C. Service Layer
Implement dedicated services for:
- job creation
- image registration
- Gemini submission/orchestration
- review payload assembly
- reviewed content upsert
- approval validation
- CSV export generation
- status transition/history writing

## D. Integration Layer
Implement Gemini integration behind a clean interface so the first working slice can support:
- real Gemini integration later
- local mock/fake response mode immediately

## E. Export Layer
Implement:
- reviewed-content-only row assembly
- deterministic CSV column ordering
- export payload snapshot creation
- file write to local storage path

---

## 5. Required Database Models

Claude Code should create ORM models for:

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

Each model should reflect:
- column names exactly
- types exactly
- PK/FK relationships
- unique constraints
- indexes where appropriate

---

## 6. Required Service Behaviors

## 6.1 Job Creation Service
Must:
- generate UUID `job_id`
- generate unique `job_number`
- insert `listing_jobs` row in `initialized`
- insert initial status history row

## 6.2 Image Registration Service
Must:
- reject terminal jobs
- enforce unique `image_order` per job
- insert image metadata row
- update job timestamp

## 6.3 Submit-to-AI Service
Must:
- validate job exists
- validate valid submit status
- validate job has at least one image
- move status to `submitted_to_ai`
- assemble images ordered by `image_order`
- call Gemini client
- validate response structure
- upsert all four draft tables
- move status to `ready_for_review`
- handle `validation_failed`
- handle `ai_error`

## 6.4 Review Payload Service
Must:
- fetch job
- fetch ordered images
- fetch draft layer
- fetch review layer
- return one composite payload shaped exactly like `review_payload_schema.json`

## 6.5 Review Save Service
Must:
- allow partial section writes
- set status to `under_review` on first review save from `ready_for_review`
- upsert only provided sections
- leave omitted sections untouched
- update review audit fields

## 6.6 Approval Service
Must:
- require status `under_review`
- validate against reviewed layer only
- collect all validation failures in one response
- update job status to `approved`
- insert status history

## 6.7 Export Service
Must:
- require status `approved`
- read from reviewed tables only
- transform values per CSV export spec
- write one-row CSV
- create `listing_exports` row
- update job status to `exported`
- preserve exact export snapshot

---

## 7. Non-Negotiable Implementation Rules

1. Draft and review layers must stay separate.
2. Approval must never read draft tables.
3. Export must never read draft tables.
4. Every status transition must create a history row.
5. Multi-table workflow writes must be transactional.
6. Response shapes must align to OpenAPI.
7. Review payload must align to `review_payload_schema.json`.
8. CSV column order must align exactly to the export mapping spec.

---

## 8. Recommended Build Order

### Phase A — Foundation
1. Create backend project skeleton
2. Add config/env loading
3. Add DB session + base ORM setup
4. Add migration execution support
5. Run initial migration

### Phase B — Data Model
6. Implement ORM models
7. Implement repository helpers
8. Add status transition utility

### Phase C — API Happy Path
9. Implement `POST /jobs`
10. Implement `POST /jobs/{job_id}/images`
11. Implement `GET /jobs/{job_id}`
12. Implement fake/mock Gemini client
13. Implement `POST /jobs/{job_id}/submit`
14. Implement `GET /jobs/{job_id}/review-payload`
15. Implement `PUT /jobs/{job_id}/review`
16. Implement `POST /jobs/{job_id}/approve`
17. Implement `POST /jobs/{job_id}/export`

### Phase D — Validation + Tests
18. Add response-model validation tests
19. Add approval gate tests
20. Add export mapping tests
21. Add end-to-end happy path test

---

## 9. Recommended Fake Gemini Mode for First Build

Before integrating real Gemini, Claude Code should implement a provider abstraction:

- `GeminiClientInterface`
- `MockGeminiClient`
- `RealGeminiClient`

For the first working slice, use `MockGeminiClient` to return a valid structured payload matching the expected draft shape.

This allows:
- backend/API buildout immediately
- deterministic tests
- schema validation without external dependency risk

---

## 10. Storage Assumptions for Phase 1

Use local filesystem storage for:
- uploaded image binaries
- exported CSVs
- optional raw logs

Recommended directories:

```text
/storage
  /images
  /exports
  /logs
```

The database stores metadata and paths only.

---

## 11. Required Test Coverage

Claude Code should build tests for at minimum:

## Unit Tests
- job number generation
- status transition helper
- approval validator
- CSV transform/flatten helpers
- review payload assembly

## Integration Tests
- create job
- register image
- submit job with fake Gemini success
- submit job with validation failure
- save review sections incrementally
- approve valid reviewed content
- reject invalid approval
- export approved job

## End-to-End Test
One full scenario:
- create job
- add images
- submit
- receive draft rows
- save review rows
- approve
- export
- verify DB state and CSV output

---

## 12. Key Risks Claude Code Should Avoid

- Overwriting reviewed data with draft data
- Building review payload shape that drifts from schema
- Letting export read draft content
- Skipping status history inserts
- Allowing partial invalid approval success
- Mutating absent review sections on partial save
- Adding out-of-scope enrichment features in Phase 1

---

## 13. Definition of Done for First Working Slice

The backend is considered done for the first working slice when:

1. Migration runs successfully against local PostgreSQL
2. All Phase 1 tables exist
3. All core endpoints are implemented
4. Mock Gemini mode works end to end
5. Approval gate works exactly per spec
6. CSV export works exactly per spec
7. Tests cover the happy path and major failures
8. Local README explains how to run the backend

---

## 14. Immediate Next Step

All pre-implementation artifacts are complete. The next chat should use `docs/claude_code_starter_prompt.md` as the opening prompt and begin at Phase A of the build order in §8.

---

## 15. Structure Decision Record

**Date:** 2026-04-19

**Decision:** Use `/backend/src/service_photo/` as the Python package root, not `/backend/app/`.

**Reason:** The directory scaffold was already created before this guide was written. The `/src/service_photo/` layout aligns with `pyproject.toml`-based packaging (the project standard), keeps the package name explicit, and avoids restructuring work. The module names inside (`api/`, `core/`, `db/`, `models/`, `repositories/`, `schemas/`, `services/`, `integrations/`, `exports/`) are identical to those recommended in the original guide.

**Also decided:** Use `pyproject.toml` for dependency management rather than `requirements.txt`. This is the modern Python standard and was the original plan in the Phase 2 task list.

**Also decided:** Alembic migrations live at `backend/src/service_photo/db/migrations/` (already scaffolded with a `versions/` subdirectory), not at a top-level `/migrations/` directory.

---

## 16. extraction_warnings — Schema Gap Fixed

**Note added:** The original version of this guide was written before `contracts/gemini_response_schema.json` was finalized. That schema defines a top-level `extraction_warnings` field (array of strings or null) that had no corresponding column in the migration.

**Resolution:** `extraction_warnings JSONB` has been added to `listing_draft_overview` in both `docs/04_initial_migration.md` and `backend/src/service_photo/db/migrations/initial_schema.sql`. The mock Gemini client must include this field in its response payload.
