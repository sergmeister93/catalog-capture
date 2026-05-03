# Service Photo POC — Claude Code Starter Prompt

Use the following prompt in a new Claude Code chat to start backend implementation.

---

Read these project files as the authoritative source of truth:

- `docs/02_physical_schema_spec.md`
- `contracts/backend_workflow_spec.md`
- `contracts/approval_validation_rules.md`
- `contracts/openapi_service_photo_poc.yaml`
- `contracts/review_payload_schema.json`
- `contracts/csv_export_schema.md`
- `contracts/gemini_response_schema.json`
- `docs/04_initial_migration.md`
- `backend/src/service_photo/db/migrations/initial_schema.sql`
- `docs/claude_code_backend_implementation_guide.md`
- `docs/claude_code_seed_data_spec.md`

Your task is to build the first working backend slice of the Service Photo POC.

## Build goals

Implement a local FastAPI + PostgreSQL backend that supports the full Phase 1 core workflow:

1. create listing job
2. register images
3. submit job to AI
4. persist draft layer
5. return review payload
6. save reviewed content
7. approve job
8. export CSV

## Hard requirements

- Follow the OpenAPI contract exactly
- Follow the physical schema exactly (including `extraction_warnings JSONB` on `listing_draft_overview`)
- Keep draft and review layers fully separate
- Approval must validate reviewed content only
- Export must read reviewed content only
- Every status transition must create a history row
- Use transactions for multi-table workflow writes
- Use a Gemini provider abstraction with a mock implementation first
- Do not add out-of-scope features like review enrichment, pricing enrichment, auth, marketplace posting, or production infra

## Technical preferences

- Python 3.11+
- FastAPI
- Pydantic v2
- SQLAlchemy 2.x (async-compatible declarative style)
- Alembic
- pytest
- `pyproject.toml` for dependency management (not requirements.txt)
- Local filesystem storage for exports/images metadata paths
- `DATABASE_URL` environment variable for PostgreSQL connection string
- Other env vars expected in `core/config.py`: `GEMINI_API_KEY` (str), `STORAGE_BASE_PATH` (str, default `./storage`), `LOG_LEVEL` (str, default `INFO`)

## Project structure (already scaffolded — do not reorganize)

```
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
  pyproject.toml
  README.md
```

All `__init__.py` files are already in place. Do not move or rename any directories.

## Deliverables

1. `pyproject.toml` with all runtime and dev dependencies pinned
2. `backend/src/service_photo/core/config.py` — env/settings loading
3. `backend/src/service_photo/db/session.py` — SQLAlchemy session factory
4. `backend/src/service_photo/db/base.py` — declarative base
5. Alembic configuration wired to `backend/src/service_photo/db/migrations/`
6. SQLAlchemy ORM models for all 12 Phase 1 tables (in `models/`)
7. Repository helpers for each table group (in `repositories/`)
8. Pydantic schemas mirroring contracts (in `schemas/`)
9. `GeminiClientInterface` + `MockGeminiClient` + `RealGeminiClient` stub (in `integrations/`); `RealGeminiClient` must load the prompt from `backend/src/service_photo/prompts/listing_extraction_v1.md`
10. Service layer — one module per workflow step (in `services/`)
11. FastAPI route handlers for all 8 Phase 1 endpoints (in `api/`)
12. CSV export generator (in `exports/`)
13. `tests/fixtures/factories.py` — seed builders for all 7 scenarios
14. `tests/unit/` — unit tests for job number generation, status transition, approval validator, CSV transforms
15. `tests/integration/` — integration tests for all 8 endpoints + approval failures + export; must assert: (a) status history row count increases on each transition, (b) draft content never mutates after creation, (c) export CSV column order matches `contracts/csv_export_schema.md` exactly, (d) approval returns all failing rule IDs in one response (not just the first)
16. `tests/test_workflow_e2e.py` — one full happy-path scenario
17. Updated `backend/README.md` with local run instructions

## Build order

1. `pyproject.toml` + `core/config.py` + `db/session.py` + `db/base.py`
2. Wire Alembic to the existing migrations directory
3. Run `initial_schema.sql` (or generate equivalent Alembic migration) against local PostgreSQL
4. Implement ORM models for all 12 tables
5. Implement repository helpers
6. Implement `MockGeminiClient` returning a valid `gemini_response_schema.json`-compliant payload
7. Implement `POST /jobs` + `POST /jobs/{job_id}/images` + `GET /jobs/{job_id}`
8. Implement `POST /jobs/{job_id}/submit` using mock Gemini
9. Implement `GET /jobs/{job_id}/review-payload`
10. Implement `PUT /jobs/{job_id}/review`
11. Implement `POST /jobs/{job_id}/approve`
12. Implement `POST /jobs/{job_id}/export`
13. Implement test fixtures and all test suites

## Expected behavior

- `POST /jobs` creates an initialized job and status history row
- `POST /jobs/{job_id}/images` registers image metadata and enforces unique image order
- `POST /jobs/{job_id}/submit` uses ordered images, mock Gemini output, response validation, and draft upserts; stores `extraction_warnings` in `listing_draft_overview`
- `GET /jobs/{job_id}/review-payload` returns job + images + draft + review in the exact expected shape from `contracts/review_payload_schema.json`
- `PUT /jobs/{job_id}/review` supports partial section upserts without wiping omitted sections
- `POST /jobs/{job_id}/approve` returns all validation failures in one response when invalid
- `POST /jobs/{job_id}/export` writes a one-row CSV using the exact export column order from `contracts/csv_export_schema.md` and logs the export record

## Mock Gemini client requirements

The mock client must return a response that is valid against `contracts/gemini_response_schema.json`.
This includes the top-level `extraction_warnings` field (may be `null` or a JSON array of strings).
Use realistic camera-item data (e.g. Canon EOS R6 body) so seed scenarios are human-readable.

## Testing requirements

Create seed/factory coverage for all 7 scenarios defined in `docs/claude_code_seed_data_spec.md`:
- initialized job (Scenario A)
- job with images (Scenario B)
- ready-for-review job with draft content (Scenario C)
- under-review job with partial reviewed content (Scenario D)
- approval-failure case (Scenario E)
- approved job (Scenario F)
- exported job (Scenario G)

## Local environment assumption

Assume PostgreSQL is running on `localhost:5432` with a database named `service_photo_dev` and a user/password of `postgres`/`postgres`. Do not add environment setup instructions or Docker configuration — just wire `DATABASE_URL` accordingly in the default config.

## Conflict resolution rule

When making implementation decisions, prefer the documented specs over assumptions.
If you find a contract gap that would require a guess, **stop**: write a `TODO` comment with the exact question and do not proceed past that point until the question is answered. Do not silently improvise.
