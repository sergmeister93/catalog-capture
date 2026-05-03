# Catalog Capture

AI-assisted listing workflow for used camera equipment. Reviewer drops photos → Gemini drafts structured listings and live market pricing → reviewer edits and approves → CSV export for marketplace tooling.

> **Primary orientation doc:** [`CLAUDE.md`](CLAUDE.md) (more current than this file for day-to-day detail).
> **System overview for newcomers:** [`docs/system-overview.md`](docs/system-overview.md).

---

## Status

**Phases 1–6 complete** (2026-04-19). **Phase 7 open** — candidates tracked in [`docs/claude_code_phase7_handoff.md`](docs/claude_code_phase7_handoff.md).

| Phase | Outcome |
|---|---|
| 1 — Contracts & schema | OpenAPI, JSON Schemas, approval rules, CSV + workflow specs authored before code |
| 2 — Backend (DB pipeline) | FastAPI + PostgreSQL stack with 12 tables, 8 routes, 47/47 tests passing |
| 3 → 3.5 — Frontend pivot | Moved from "one job = many photos" to "one image = one listing"; built parallel filesystem pipeline |
| 4 — E2E validation | UI-triggered extraction verified live against Gemini |
| 5 — Pricing via grounding | Single-pass extraction + pricing, SDK migrated to `google-genai` |
| 6 — UX rebrand & polish | Catalog Capture brand; enterprise design tokens; drag-and-drop upload |

Current state of every phase: [`docs/progress.md`](docs/progress.md).

---

## Quickstart

**Prerequisites:** Python 3.12 (not 3.14 — pinned deps have no wheels for it), Node 18+, Docker (for PostgreSQL, only if using the dormant DB pipeline), a `.env` file at repo root with `GEMINI_API_KEY`.

```bash
# One-click launch (Windows)
dev.bat
# Opens backend on :8000, frontend on :5173, browser at #/inbound
```

Then:

1. Drag photos into the **Upload** screen (or drop them into `input_images/`).
2. Click **Start Analysis** — extraction runs per-image with Google Search grounding for pricing.
3. Review each card on the **Review** screen; edit and approve.
4. Click **Export Approved Items** → CSV lands in `exports/listings_<UTC>.csv`.

Full reproducible stack setup (Python, Postgres, tests): see the **Phase 2 verified stack** section of [`CLAUDE.md`](CLAUDE.md).

---

## Architecture at a glance

- **Frontend** — React 18 + Vite + TypeScript. Three screens (Upload / Review / Batch History) live in `frontend/src/screens/InboundScreen.tsx`. Custom hash router, localStorage-backed edit state.
- **Backend** — FastAPI (Python 3.12). Active path is filesystem-backed (`/api/v1/inbound/*`) with an in-memory job tracker. A dormant PostgreSQL-backed pipeline (`/jobs/*`, 12 tables, 47/47 tests) is retained for future promotion.
- **AI** — Google Gemini 2.x via `google-genai` SDK; single multimodal call per image with `types.Tool(google_search=...)` attached for live pricing comps.
- **Storage** — local filesystem: `input_images/` (raw), `inbound/` (per-image JSON artifacts), `exports/` (CSVs). All gitignored.

Presentation-ready diagram: [`docs/system-architecture-diagram.svg`](docs/system-architecture-diagram.svg).

---

## Repository layout

```
UsedItemsListing_App/
├── CLAUDE.md              Primary orientation + gotchas (read first)
├── contracts/             OpenAPI spec, JSON Schemas, approval & CSV specs
├── docs/                  Planning, ADRs, phase handoffs, audit, architecture
├── backend/               FastAPI service (src/service_photo/ package)
│   ├── src/service_photo/
│   │   ├── api/           inbound_routes.py (active) + routes.py (dormant)
│   │   ├── services/      inbound_extraction, export_service, + DB services
│   │   ├── integrations/  real_gemini, mock_gemini, gemini_interface
│   │   ├── models/        12 SQLAlchemy ORM models (dormant)
│   │   ├── schemas/       Pydantic request/response shapes
│   │   ├── repositories/  Data-access layer (dormant)
│   │   ├── prompts/       listing_extraction_v1.md
│   │   ├── core/          config.py — .env loader with abs path
│   │   └── db/            Alembic migrations
│   └── tests/             unit + integration + E2E (DB pipeline only)
├── frontend/              React SPA (src/screens/, src/api/, src/state/)
├── input_images/          Drop photos here (gitignored)
├── inbound/               Extraction artifacts (gitignored)
├── exports/               Output CSVs (gitignored)
├── scripts/               run_gemini_extraction.py (CLI alternative)
├── handover/              Stakeholder packaging: docx, pdf, architecture PNG
├── dev.bat, extract.bat   Windows launchers
└── .env                   Gitignored — GEMINI_API_KEY + config
```

