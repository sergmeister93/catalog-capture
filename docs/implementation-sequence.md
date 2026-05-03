# Implementation Sequence

A concise, chronological reconstruction of how Catalog Capture was built. Based on `docs/progress.md`, `CLAUDE.md`, the `docs/claude_code_*` handoff briefs, and code inspection. Phase boundaries are directly evidenced; intra-phase ordering is inferred where not explicit.

---

### Phase 1 — Contracts & Scaffolding
**Likely goal:** Define the system on paper before writing code. Lock the API surface, data model, and validation rules so implementation becomes mechanical.
**Evidence:** `docs/00_–03_*`, ADR-0001, and every file in `contracts/` predate the backend implementation.
**Files involved:**
- `contracts/openapi_service_photo_poc.yaml`
- `contracts/review_payload_schema.json`
- `contracts/gemini_response_schema.json`
- `contracts/approval_validation_rules.md`
- `contracts/backend_workflow_spec.md`
- `contracts/csv_export_schema.md`
- `docs/00_project_documentation.md` → `docs/04_initial_migration.md`
- `docs/decisions/0001-draft-vs-review-layers.md`
- Root `README.md`, `.gitignore`, `.env.example`

**Outcome:** A fully specified, unimplemented system. README reflects this state (and is now stale — it was never updated past this point).

---

### Phase 2 — Backend Implementation (DB-backed pipeline)
**Likely goal:** Stand up FastAPI + PostgreSQL, implement all eight `/jobs/*` routes against the contract, and verify with tests.
**Evidence:** `docs/claude_code_backend_implementation_guide.md`, `docs/claude_code_starter_prompt.md`, and `docs/claude_code_seed_data_spec.md` are explicit work packages for this phase. The code structure (`models/`, `repositories/`, `schemas/`, `services/`, `api/routes.py`) matches the guide. `CLAUDE.md` records 47/47 tests passing at the end of verification.
**Files involved:**
- `backend/pyproject.toml` (FastAPI, SQLAlchemy, Alembic, pydantic, psycopg2, google-generativeai — later migrated)
- `backend/src/service_photo/models/*.py` (12 ORM models)
- `backend/src/service_photo/repositories/*.py` (5 repositories)
- `backend/src/service_photo/schemas/*.py` (draft, review, jobs, export, errors)
- `backend/src/service_photo/services/*.py` (job, submit, review, review_payload, approval, export, image)
- `backend/src/service_photo/api/routes.py`
- `backend/src/service_photo/db/migrations/versions/001_initial_schema.py`
- `backend/src/service_photo/integrations/gemini_interface.py`, `mock_gemini.py`, `real_gemini.py`
- `backend/tests/unit/*.py`, `backend/tests/integration/*.py`, `backend/tests/test_workflow_e2e.py`

**Four documented bugs surfaced and were fixed** (forward-ref timing, error response shape, Decimal→JSONB, test fixture transaction).

**Outcome:** Fully working DB-backed pipeline, verified end-to-end in tests but not yet wired to a UI.

---

### Phase 3 — Frontend Review Shell (paused)
**Likely goal:** Build a React SPA consuming `/jobs/*` for the multi-image-per-job review workflow described in the original spec.
**Evidence:** `docs/claude_code_phase3_handoff.md`; dormant `PrepScreen.tsx` and `BatchesScreen.tsx` remain in the repo.
**Outcome:** Paused mid-phase after the domain model pivoted from "one job = many photos" to "one image = one listing."

---

### Phase 3.5 — Per-Image Inbound Pipeline (pivot)
**Likely goal:** Build a parallel filesystem-backed pipeline that matches the new domain model without disturbing the verified DB pipeline.
**Evidence:** `CLAUDE.md` explicitly documents the pivot and the decision to parallel-track rather than rewrite.
**Files involved:**
- `backend/src/service_photo/api/inbound_routes.py`
- `backend/src/service_photo/services/inbound_extraction.py`
- `scripts/run_gemini_extraction.py`, `extract.bat`
- `input_images/`, `inbound/`, `exports/` directories

**Outcome:** Working parallel pipeline backed by the filesystem with an in-memory job tracker.

---

### Phase 4 — End-to-End Validation
**Likely goal:** Verify UI-triggered extraction against a live Gemini API.
**Evidence:** `docs/claude_code_phase4_e2e_handoff.md`; `CLAUDE.md` documents the `.env` absolute-path fix discovered during this phase.
**Files involved:**
- `backend/src/service_photo/core/config.py` (switched from relative to absolute `.env` path)
- Initial `InboundScreen.tsx` wiring

**Outcome:** UI-triggered extraction + E2E smoke both pass against real Gemini.

---

### Phase 5 — Pricing via Google Search Grounding (SDK migration)
**Likely goal:** Add live market pricing to each extraction in a single Gemini call.
**Evidence:** `docs/claude_code_phase5_pricing_handoff.md`; `CLAUDE.md` gotcha #6 documents the migration from `google-generativeai` to `google-genai`. Verified 5/5 images live.
**Files involved:**
- `backend/pyproject.toml` — SDK swap, pydantic upgrade
- `backend/src/service_photo/integrations/real_gemini.py` — full rewrite on new SDK
- `contracts/gemini_response_schema.json` — `pricing` block added as optional top-level property
- `contracts/csv_export_schema.md` — 9 pricing columns appended
- `backend/src/service_photo/services/export_service.py` — pricing flattener

**Outcome:** Single-pass extraction + pricing with Google Search grounding in production-like conditions.

---

### Phase 6 — UX Rebrand & Enterprise Polish
**Likely goal:** Promote the POC from "working" to "presentable" for stakeholders. Ran in seven sub-phases (6A–6G).
**Evidence:** `CLAUDE.md` Phase 6 summary; the multi-pass structure is explicit.
**Files involved:**
- `frontend/src/screens/InboundScreen.tsx` (grew significantly across sub-phases)
- `frontend/src/state/extractionHandoff.ts` — cross-screen handoff (6A)
- `frontend/src/index.css` — design tokens (6G)
- `api/inbound_routes.py` — `POST /inbound/input-images` (6E), `GET /inbound/batches` (6A)

**Sub-phases:**
- 6A: flow + persistence (`localStorage` keyed `service-photo:inbound-review-state-v2`).
- 6B: layout density.
- 6C: visual polish.
- 6D: React StrictMode polling fix (gotcha #8).
- 6E: drag-and-drop upload.
- 6F: terminology rename (display only; internal routes unchanged).
- 6G: enterprise design tokens, Inter + Manrope fonts, humanization helpers.

**Outcome:** App rebranded to "Catalog Capture"; reviewer-facing copy stripped of raw vendor/system strings; presentation-ready.

---

### Phase 7 — Open (candidates)
**Likely goal:** Productionization. Not started.
**Evidence:** `docs/claude_code_phase7_handoff.md` lists candidate directions.
**Candidates:**
- Promote in-memory `_jobs` to SQLite or PostgreSQL.
- Marketplace posting integrations.
- Per-field confidence scoring.
- Multi-reviewer queues.
- Self-host Inter/Manrope fonts.

**Outcome:** Awaiting direction from project owner.

---

### Cross-phase pattern
Every phase follows the same shape:
1. A handoff brief is written (`docs/claude_code_*.md`) describing intent and constraints.
2. Claude Code implements against the brief.
3. Verification surfaces specific bugs, which are captured as "do not reintroduce" items in `CLAUDE.md`.
4. `docs/progress.md` is updated.

This is a disciplined, AI-assisted development workflow. The handoff briefs double as both work packages and post-hoc documentation.
