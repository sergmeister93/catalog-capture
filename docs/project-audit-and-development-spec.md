# Catalog Capture — Project Audit & Development Specification

> **Document type**: Technical audit and implementation narrative
> **Audience**: Technical leadership, incoming engineers, project handoff reviewers
> **Authoritative sources**: `CLAUDE.md`, `docs/progress.md`, `contracts/`, `docs/claude_code_*` handoff docs, and direct code inspection
> **Audit date**: 2026-04-21

Throughout this document, statements are labeled:
**[Evidenced]** — directly visible in the codebase or committed docs.
**[Inferred]** — a reasoned interpretation based on artifacts.
**[Uncertain]** — flagged for validation with the project owner.

---

## 1. Executive Summary

**What it is.** Catalog Capture is a proof-of-concept application that converts photographs of used items (primarily cameras) into priced, reviewed, export-ready marketplace listings. It uses Google Gemini to draft structured listing content from a single photograph, includes live market pricing via Google Search grounding, requires human approval before export, and produces a CSV for downstream marketplace tooling.

**Stage.** Proof of concept. Phases 1–6 are explicitly marked complete; Phase 7 ("productionization candidates") is open and unstarted. **[Evidenced]** in `docs/progress.md` and `CLAUDE.md`.

**Maturity assessment.**
- **Architecture**: mature for a POC — contracts-first, layered, documented.
- **Active workflow**: functional end-to-end, verified against the live Gemini API (5/5 images).
- **Dormant DB pipeline**: fully tested (47/47 pytest), preserved but currently unused by the UI.
- **Productionization gap**: significant — no auth, in-memory job state, single-host filesystem storage, single-user assumption.

**Overall**: A credible, well-scoped POC with unusually strong specification discipline for its size. The distance to production is substantial but the architectural foundations are sound.

---

## 2. Project Purpose

**Business problem.** Listing used camera equipment for resale is labor-intensive: each item requires photographing, writing a description, specifying condition and accessories, researching fair market value across multiple reseller sites (eBay, MPB, KEH, B&H), and formatting the result for a marketplace feed. Catalog Capture automates the draft, keeps the human in the loop for correction, and produces a standardized export.

**Intended users.** Store staff / reviewers at a single service-photo operation. Single-role model; no multi-tenant concerns in the current design. **[Evidenced]** — no authentication code, no role/permission model, `CLAUDE.md` explicitly lists auth as out of scope.

**Main workflow.**
1. Drop photos into `input_images/` (or drag-and-drop in the Upload screen).
2. Trigger Gemini extraction (one multimodal call per image, with Google Search grounding for pricing).
3. Review AI-drafted listings in a card UI; edit content and pricing; approve per card.
4. Bulk-export approved items to a timestamped CSV.

**Core outputs.**
- `inbound/extraction_<UTC>__<image-stem>.json` — structured AI artifacts.
- `exports/listings_<UTC>.csv` — the marketplace-ready deliverable.

---

## 3. Codebase Audit Summary

### Tech stack **[Evidenced]**
| Layer | Technology | Version |
|---|---|---|
| Backend framework | FastAPI | 0.111.0 |
| Server | Uvicorn | 0.29.0 |
| Python runtime | CPython | 3.12 (3.14 incompatible — no wheels for pinned deps) |
| Validation | Pydantic | ≥2.11 (upgraded from 2.7.1 for google-genai) |
| Settings | pydantic-settings | ≥2.2.1 |
| ORM | SQLAlchemy | 2.0.30 |
| Migrations | Alembic | 1.13.1 |
| Database driver | psycopg2-binary | 2.9.9 |
| Database | PostgreSQL | 15 (via Docker) |
| AI SDK | google-genai | ≥1.0 (replaces the older `google-generativeai`) |
| JSON validation | jsonschema | 4.22.0 |
| Frontend build | Vite | 5.4.x |
| Frontend framework | React | 18.3 + TypeScript 5.6 |
| Frontend router | custom hash router (`state/router.ts`) — no react-router |
| Frontend state | local component state + `localStorage` |
| Testing | pytest, pytest-asyncio, httpx (TestClient), pytest-cov |