---

## Documentation map

**Start here**
- [`CLAUDE.md`](CLAUDE.md) — Current state, phase summaries, 13 documented gotchas
- [`docs/system-overview.md`](docs/system-overview.md) — One-page orientation

**Architecture**
- [`docs/system-architecture-summary.md`](docs/system-architecture-summary.md) — Written explanation
- [`docs/system-architecture-diagram.svg`](docs/system-architecture-diagram.svg) — Presentation-ready diagram
- [`docs/system-architecture-components.md`](docs/system-architecture-components.md) — Box-by-box inventory

**Audit & handoff**
- [`docs/project-audit-and-development-spec.md`](docs/project-audit-and-development-spec.md) — Full technical audit
- [`docs/component-build-inventory.md`](docs/component-build-inventory.md) — Per-component table
- [`docs/implementation-sequence.md`](docs/implementation-sequence.md) — Phase-by-phase build story
- [`docs/open-issues-and-risks.md`](docs/open-issues-and-risks.md) — Risk matrix
- [`docs/production-readiness-assessment.md`](docs/production-readiness-assessment.md) — 10-category scorecard
- [`docs/developer-handoff.md`](docs/developer-handoff.md) — Day-one / day-two / first-week brief

**Planning & contracts**
- [`docs/00_project_documentation.md`](docs/00_project_documentation.md) — Vision, scope, business rules
- [`docs/01_database_schema_architecture.md`](docs/01_database_schema_architecture.md) — Logical data model
- [`docs/02_physical_schema_spec.md`](docs/02_physical_schema_spec.md) — PostgreSQL DDL spec
- [`docs/decisions/`](docs/decisions/) — ADRs
- [`docs/progress.md`](docs/progress.md) — Running phase tracker
- [`contracts/`](contracts/) — API and data contracts

**Phase handoffs** (work packages for each implementation phase):
`docs/claude_code_starter_prompt.md`, `docs/claude_code_backend_implementation_guide.md`, `docs/claude_code_seed_data_spec.md`, `docs/claude_code_phase3_handoff.md`, `docs/claude_code_phase4_e2e_handoff.md`, `docs/claude_code_phase5_pricing_handoff.md`, `docs/claude_code_phase7_handoff.md` (active).

---

## Hosted Railway Deployment

The repo ships a single multi-stage [`Dockerfile`](Dockerfile) that builds the
React frontend and bundles it next to the FastAPI backend. One container,
one process, one public URL — frontend at `/`, API at `/api/*` — so there is
no CORS surface to manage. Authentication is **not** in the app: put
[Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/applications/configure-apps/self-hosted-public-app/)
in front of the Railway URL with an email allowlist.

### Deploy steps

1. Create a new Railway project pointed at this repo. Railway autodetects the
   root `Dockerfile`.
2. Add a **Volume** to the service, mounted at **`/data`** (1–10 GB is plenty
   for the POC). Without this, every redeploy wipes uploads, extractions, and
   exports.
