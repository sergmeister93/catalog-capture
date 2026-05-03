# Component Inventory

Each box in the architecture diagram, with its role and where it lives in the codebase.

## User
| Component | Role |
|---|---|
| **Reviewer** | Operator who supplies photos, edits AI drafts, approves, and exports. Single role; no auth in POC. |

## User Interface Layer — `frontend/`
Vite · React · TypeScript SPA, hash-routed.

| Component | Role | Source |
|---|---|---|
| **Upload screen** | Drag-and-drop photos into `input_images/`. Triggers extraction. Shows live progress banner. | `frontend/src/screens/InboundScreen.tsx` |
| **Review screen** | Card grid of extracted items. Per-field editing, pricing review, per-card approval toggle. Edits cached in `localStorage` under key `service-photo:inbound-review-state-v2`. | `frontend/src/screens/InboundScreen.tsx` |
| **Batch History** | Lists prior extraction runs grouped by batch name and start time. | `frontend/src/screens/InboundScreen.tsx` + `GET /inbound/batches` |
| **API client** | Thin fetch wrapper for all `/api/v1/inbound/*` calls. | `frontend/src/api/inbound.ts` |

## Application / Orchestration Layer — `backend/src/service_photo/`
FastAPI on Python 3.12, launched via Uvicorn.

| Component | Role | Source |
|---|---|---|
| **REST API** | Eight `/api/v1/inbound/*` endpoints: list artifacts, upload & list input images, serve images, list batches, start + poll extraction, export CSV. | `api/inbound_routes.py` |
| **Extraction Orchestrator** | Scans `input_images/`, calls Gemini per image, validates response against schema, writes artifacts. Exposes `on_image_start` / `on_image_done` callbacks for progress reporting. | `services/inbound_extraction.py` |
| **Gemini Integration** | `google-genai` client wrapper. Builds the multimodal prompt, attaches the Google Search grounding tool, parses the structured response. | `integrations/real_gemini.py` |
| **Job Tracker** | In-memory `_jobs` dict keyed by UUID. Runs extraction in a daemon thread so the HTTP request returns immediately. State is lost on restart; completed artifacts on disk remain authoritative. | `api/inbound_routes.py` |
| **CSV Exporter** | Reads approved artifacts from `inbound/`, flattens them into the CSV column contract (base fields + 9 pricing columns), writes timestamped file to `exports/`. | `services/export_service.py` |
| **Config loader** | Loads `.env` via an absolute path so the working directory doesn't matter. | `core/config.py` |
| **Contracts** | OpenAPI spec, Gemini JSON schema, CSV export spec — the validated shared vocabulary between AI, backend, and frontend. | `contracts/` |

## AI Processing Layer — external
| Component | Role |
|---|---|
| **Google Gemini 2.x** | Multimodal model. Accepts photo + structured prompt; returns JSON containing visual extraction **and** pricing in a single pass. |
| **Google Search Grounding** | `types.Tool(google_search=...)` attached to the same generate-content call. Lets Gemini pull live pricing comps from eBay, MPB, KEH, B&H and cite sources. |

## Data / Storage Layer — local filesystem
No database is used by the active pipeline.

| Component | Role |
|---|---|
| **`input_images/`** | Raw photos (one photo = one listing). Populated by upload or manual drop. |
| **`inbound/`** | Per-image extraction artifacts: `extraction_<UTC>__<image-stem>.json`. Source of truth for the Review screen. Gitignored. |
| **`exports/`** | Timestamped CSVs: `listings_<UTC>.csv`. The deliverable consumed by downstream marketplace tooling. Gitignored. |

## Dormant DB Pipeline — retained, currently unused
Preserved intact from Phase 2; verified with 47/47 pytest passing.

| Component | Role | Source |
|---|---|---|
| **`/jobs/*` endpoints (8)** | Full DB-backed lifecycle: create job → register images → submit to AI → review-payload → save review → approve → export. | `api/routes.py` |
| **Service layer** | Job, submit, review, review-payload, approval, export, image services. | `services/*.py` |
| **PostgreSQL schema** | 12 tables split into **draft** (AI output, read-only) and **review** (human-edited, source of truth for approval and export) layers, plus append-only status history. | `models/` · Alembic migrations |

The dormant pipeline represents the promotion path when the POC graduates to a durable multi-user system.

## Supporting tooling
| Component | Role | Source |
|---|---|---|
| **`dev.bat`** | One-click launcher: starts backend + frontend, opens the browser. |
| **`extract.bat` / `scripts/run_gemini_extraction.py`** | Power-user CLI alternative to the UI's extraction button. Delegates to the same `inbound_extraction` service. |