### Major directories
| Path | Role |
|---|---|
| `contracts/` | OpenAPI, JSON schemas, approval rules, CSV spec, workflow spec — contracts-first artifacts |
| `docs/` | Numbered planning docs (`00_`–`04_`), phase handoff briefs, ADRs, progress tracker |
| `docs/claude_code_*.md` | Explicit handoff briefs to Claude Code for each backend phase |
| `backend/src/service_photo/` | FastAPI app; subdivides into `api/`, `core/`, `db/`, `integrations/`, `models/`, `repositories/`, `schemas/`, `services/`, `prompts/`, `utils/` |
| `backend/tests/` | Unit + integration tests, plus `test_workflow_e2e.py` |
| `frontend/src/` | React SPA — `screens/`, `api/`, `state/`, `App.tsx`, `index.css` |
| `input_images/`, `inbound/`, `exports/`, `storage/` | Runtime artifact folders (gitignored) |
| `scripts/` | CLI helpers, notably `run_gemini_extraction.py` |
| `handover/` | Stakeholder packaging — Word doc, PDF, architecture PNG, video demos |

### Deployment assumptions **[Inferred]**
- **Single-host, developer workstation.** `dev.bat` launches backend and frontend in separate `cmd` windows and opens a browser. No containerization for the app itself (only the Postgres dependency uses Docker).
- **Windows-first.** `dev.bat`, `extract.bat`, `reset_postgres_password.ps1` — all Windows-targeted.
- **No cloud deployment config** — no Dockerfile for the app, no CI, no reverse proxy config, no TLS.

### Environment / config dependencies
- `.env` at repo root (gitignored). Keys: `GEMINI_API_KEY`, `GEMINI_MODEL`, `DATABASE_URL`, `TEST_DATABASE_URL`, `USE_MOCK_GEMINI`. **[Evidenced]**
- `.env.example` committed as a template.
- `core/config.py` resolves `.env` via an absolute path (`Path(__file__).resolve().parents[4]`) to survive uvicorn's working-directory variance — a documented Phase-4 fix.

### Third-party integrations
- **Google Gemini** (`google-genai` SDK) for multimodal extraction and pricing.
- **Google Search grounding** attached to the same call via `types.Tool(google_search=...)`.
- No other external services.

### Data storage **[Evidenced]**
- **Active pipeline**: local filesystem (`input_images/`, `inbound/`, `exports/`) plus an in-memory `_jobs` dict for job tracking.
- **Dormant pipeline**: PostgreSQL, 12 tables, Alembic-managed (`001_initial_schema.py`), split into draft (AI output) and review (human-edited) layers with append-only status history.

### AI / model usage
- One grounded multimodal call per image returning both visual extraction and pricing in a single structured JSON response.
- Prompt externalized to `backend/src/service_photo/prompts/listing_extraction_v1.md`.
- Response validated against `contracts/gemini_response_schema.json`.
- Mock Gemini available via `integrations/mock_gemini.py` + `USE_MOCK_GEMINI` flag for offline development.

---

## 4. Reconstructed Build Narrative

The project is unusually well-documented. Each phase has an explicit handoff brief (`docs/claude_code_*.md`) and a progress tracker (`docs/progress.md`). The narrative below is reconstructed from those artifacts and cross-checked against the code.

### Phase 1 — Contracts & Schema Definition **[Evidenced — progress.md, CLAUDE.md]**
Contracts-first. Before any application code existed, the team wrote:
- `contracts/openapi_service_photo_poc.yaml` — full REST contract.
- `contracts/review_payload_schema.json`, `gemini_response_schema.json` — JSON Schemas.
- `contracts/approval_validation_rules.md`, `backend_workflow_spec.md`, `csv_export_schema.md`.
- `docs/00`–`docs/03` — business scope, logical schema, physical schema, UI notes.
- `docs/decisions/0001-draft-vs-review-layers.md` — first ADR.

**Evidence:** The `README.md` is frozen at "Phase 1" and still reads "Backend and frontend scaffolding are in place but not yet implemented." **[Evidenced]** This README was never revised — a minor documentation-drift issue flagged in §10.

### Phase 2 — Backend Implementation **[Evidenced]**
Implementation of the DB-backed `/jobs/*` pipeline:
- 12 SQLAlchemy models matching the physical schema.
- 5 repositories (`draft`, `exports`, `images`, `jobs`, `review`).
- 7 services (`job`, `submit`, `review`, `review_payload`, `approval`, `export`, `image`).
- 8 routes in `api/routes.py`.
- Single Alembic migration `001_initial_schema.py`.
- Integration tests per route group + unit tests for validators and CSV transforms.
- Gemini integration with real + mock implementations behind a common `gemini_interface` protocol.

