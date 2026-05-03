# Service Photo POC — Backend

FastAPI + PostgreSQL backend for the AI-assisted used-camera listing workflow.

## Prerequisites

- Python 3.11+
- PostgreSQL 15+ running locally
- `pip` or a virtual environment manager

## Quick Start

```bash
# 1. Navigate to the backend directory
cd backend

# 2. Install the package and all dependencies in editable mode
pip install -e ".[dev]"

# 3. (Optional) Create a .env file to override defaults
#    Defaults: DATABASE_URL=postgresql://postgres:postgres@localhost:5432/service_photo_dev
#              USE_MOCK_GEMINI=true

# 4. Create the development database in PostgreSQL
createdb -U postgres service_photo_dev   # or use psql

# 5. Run Alembic migration to create all 12 tables
alembic upgrade head

# 6. Start the development server
uvicorn service_photo.main:app --reload --host 0.0.0.0 --port 8000
```

API is available at: **http://localhost:8000/api/v1**
Interactive docs:     **http://localhost:8000/docs**

## Environment Variables

| Variable           | Default                                                     | Purpose                         |
|--------------------|-------------------------------------------------------------|---------------------------------|
| `DATABASE_URL`     | `postgresql://postgres:postgres@localhost:5432/service_photo_dev` | PostgreSQL connection string |
| `GEMINI_API_KEY`   | `placeholder-not-needed-for-mock`                           | Google Gemini API key           |
| `STORAGE_BASE_PATH`| `./storage`                                                 | Root directory for images/exports/logs |
| `LOG_LEVEL`        | `INFO`                                                      | Python logging level            |
| `USE_MOCK_GEMINI`  | `true`                                                      | Use mock Gemini client (set `false` to call real API) |

## Running Tests

```bash
# From the backend/ directory.
# Tests use the service_photo_test database (created/destroyed automatically).

createdb -U postgres service_photo_test   # one-time setup

# Run all tests
pytest

# Run with coverage report
pytest --cov=service_photo --cov-report=term-missing

# Run only unit tests (no DB required is not applicable — unit tests use the test DB too)
pytest tests/unit/

# Run only integration tests
pytest tests/integration/

# Run the end-to-end happy path
pytest tests/test_workflow_e2e.py -v
```

## Project Layout

```
backend/
  alembic.ini                        # Alembic config
  pyproject.toml                     # Dependencies and build config
  src/
    service_photo/
      main.py                        # FastAPI app + lifespan
      core/
        config.py                    # Settings (pydantic-settings)
      db/
        base.py                      # SQLAlchemy DeclarativeBase
        session.py                   # Engine + get_db() dependency
        migrations/
          env.py                     # Alembic env
          versions/
            001_initial_schema.py    # All 12 Phase 1 tables
      models/                        # SQLAlchemy ORM models (one file per table)
      schemas/                       # Pydantic request/response schemas
        jobs.py                      # ListingJob, ListingJobDetail, inputs
        draft.py                     # Draft layer schemas
        review.py                    # Review layer schemas + ReviewPayload
        export.py                    # ListingExport schema
        errors.py                    # ErrorResponse, ApprovalValidationError
      repositories/                  # Data access helpers (no business logic)
        jobs.py  images.py  draft.py  review.py  exports.py
      services/                      # Business logic (one module per workflow step)
        job_service.py               # POST /jobs
        image_service.py             # POST /jobs/{id}/images
        submit_service.py            # POST /jobs/{id}/submit (Gemini orchestration)
        review_payload_service.py    # GET /jobs/{id}/review-payload
        review_service.py            # PUT /jobs/{id}/review
        approval_service.py          # POST /jobs/{id}/approve
        export_service.py            # POST /jobs/{id}/export
      integrations/
        gemini_interface.py          # Abstract client contract
        mock_gemini.py               # Deterministic Canon EOS R6 mock
        real_gemini.py               # Real client stub (Phase 1 not wired)
      exports/
        csv_generator.py             # generate_csv_row() + write_csv_to_storage()
      api/
        routes.py                    # All 8 FastAPI route handlers
      utils/
        job_number.py                # JOB-YYYYMMDD-NNN generator
      prompts/
        listing_extraction_v1.md     # Gemini extraction prompt
  tests/
    conftest.py                      # Session/function-scoped DB fixtures + TestClient
    fixtures/
      factories.py                   # Seed builders for all 7 scenarios (A–G)
    unit/
      test_job_number.py
      test_approval_validator.py
      test_csv_transforms.py
    integration/
      test_jobs.py  test_images.py  test_submit.py
      test_review.py  test_approval.py  test_export.py
    test_workflow_e2e.py             # Full happy path end-to-end test
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/jobs` | Create a listing job |
| GET | `/api/v1/jobs/{job_id}` | Get job with images + history |
| POST | `/api/v1/jobs/{job_id}/images` | Register an image |
| POST | `/api/v1/jobs/{job_id}/submit` | Submit to AI (mock or real Gemini) |
| GET | `/api/v1/jobs/{job_id}/review-payload` | Get full draft + review payload |
| PUT | `/api/v1/jobs/{job_id}/review` | Save reviewed content (partial upsert) |
| POST | `/api/v1/jobs/{job_id}/approve` | Run approval gate |
| POST | `/api/v1/jobs/{job_id}/export` | Generate CSV export |

## Architecture Notes

- **Two content layers**: `listing_draft_*` (AI output, read-only after creation) and `listing_review_*` (human-edited, authoritative for export). They are never merged.
- **Append-only status history**: every status transition inserts a new row into `listing_job_status_history`.
- **Approval gate**: collects ALL failing rules in one response — does not short-circuit on the first failure.
- **Export**: reads exclusively from the four review tables. Draft content never appears in CSV output.
- **Gemini mock**: `USE_MOCK_GEMINI=true` (default) uses `MockGeminiClient` which returns a deterministic Canon EOS R6 payload without any API call.

## References

- API contract: [`contracts/openapi_service_photo_poc.yaml`](../contracts/openapi_service_photo_poc.yaml)
- Workflow spec: [`contracts/backend_workflow_spec.md`](../contracts/backend_workflow_spec.md)
- Approval rules: [`contracts/approval_validation_rules.md`](../contracts/approval_validation_rules.md)
- CSV export spec: [`contracts/csv_export_schema.md`](../contracts/csv_export_schema.md)
- Physical schema: [`docs/02_physical_schema_spec.md`](../docs/02_physical_schema_spec.md)