3. Set the environment variables below in the service settings.
4. Once the service is up, point Cloudflare Access at the public Railway URL
   (or a custom domain CNAME'd to it) and add the allowed emails.

### Required environment variables

| Variable | Value | Notes |
|---|---|---|
| `GEMINI_API_KEY` | your Google AI Studio key | Required for real Gemini calls |
| `USE_MOCK_GEMINI` | `false` | Defaults to `true` if you forget — UI will look broken |

### Optional environment variables

| Variable | Default | Notes |
|---|---|---|
| `APP_DATA_DIR` | `/data` (set in Dockerfile) | Override only if you mount the volume elsewhere |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Match what `real_gemini.py` expects |
| `LOG_LEVEL` | `INFO` | `DEBUG` for verbose troubleshooting |
| `ENV_FILE` | _(unset)_ | Path to a dotenv file if you'd rather load vars from a file |
| `FRONTEND_DIST_DIR` | `/app/frontend_dist` | Override only if you bake the frontend somewhere else |
| `PORT` | injected by Railway | uvicorn binds to `${PORT:-8000}` |

`DATABASE_URL` is **not required** — the active `/inbound` pipeline is
filesystem-backed. The dormant `/jobs` pipeline still imports SQLAlchemy at
startup but never opens a connection unless those routes are called.

### Volume mount

| Mount path | Purpose |
|---|---|
| `/data` | Holds `input_images/`, `inbound/`, and `exports/` so they survive container restarts |

### Single-worker constraint

The Dockerfile launches uvicorn with `--workers 1` deliberately. The active
inbound pipeline keeps extraction job state in an in-memory `_jobs` dict
inside `api/inbound_routes.py`. Multiple workers would silently round-robin
polling requests across processes and break progress reporting. To raise the
worker count, first promote `_jobs` to durable storage (Phase 7A).

### Local Docker test

Build and run the same image locally before pushing to Railway:

```bash
docker build -t catalog-capture .
docker run --rm -p 8000:8000 \
  -e GEMINI_API_KEY=your-key \
  -e USE_MOCK_GEMINI=false \
  -v "$(pwd)/_local_data:/data" \
  catalog-capture
# Open http://localhost:8000/
```

The app is reachable at `http://localhost:8000/` (frontend) and
`http://localhost:8000/api/v1/inbound` (API). Volume-mount any host folder
to `/data` to preview real persistence.

### Risks & assumptions

- **Auth is delegated to Cloudflare Access.** If you expose the Railway URL
  directly without putting CFA (or another reverse-proxy auth layer) in
  front of it, anyone with the URL can extract and export.
- **Single-user, single-worker.** No concurrency story; Phase 7A is the
  prereq for scaling beyond one reviewer.
- **Build context is large.** The Dockerfile copies `backend/src` and
  `frontend/`; `.dockerignore` excludes `node_modules/`, `input_images/`,
  `inbound/`, `exports/`, `storage/`, `test_data/`, and `.env`. If you add
  new big runtime-only folders, extend `.dockerignore` to match.
- **Volume sizing.** Camera photos average 5–15 MB and `inbound/` is purged
  on every extraction run, so the dominant cost is `input_images/` +
  `exports/`. 10 GB lasts a long time for one reviewer; revisit if usage
  grows.
- **`google-genai` requires outbound HTTPS to Google.** Railway's default
  egress works; air-gapped environments do not.
- **`dev.bat` is unaffected.** All path resolution defaults preserve the
  old "repo root = data dir" behavior on Windows.

---

## Known constraints

This is a **proof of concept**, not a production system.

- **No authentication.** Anyone who can reach the backend can extract and export.
- **Single-user assumption.** `input_images/`, `inbound/`, and `exports/` are shared folders.
- **In-memory job tracker.** A backend restart drops in-flight extraction state (completed artifacts on disk survive).
- **Windows-first.** `dev.bat` launcher and supporting scripts target Windows; Linux or cloud deployment requires additional work.
- **No automated tests on the active `/inbound` pipeline.** The 47/47 passing suite covers the dormant DB pipeline.

Full risk register: [`docs/open-issues-and-risks.md`](docs/open-issues-and-risks.md).
Path to production: [`docs/production-readiness-assessment.md`](docs/production-readiness-assessment.md).

---

## Contributing

1. Add new contracts under [`contracts/`](contracts/) and link them from [`docs/00_project_documentation.md`](docs/00_project_documentation.md).
2. Add new ADRs under [`docs/decisions/`](docs/decisions/) for significant architectural changes.
3. Update [`docs/progress.md`](docs/progress.md) at the end of each working session.
4. Never commit anything under `input_images/`, `inbound/`, `exports/`, or `storage/` — they are runtime-only.
5. Do **not** reinstall `google-generativeai` — use `google-genai` (gotcha #6 in `CLAUDE.md`).