Four non-obvious bugs were fixed during verification and documented in `CLAUDE.md` (forward-ref timing, error response shape, Decimal→JSONB serialization, test fixture transaction ownership). The fact that these are called out explicitly suggests a rigorous verification pass.

**Handoff evidence:** `docs/claude_code_backend_implementation_guide.md`, `docs/claude_code_starter_prompt.md`, `docs/claude_code_seed_data_spec.md` — briefs directed at Claude Code for this phase.

### Phase 3 — Frontend Review Shell (paused) **[Evidenced]**
The original plan was a multi-image-per-job review UI backed by `/jobs/*`. A pivot happened mid-phase:

> "Mid-Phase-3, the workflow shifted from 'one job = one item, multiple photos' to 'one image = one product listing'." — `CLAUDE.md`

**Evidence in code:** Dormant screens (`PrepScreen.tsx`, `BatchesScreen.tsx`) exist alongside the active `InboundScreen.tsx`. The `/jobs/*` routes remain mounted but unused by the UI. The hash router points to `#/inbound` by default.

### Phase 3.5 — Per-image Inbound Flow **[Evidenced]**
A parallel pipeline introduced to avoid disturbing the verified DB stack:
- `api/inbound_routes.py` (943 LOC).
- `services/inbound_extraction.py` (338 LOC) — shared between the HTTP route and the CLI script.
- Filesystem artifacts in `inbound/`.
- In-memory `_jobs` dict for progress polling.

### Phase 4 — End-to-End Validation **[Evidenced]**
`test_workflow_e2e.py` plus a `.env` path-resolution fix (`core/config.py` switched from relative to absolute path). Verified UI-triggered extraction end-to-end.

### Phase 5 — Pricing / Web Enrichment (single-pass) **[Evidenced]**
The most architecturally significant post-Phase-2 change:
- Migrated SDK from `google-generativeai` to `google-genai` (native Google Search grounding on Gemini 2.x).
- Combined extraction + pricing into a single grounded call (rather than a two-pass design).
- Added 9 pricing columns to the CSV.
- Verified end-to-end against the live API (5/5 images).

Documented in `docs/claude_code_phase5_pricing_handoff.md`.

