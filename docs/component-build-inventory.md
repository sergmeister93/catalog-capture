# Component Build Inventory

Structured inventory of every non-trivial component in the codebase, with purpose, dependencies, and status. Grouped by layer. Status key: **Complete** (implemented and in active use), **Dormant** (implemented, tested, not wired to the active UI), **Partial** (implemented but incomplete), **Placeholder** (stub only), **Spec-only** (documented, not implemented).

## Frontend

| Component | Type | Purpose | Key Files | Dependencies | Status | Notes |
|---|---|---|---|---|---|---|
| App shell | React root | Mounts the router; applies global layout | `frontend/src/App.tsx`, `main.tsx`, `index.css` | React 18, Vite | Complete | Custom hash routing; no react-router |
| Hash router | State module | Maps `#/inbound` etc. to screens | `frontend/src/state/router.ts` | — | Complete | Minimal, hand-rolled |
| Extraction handoff | State module | Stores cross-screen trigger flag in localStorage | `frontend/src/state/extractionHandoff.ts` | `localStorage` | Complete | Subject to StrictMode gotcha (#8) |
| Inbound screen | Screen component | Upload / Review / Batch History — the entire user-facing UI | `frontend/src/screens/InboundScreen.tsx` (~1,300 LOC) | `api/inbound.ts`, `localStorage` | Complete | God component; refactor target |
| Prep screen | Screen component | Legacy prep/upload view from pre-pivot era | `frontend/src/screens/PrepScreen.tsx` | — | Dormant | Retained after pivot; not in active navigation |
| Batches screen | Screen component | Separate batch listing (superseded by Inbound's Batch History tab) | `frontend/src/screens/BatchesScreen.tsx` | — | Dormant | Superseded but still present |
| Inbound API client | TS module | Fetch wrapper for `/api/v1/inbound/*` | `frontend/src/api/inbound.ts` | native `fetch` | Complete | No retry; throws on non-2xx |
| Design tokens & humanizers | CSS + helpers | Type/spacing/radius/shadow scale; humanization helpers scrub vendor strings | `frontend/src/index.css`, helpers at bottom of `InboundScreen.tsx` | Inter + Manrope via Google Fonts CDN | Complete | Source of truth for styling (see gotcha #10) |

## Backend — active (`/inbound` pipeline)

| Component | Type | Purpose | Key Files | Dependencies | Status | Notes |
|---|---|---|---|---|---|---|
| FastAPI app | Entry point | HTTP app bootstrap, CORS, custom error handler | `backend/src/service_photo/main.py` | FastAPI | Complete | Custom `HTTPException` handler unwraps dict detail (gotcha #2) |
| Config loader | Core utility | Loads `.env` via absolute path | `backend/src/service_photo/core/config.py` | pydantic-settings | Complete | Abs path is load-bearing (gotcha #5) |
| Inbound routes | API module | 7 endpoints for upload / extract / poll / batches / images / export | `backend/src/service_photo/api/inbound_routes.py` (~940 LOC) | `inbound_extraction`, `export_service` | Complete | Large; mixes routing + orchestration + job tracking |
| Inbound extraction service | Service | Scans folder, dispatches per-image Gemini call, writes artifacts, exposes progress callbacks | `backend/src/service_photo/services/inbound_extraction.py` | `real_gemini` | Complete | Shared with CLI; daemon-threaded |
| Gemini interface | Protocol | Integration abstraction | `backend/src/service_photo/integrations/gemini_interface.py` | — | Complete | Enables mock/real swap |
| Real Gemini | Integration | Calls `google-genai` with multimodal + Google Search grounding | `backend/src/service_photo/integrations/real_gemini.py` | `google-genai` ≥1.0 | Complete | SDK-migrated in Phase 5 (gotcha #6) |
| Mock Gemini | Integration | Deterministic response for offline dev | `backend/src/service_photo/integrations/mock_gemini.py` | — | Complete | Toggled by `USE_MOCK_GEMINI` |
| Extraction prompt | Prompt asset | Instructions sent to Gemini for visual + pricing extraction | `backend/src/service_photo/prompts/listing_extraction_v1.md` | — | Complete | Externalized for iteration |
| CSV exporter | Service | Flattens approved artifacts to CSV per contract | `backend/src/service_photo/services/export_service.py` | csv stdlib | Complete | 9 pricing cols added in Phase 5 |
| In-memory job tracker | In-module state | Tracks extraction progress for polling | `inbound_routes.py::_jobs` | — | Complete (fragile) | Lost on restart; Phase 7 promotion candidate |

## Backend — dormant (`/jobs` DB pipeline)

| Component | Type | Purpose | Key Files | Dependencies | Status | Notes |
|---|---|---|---|---|---|---|
| Jobs routes | API module | 8 endpoints for full DB-backed lifecycle | `backend/src/service_photo/api/routes.py` | all services below | Dormant | 47/47 tests passing at Phase 2 verification |
| Job service | Service | Create job, manage status transitions | `services/job_service.py` | `repositories/jobs` | Dormant | |
| Submit service | Service | Trigger AI, persist draft | `services/submit_service.py` | `integrations/gemini_interface`, `repositories/draft` | Dormant | |
| Review payload service | Service | Combine draft + review for UI | `services/review_payload_service.py` | repositories | Dormant | |
| Review service | Service | Upsert per-section reviewed content | `services/review_service.py` | `repositories/review` | Dormant | |
| Approval service | Service | Run approval gate; return all failures | `services/approval_service.py` | approval rules | Dormant | |
| Export service (DB) | Service | Snapshot review layer to export table and CSV | `services/export_service.py` | `repositories/exports` | Dormant | |
| Image service | Service | Register / serve job images | `services/image_service.py` | `repositories/images` | Dormant | |
| Repositories (5) | Data access | CRUD for draft, review, jobs, images, exports | `repositories/*.py` | SQLAlchemy | Dormant | |
| ORM models (12) | Data model | Tables for jobs, images, status history, draft, review, exports | `models/*.py` | SQLAlchemy 2.0 | Dormant | Matches `docs/02_physical_schema_spec.md` |
| Pydantic schemas | Validation | Request/response shapes | `schemas/*.py` (draft, review, jobs, export, errors) | Pydantic ≥2.11 | Dormant | `ReviewPayload` has forward-ref trap (gotcha #1) |
| Alembic migration | Migration | Initial schema | `db/migrations/versions/001_initial_schema.py` | Alembic | Dormant | Single revision; no incremental migrations yet |

## Contracts & Specifications

| Component | Type | Purpose | Key Files | Status |
|---|---|---|---|---|
| OpenAPI spec | REST contract | All endpoint request/response shapes | `contracts/openapi_service_photo_poc.yaml` | Complete (for `/jobs`); `/inbound` only partially reflected |
| Review payload schema | JSON Schema | `GET /jobs/{id}/review-payload` shape | `contracts/review_payload_schema.json` | Complete |
| Gemini response schema | JSON Schema | Validates Gemini output (with optional `pricing` block) | `contracts/gemini_response_schema.json` | Complete — Phase 5 updated |
| Approval rules | Spec | Rule IDs, required fields, error codes | `contracts/approval_validation_rules.md` | Complete |
| Backend workflow spec | Spec | Endpoint-by-endpoint logic + status transitions | `contracts/backend_workflow_spec.md` | Complete |
| CSV export schema | Spec | CSV columns, mapping, transforms, validation gate | `contracts/csv_export_schema.md` | Complete |

## Documentation artifacts

| Component | Type | Purpose | Key Files | Status |
|---|---|---|---|---|
| Project overview | Reference | Vision, scope, rules, layout | `docs/00_project_documentation.md` | Complete |
| Logical schema | Reference | Entity-relationship narrative | `docs/01_database_schema_architecture.md` | Complete |
| Physical schema | Reference | DDL spec for PostgreSQL | `docs/02_physical_schema_spec.md` | Complete |
| UI design | Reference | Early UI notes (stale after Phase 6G) | `docs/03_ui_design.md` | Stale |
| Initial migration notes | Reference | Migration narrative companion | `docs/04_initial_migration.md` | Complete |
| Progress tracker | Running log | Phase checklist | `docs/progress.md` | Current |
| ADR-0001 | Decision record | Draft/review layer separation | `docs/decisions/0001-draft-vs-review-layers.md` | Current |
| Phase handoff briefs | Work packages | Prompts directed at Claude Code per phase | `docs/claude_code_starter_prompt.md`, `claude_code_backend_implementation_guide.md`, `claude_code_seed_data_spec.md`, `claude_code_phase3_handoff.md`, `claude_code_phase4_e2e_handoff.md`, `claude_code_phase5_pricing_handoff.md`, `claude_code_phase7_handoff.md` | Complete (Phase 7 is the active open brief) |
| Architecture package (this audit) | Reference | System diagram + component inventory + summary | `docs/system-architecture-*.{md,mmd,svg}` | Current |
| Stakeholder handover | Packaging | Word/PDF overview, architecture PNG, demo videos | `handover/*` | Current |

## Tooling & scripts

| Component | Type | Purpose | Key Files | Status | Notes |
|---|---|---|---|---|---|
| Dev launcher | Batch script | Starts backend + frontend, opens browser | `dev.bat` | Complete | Does not kill stale processes (gotcha #7) |
| Extraction CLI | Batch + Python | Runs Gemini over `input_images/` from command line | `extract.bat`, `scripts/run_gemini_extraction.py` | Complete | Shares `inbound_extraction` service; `--purge` flag |
| Postgres reset | PowerShell | Resets local Postgres superuser password | `backend/reset_postgres_password.ps1` | Complete | Windows-only utility |
| Tests — unit | pytest | Approval validator, CSV transforms, job number generator | `backend/tests/unit/*.py` | Complete | |
| Tests — integration | pytest | Route-group coverage for DB pipeline | `backend/tests/integration/test_{jobs,images,submit,review,approval,export}.py` | Complete | Zero coverage for `/inbound` pipeline |
| Tests — E2E | pytest | Full workflow smoke | `backend/tests/test_workflow_e2e.py` | Complete | DB-pipeline E2E only |