### Phase 6 — UX Rebrand & Polish **[Evidenced]**
Ran in sub-phases 6A–6G:
- **6A**: cross-screen handoff + localStorage persistence (key `service-photo:inbound-review-state-v2`).
- **6B**: layout density.
- **6C**: visual polish.
- **6D**: React StrictMode polling fix (documented gotcha #8 in `CLAUDE.md`).
- **6E**: drag-and-drop upload via `POST /inbound/input-images`.
- **6F**: terminology rename (display only — internal `/inbound` route and directory unchanged).
- **6G**: enterprise design tokens, Inter + Manrope fonts, humanization helpers for vendor/system strings.

### Phase 7 — Open **[Evidenced]**
`docs/claude_code_phase7_handoff.md` enumerates candidates: SQLite promotion of `_jobs`, marketplace posting integrations, per-field confidence scoring, multi-reviewer queues, self-hosting Inter/Manrope. No Phase 7 work has been started.

### Observed development style **[Inferred]**
- **Specification-first.** Contracts and docs precede code. The `docs/claude_code_*` handoff briefs read like work-package prompts — a structured way to delegate implementation to an AI pair programmer.
- **Preserve-and-parallel on pivots.** When the domain model shifted mid-Phase-3, the team did not tear out the DB pipeline; they built a second pipeline alongside and marked the first dormant. This is a conservative, risk-averse pattern.
- **Documented gotchas.** `CLAUDE.md` lists 13 specific bugs with "do not reintroduce" guidance — the project actively invests in institutional memory.

---

## 5. Claude Code Contribution Interpretation

This is interpretive — framed as evidence-backed inference rather than certainty. The project explicitly names Claude Code as the intended implementer (see `docs/claude_code_*` handoff briefs), so attribution is better-supported here than in most codebases.

### Strongly evidenced — likely Claude-Code-assisted
- **Layered backend scaffold.** The textbook separation (route → service → repository → model → schema) with one-file-per-entity and comprehensive `__init__.py` exports is the kind of structurally clean, documentation-heavy scaffold AI pair programmers produce reliably.
- **Pydantic schemas + SQLAlchemy models.** 12 ORM models + parallel Pydantic schemas with matching docstrings — a repetitive task well-suited to AI generation from a specification document.
- **Test suites per route group.** Six integration test files (`test_approval.py`, `test_export.py`, `test_images.py`, `test_jobs.py`, `test_review.py`, `test_submit.py`) plus three unit tests — consistent structure, aligned with the route/service split.
- **Alembic migration from spec.** `001_initial_schema.py` almost certainly generated from `docs/02_physical_schema_spec.md` and `docs/04_initial_migration.md`.
- **OpenAPI and JSON Schema drafting.** The contracts are consistent in tone, structured thoroughly, and reference the same vocabulary as the code — a hallmark of AI-assisted spec drafting.
- **Gemini prompt engineering.** `backend/src/service_photo/prompts/listing_extraction_v1.md` + the structured JSON response contract — AI-assisted prompt + schema co-design.

### Moderately evidenced — plausibly Claude-Code-assisted
- **Frontend InboundScreen (1,301 LOC).** The file concentrates Upload, Review, and Batch History into a single screen with numerous humanization helpers. The scale and cohesion suggest AI iterative assembly, though the god-component structure also suggests it was *not* refactored afterward.
- **SDK migration glue (Phase 5).** `real_gemini.py` rewrite from `google-generativeai` to `google-genai` is documented as a deliberate phase with its own handoff brief.
- **Design-token overhaul (Phase 6G).** The enterprise polish pass — type/spacing/radius/shadow scales, font wiring, humanization helpers — is the kind of targeted, repetitive styling work AI tools accelerate well.

### Likely human-led (direction, not generation)
- **Architectural decisions.** The draft-vs-review layer split, the decision to preserve the DB pipeline on pivot, the single-pass grounding strategy — these read as human architectural calls captured in ADRs and handoff briefs.
- **Domain modeling.** The 12-table schema and the approval-gate rule set are specific, deliberate, and grounded in the business problem.
- **Phase structuring and work-package framing.** The discipline of writing a `claude_code_*_handoff.md` before each phase is a human workflow choice.

### Not attributable
Exact line-by-line authorship cannot be determined from the artifacts. There is no git history (project is not a git repository per the environment info).

---

## 6. Functional Breakdown

| Capability | User Goal | Key Files | Inputs | Outputs | Dependencies | Status |
|---|---|---|---|---|---|---|
| Photo upload | Add a photo to the batch | `frontend/.../InboundScreen.tsx`, `api/inbound_routes.py::POST /inbound/input-images` | Multipart file | File in `input_images/` | Filesystem | **Complete** |
| Batch extraction | Run Gemini over all photos | `api/inbound_routes.py::POST /inbound/extract`, `services/inbound_extraction.py`, `integrations/real_gemini.py` | Folder contents, optional `batch_name` | Per-image JSON + in-memory job state | `google-genai`, `GEMINI_API_KEY` | **Complete** |
| Progress polling | See live extraction status | `GET /inbound/extract/{job_id}` | `job_id` | Status, completed count, current image | In-memory `_jobs` | **Complete** |
| Artifact listing | See all prior extractions | `GET /inbound` | — | JSON array of artifacts | `inbound/` | **Complete** |
| Batch grouping | Browse past runs | `GET /inbound/batches`, `BatchesScreen.tsx` | — | Grouped by `(batch_name, started_at)` | `inbound/` metadata | **Complete** |
| Review editing | Correct AI output | `InboundScreen.tsx` (Review view) | Artifact JSON | Edited state in `localStorage` | Browser | **Complete** |
| Per-card approval | Mark listing ready | `InboundScreen.tsx` | — | Boolean approval state (client-side) | `localStorage` | **Complete** |
| Bulk export | Produce marketplace CSV | `POST /inbound/export`, `services/export_service.py` | All approved cards | `exports/listings_<UTC>.csv` | Filesystem, CSV spec | **Complete** |
| Image serving | Render photos in UI | `GET /inbound/images/{filename}` | Filename | Image bytes | `input_images/` | **Complete** (path-traversal defended) |
| Mock mode | Offline dev | `integrations/mock_gemini.py`, `USE_MOCK_GEMINI` flag | — | Fake response | — | **Complete** |
| CLI extraction | Power-user alternative | `scripts/run_gemini_extraction.py`, `extract.bat` | `--purge` flag | Same artifacts as UI path | Shared service | **Complete** |
| DB-backed job lifecycle | *(dormant)* full workflow | `api/routes.py` + service layer + 12 models | — | — | PostgreSQL | **Dormant** — code complete, not wired to UI |
| Authentication | Identify reviewers | — | — | — | — | **Not started** (out of scope) |
| Marketplace posting | Auto-list on eBay/etc. | — | — | — | — | **Not started** (out of scope) |
| Confidence scoring | Flag low-confidence fields | — | — | — | — | **Not started** (Phase 7 candidate) |

---

## 7. Data Flow and Processing Flow

**1. Ingress.**
- UI path: reviewer drags photos onto the Upload screen → `POST /inbound/input-images` (multipart; 25 MB/file cap, extension allowlist, safe-basename renaming on collision) → bytes written to `input_images/`.
- Manual path: reviewer drops files directly into `input_images/` on disk.

**2. Extraction trigger.**
- UI button or `extract.bat` → `POST /inbound/extract` (optionally with `{batch_name}`) → the route generates a `job_id`, creates an entry in the in-memory `_jobs` dict, and spawns a daemon thread running `inbound_extraction.run_extraction`.
- `inbound/` is purged before each run to avoid mixing batches.

**3. Per-image AI call.**
- The service iterates files in `input_images/`.
- For each image, it calls `real_gemini.extract_listing` which:
  - Loads the prompt from `prompts/listing_extraction_v1.md`.
  - Attaches the image as `types.Part.from_bytes(...)`.
  - Attaches the Google Search grounding tool.
  - Calls `client.models.generate_content(...)`.
  - Parses the response as structured JSON.
- The response is validated against `contracts/gemini_response_schema.json`.
- The artifact is written to `inbound/extraction_<UTC>__<stem>.json`.
- `on_image_done` callback updates the in-memory job state; UI polls `GET /inbound/extract/{job_id}`.

**4. Human review.**
- Reviewer navigates to the Review screen.
- `GET /inbound` returns all artifacts; the screen renders one card per artifact.
- Fields are editable inline; changes write to `localStorage` under key `service-photo:inbound-review-state-v2`.
- Vendor/system strings are routed through humanization helpers (`humanizeModelName`, `humanizePricingTag`, `humanizeWarning`, `formatFetchedAt`) before display.
- Per-card approval is a client-side toggle.

**5. Export.**
- Reviewer clicks "Export Approved Items" → bulk-approves any remaining cards → `POST /inbound/export`.
- `export_service` reads approved artifacts, flattens per `contracts/csv_export_schema.md`, writes `exports/listings_<UTC>.csv` (includes 9 pricing columns and sources JSON).
- Reviewer downloads the CSV for downstream marketplace tooling.

**6. Dormant DB path (not executed in the active flow).**
`POST /jobs` → `POST /jobs/{id}/images` → `POST /jobs/{id}/submit` → status transitions through `submitted_to_ai → ai_response_received → ready_for_review → under_review → approved → exported`, with every transition appended to `listing_job_status_history`. The draft and review layers remain separate until export; export reads the review layer only.

---

## 8. Component Build Inventory

See [`component-build-inventory.md`](component-build-inventory.md) for the structured table.

Summary by layer:
- **Frontend**: 3 screens (`InboundScreen`, `PrepScreen`, `BatchesScreen`), 1 API client, 2 state modules, custom hash router.
- **Backend — active**: 1 route module (`inbound_routes.py`), 2 services (`inbound_extraction`, `export_service`), 1 integration module (`real_gemini.py` + `mock_gemini.py` + `gemini_interface.py`).
- **Backend — dormant**: 1 route module (`routes.py`), 6 services, 5 repositories, 12 models, 6 schema modules.
- **Contracts**: 6 artifacts.
- **Docs**: 4 numbered planning docs, 8 phase handoff briefs, 1 ADR, 1 progress tracker.
- **Tooling**: 2 Windows batch launchers, 1 CLI script, 1 PowerShell utility.

---

## 9. Architectural Decisions and Patterns

### Notable patterns
- **Contracts-first.** OpenAPI spec, JSON Schemas, and validation rules were authored before implementation. This is rare at POC scale and pays off visibly — the Gemini response, CSV export, and HTTP surface are all pinned to a single source of truth.
- **Draft/review layer separation (ADR-0001).** `listing_draft_*` tables are read-only AI output; `listing_review_*` tables are human-edited and the source of truth for approval and export. Enforced by repository code.
- **Append-only status history.** Every status transition writes a new row; old rows are never updated.
- **Approval collects all failures.** The approval service does not short-circuit on the first rule failure — reviewers see every issue at once.
- **Externalized prompts.** Prompt lives in a markdown file (`prompts/listing_extraction_v1.md`), versioned in-filename. Easy to iterate without code churn.
- **Integration abstraction.** `gemini_interface.py` declares the protocol; `real_gemini.py` and `mock_gemini.py` are interchangeable behind a `USE_MOCK_GEMINI` flag.
- **Shared service for CLI and HTTP.** `inbound_extraction.py` is called both by the route and by `scripts/run_gemini_extraction.py` — no duplication.
- **Preserve-and-parallel pivot.** When the domain model shifted, the DB pipeline was left intact and a second filesystem pipeline was built alongside — trading some short-term duplication for much lower regression risk.
- **Progress callbacks.** `on_image_start` / `on_image_done` allow the UI to poll without the service layer knowing about HTTP.

### Weak patterns / visible debt
- **`InboundScreen.tsx` is a god component (1,301 LOC).** Upload, Review, and Batch History views all live in one file with co-located helpers. Candidate for decomposition. **[Evidenced]**
- **`inbound_routes.py` is large (943 LOC).** Mixes routing, job tracking, file handling, and orchestration in one module.
- **In-memory job state.** `_jobs` is a module-level dict; it is lost on backend restart and would not survive multi-worker deployment.
- **No async for Gemini calls.** The daemon-thread + in-memory-dict pattern is simple but does not leverage FastAPI's async model. For POC scale this is adequate.
- **No test coverage for the active `/inbound` pipeline.** The 47/47 passing tests all target the *dormant* DB pipeline. The active user-facing workflow has no automated tests. **[Evidenced]** — `backend/tests/integration/` mirrors `/jobs/*` routes only.
- **README drift.** `README.md` still says "Phase 1" and "Backend and frontend scaffolding are in place but not yet implemented." Six phases later, this is inaccurate.
- **Two places describe architecture tokens.** `docs/03_ui_design.md` is noted stale (per gotcha #10); the source of truth is now `frontend/src/index.css`.

---

## 10. Known Gaps, Risks, and Ambiguities

See [`open-issues-and-risks.md`](open-issues-and-risks.md) for a categorized list. High-level:

**Confirmed issues** **[Evidenced in code or CLAUDE.md]**
- In-memory `_jobs` dict loses all in-flight state on backend restart.
- README.md is out of date (stuck at Phase 1).
- Active `/inbound` pipeline has no automated test coverage.
- `dev.bat` does not kill prior uvicorn/Vite processes; repeat launches stack duplicate listeners (documented as gotcha #7).
- `docs/03_ui_design.md` is stale after Phase 6G — CSS tokens changed but doc was not updated.
- `/inbound` pipeline is single-user — concurrent reviewers will race on shared folders.
- No authentication; anyone who can reach the backend can export.

**Probable issues** **[Inferred]**
- Pricing accuracy depends entirely on Gemini's grounded search — no independent verification, no confidence score persisted.
- The "Export Approved Items" button bulk-approves any not-yet-approved cards (per gotcha #13), which could surprise reviewers expecting a strict approved-only filter.
- Frontend god-component will slow future feature work and complicate testing.
- No rate limiting on `/inbound/extract` — a reviewer can flood Gemini quota.
- No logging framework — only `print` statements; no structured logs for debugging live issues.

**Unknowns requiring validation** **[Uncertain]**
- Whether the dormant DB pipeline code still compiles against current Pydantic ≥2.11 after the Phase 5 SDK migration (47/47 were passing before the upgrade; re-verification not documented).
- Backup/retention policy for `exports/` and `inbound/` — currently all runtime folders are local filesystem only.
- Whether the CSV column contract is aligned with the actual target marketplace's import spec, or if this is assumed.
- Whether multi-user handoff will ever be needed (changes the SQLite-promotion vs full-Postgres-promotion decision).

---

## 11. Production Readiness Assessment

See [`production-readiness-assessment.md`](production-readiness-assessment.md) for the full scorecard. Summary:

| Category | Status |
|---|---|
| Architecture | **Partially Ready** — sound patterns, but single-host assumption |
| Code quality | **Partially Ready** — clean structure, god components in two places |
| Error handling | **Partially Ready** — custom exception handler, but limited in `/inbound` |
| Observability | **Not Ready** — no structured logging, no metrics, no tracing |
| Security | **Not Ready** — no auth, no secret rotation, no rate limiting |
| Configuration | **Partially Ready** — `.env` with absolute-path loader, no secret manager |
| Test coverage | **Partially Ready** — strong for dormant pipeline, zero for active pipeline |
| Resilience | **Not Ready** — in-memory job state, no retry, no backoff for Gemini |
| Deployment | **Not Ready** — no Dockerfile for app, no CI, Windows-only launchers |
| Workflow completeness | **Ready** — happy path works end-to-end, verified live |

---

## 12. Recommended Next Steps

Prioritized for productionization. Items in **bold** are prerequisites for any multi-user or production deployment.

1. **Promote `_jobs` to SQLite (or PostgreSQL).** The most-cited risk in `CLAUDE.md` and `phase7_handoff.md`. Low effort, high resilience payoff.
2. **Add integration tests for the `/inbound` pipeline.** Currently zero coverage for the active user workflow.
3. **Add authentication.** Even a single shared credential behind the UI closes the biggest security gap.
4. **Structured logging.** Replace `print` with a standard logger; emit one JSON line per extraction, export, and error.
5. **Refactor `InboundScreen.tsx`.** Decompose Upload / Review / Batches into separate modules with shared state. Tests become possible after this.
6. **Update `README.md`.** It still says Phase 1; this is the first thing an inheriting engineer will read.
7. **Rate-limit `/inbound/extract`.** Protect Gemini quota and prevent accidental runaway costs.
8. **Add error-retry for Gemini.** Handle transient 5xx + 429 with exponential backoff; current flow fails the single image and continues.
9. **Persist per-field confidence scores.** Gemini already returns uncertainty tags; surface them in the UI and the CSV.
10. **Deployment artifact.** Minimal Dockerfile + Compose for app + Postgres; document how to run on Linux.
11. **Harden `dev.bat`.** Kill prior uvicorn/Vite processes before relaunching (gotcha #7).
12. **Align CSV schema with target marketplace.** Confirm the column contract matches the real import spec.
13. **Multi-reviewer queue design.** Required if more than one person will ever review simultaneously.
14. **Self-host fonts.** Drop the Google Fonts CDN dependency for air-gapped deploys.
15. **Refresh `docs/03_ui_design.md`** to match `index.css` as the current source of truth.

---

## 13. Developer Handoff Notes

See [`developer-handoff.md`](developer-handoff.md) for the complete handoff brief. Highlights:

- **Read first**: `CLAUDE.md` (the primary orientation doc — it is more current than `README.md`), then `docs/claude_code_phase7_handoff.md` for what's open next.
- **Start here**: boot `dev.bat`, drop a photo into `input_images/`, click "Run Gemini Extraction," follow the flow to CSV. Understand the happy path before reading code.
- **Most important modules**:
  - `backend/src/service_photo/services/inbound_extraction.py` — the orchestration core.
  - `backend/src/service_photo/integrations/real_gemini.py` — the one AI call that defines the product.
  - `contracts/gemini_response_schema.json` + `contracts/csv_export_schema.md` — the two contracts any change will have to respect.
  - `frontend/src/screens/InboundScreen.tsx` — the entire user-facing UI (refactor target).
- **Risky areas**:
  - Anything that touches `_jobs` in-memory state.
  - The StrictMode + localStorage handoff pattern (gotcha #8).
  - The `.env` absolute-path resolution in `core/config.py` (gotcha #5) — do not switch it back to a relative path.
  - SDK choice: do not reinstall `google-generativeai` (gotcha #6).
- **Assumptions to validate first**:
  - Does the CSV still match what the target marketplace expects?
  - Is multi-reviewer access a near-term requirement?
  - Is the Gemini spend within acceptable bounds for the intended volume?

---

*End of audit.*
